"""The workspace's model_call events in SQLite: an append-only event table and per-minute rollups.

An index of the event files (``event_files``), which stay the source of truth.
Every insert is idempotent by ``event_id``, so re-reading a file never
double-counts. The rollup row a new event lands in is updated in the same
transaction, so a totals query over the rollup dimensions reads at most one row
per minute per key instead of scanning raw events. Raw events are kept
``RAW_RETENTION`` and rollups indefinitely.
"""

import sqlite3
import threading
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import auto
from pathlib import Path
from typing import Final

from imbue.imbue_common.enums import UpperCaseStrEnum
from imbue.imbue_common.frozen_model import FrozenModel
from imbue.mngr_usage.model_call import ModelCallEvent
from pydantic import Field

RAW_RETENTION: Final[timedelta] = timedelta(days=90)
# Totals are sums of per-call costs; a nanodollar is far below any price step.
_COST_DECIMAL_PLACES: Final[int] = 9

# Rollup key columns; '' stands for "not known", since NULLs never collide in a unique key.
ROLLUP_DIMENSIONS: Final[tuple[str, ...]] = (
    "origin_kind",
    "origin_id",
    "agent_id",
    "model",
    "billing_mode",
)
# Every field a totals query may group by. The ones outside ROLLUP_DIMENSIONS are read from raw events.
GROUPABLE_DIMENSIONS: Final[tuple[str, ...]] = (
    *ROLLUP_DIMENSIONS,
    "provider",
    "status",
    "run_id",
    "parent_agent_id",
    "harness",
    "session_id",
    "call_source",
    "subagent_type",
    "purpose",
    "credential_ref",
    "workspace_id",
)
TOKEN_COLUMNS: Final[tuple[str, ...]] = ("input", "output", "cache_read", "cache_write")

_SCHEMA: Final[str] = """
CREATE TABLE IF NOT EXISTS model_call (
    event_id TEXT PRIMARY KEY,
    started_at REAL NOT NULL,
    ended_at REAL NOT NULL,
    provider TEXT NOT NULL,
    model TEXT,
    input INTEGER,
    output INTEGER,
    cache_read INTEGER,
    cache_write INTEGER,
    cache_write_1h INTEGER,
    cost_usd REAL,
    cost_provenance TEXT,
    billing_mode TEXT NOT NULL,
    status TEXT NOT NULL,
    credential_ref TEXT,
    workspace_id TEXT NOT NULL,
    origin_kind TEXT NOT NULL,
    origin_id TEXT,
    run_id TEXT,
    agent_id TEXT,
    parent_agent_id TEXT,
    harness TEXT,
    session_id TEXT,
    call_source TEXT,
    subagent_type TEXT,
    purpose TEXT,
    event_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS model_call_ended_at ON model_call (ended_at);
CREATE TABLE IF NOT EXISTS rollup_minute (
    minute INTEGER NOT NULL,
    origin_kind TEXT NOT NULL,
    origin_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    model TEXT NOT NULL,
    billing_mode TEXT NOT NULL,
    calls INTEGER NOT NULL,
    unknown_cost_calls INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    input INTEGER NOT NULL,
    output INTEGER NOT NULL,
    cache_read INTEGER NOT NULL,
    cache_write INTEGER NOT NULL,
    PRIMARY KEY (minute, origin_kind, origin_id, agent_id, model, billing_mode)
);
CREATE TABLE IF NOT EXISTS file_position (
    path TEXT PRIMARY KEY,
    inode INTEGER NOT NULL,
    offset INTEGER NOT NULL
);
"""


class UsageStoreError(Exception):
    """Raised for a totals query the store cannot answer (an unknown dimension or bucket)."""


class TimeBucket(UpperCaseStrEnum):
    MINUTE = auto()
    HOUR = auto()
    DAY = auto()


BUCKET_SECONDS: Final[dict[TimeBucket, int]] = {
    TimeBucket.MINUTE: 60,
    TimeBucket.HOUR: 3600,
    TimeBucket.DAY: 86400,
}


class TotalsRow(FrozenModel):
    """Cost and tokens for one group. ``cost_usd`` sums only calls with a known cost; None when there were none."""

    group: dict[str, str | None] = Field(
        description="The grouped dimensions' values; None for 'not known'"
    )
    bucket_start: datetime | None = Field(
        default=None, description="Start of the time bucket, when bucketed"
    )
    calls: int
    unknown_cost_calls: int = Field(
        description="Calls whose cost could not be determined"
    )
    cost_usd: Decimal | None
    tokens: dict[str, int]


def _rollup_key(event: ModelCallEvent) -> tuple[str, ...]:
    attribution = event.attribution
    return (
        str(attribution.origin_kind),
        attribution.origin_id or "",
        attribution.agent_id or "",
        event.model or "",
        str(event.billing_mode),
    )


class UsageStore:
    """One SQLite database, shared by the ingest, query and stream threads behind a lock."""

    def __init__(self, database_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(
            database_path, check_same_thread=False, isolation_level=None
        )
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def insert(self, event: ModelCallEvent) -> bool:
        """Store ``event`` and fold it into its rollup. Returns False when its event_id was already stored."""
        attribution = event.attribution
        tokens = event.tokens
        cost = float(event.cost_usd) if event.cost_usd is not None else None
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = self._connection.execute(
                    "INSERT OR IGNORE INTO model_call VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        event.event_id,
                        event.started_at.timestamp(),
                        event.ended_at.timestamp(),
                        event.provider,
                        event.model,
                        tokens.input,
                        tokens.output,
                        tokens.cache_read,
                        tokens.cache_write,
                        tokens.cache_write_1h,
                        cost,
                        _optional_str(event.cost_provenance),
                        str(event.billing_mode),
                        str(event.status),
                        event.credential_ref,
                        attribution.workspace_id,
                        str(attribution.origin_kind),
                        attribution.origin_id,
                        attribution.run_id,
                        attribution.agent_id,
                        attribution.parent_agent_id,
                        attribution.harness,
                        attribution.session_id,
                        _optional_str(attribution.call_source),
                        attribution.subagent_type,
                        _optional_str(attribution.purpose),
                        event.model_dump_json(),
                    ),
                )
                is_new = cursor.rowcount == 1
                if is_new:
                    self._connection.execute(
                        "INSERT INTO rollup_minute VALUES (?,?,?,?,?,?,1,?,?,?,?,?,?) "
                        "ON CONFLICT (minute, origin_kind, origin_id, agent_id, model, billing_mode) DO UPDATE SET "
                        "calls = calls + 1, unknown_cost_calls = unknown_cost_calls + excluded.unknown_cost_calls, "
                        "cost_usd = cost_usd + excluded.cost_usd, input = input + excluded.input, "
                        "output = output + excluded.output, cache_read = cache_read + excluded.cache_read, "
                        "cache_write = cache_write + excluded.cache_write",
                        (
                            int(event.ended_at.timestamp()) // 60,
                            *_rollup_key(event),
                            1 if cost is None else 0,
                            cost or 0.0,
                            tokens.input or 0,
                            tokens.output or 0,
                            tokens.cache_read or 0,
                            tokens.cache_write or 0,
                        ),
                    )
                self._connection.execute("COMMIT")
            except sqlite3.Error:
                self._connection.execute("ROLLBACK")
                raise
        return is_new

    def file_position(self, path: Path) -> tuple[int | None, int]:
        """The inode and byte offset the collector has read ``path`` up to; (None, 0) for a new file."""
        with self._lock:
            row = self._connection.execute(
                "SELECT inode, offset FROM file_position WHERE path = ?", (str(path),)
            ).fetchone()
        return (None, 0) if row is None else (row["inode"], row["offset"])

    def set_file_position(self, path: Path, inode: int, offset: int) -> None:
        with self._lock:
            self._connection.execute(
                "INSERT INTO file_position VALUES (?, ?, ?) "
                "ON CONFLICT (path) DO UPDATE SET inode = excluded.inode, offset = excluded.offset",
                (str(path), inode, offset),
            )

    def prune(self, now: datetime) -> int:
        """Delete raw events past ``RAW_RETENTION``; their rollups stay. Returns how many were deleted."""
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM model_call WHERE ended_at < ?",
                ((now - RAW_RETENTION).timestamp(),),
            )
        return cursor.rowcount

    def totals(
        self,
        group_by: Sequence[str],
        since: datetime,
        until: datetime | None = None,
        bucket: TimeBucket | None = None,
    ) -> list[TotalsRow]:
        """Cost and token totals for calls that ended in [since, until), grouped by ``group_by`` (and ``bucket``)."""
        unknown = [
            dimension for dimension in group_by if dimension not in GROUPABLE_DIMENSIONS
        ]
        if unknown:
            raise UsageStoreError(
                f"Cannot group by {unknown}; choose from {list(GROUPABLE_DIMENSIONS)}"
            )
        dimensions = list(dict.fromkeys(group_by))
        is_rollup = all(dimension in ROLLUP_DIMENSIONS for dimension in dimensions)
        if is_rollup:
            table, time_expression = "rollup_minute", "minute * 60"
            sums = [
                "SUM(calls)",
                "SUM(unknown_cost_calls)",
                "SUM(cost_usd)",
                *[f"SUM({c})" for c in TOKEN_COLUMNS],
            ]
            # A rollup's cost sum is 0.0, not NULL, when every call in it was unpriced.
            known_cost = "SUM(calls) - SUM(unknown_cost_calls)"
        else:
            table, time_expression = "model_call", "ended_at"
            sums = [
                "COUNT(*)",
                "SUM(cost_usd IS NULL)",
                "SUM(cost_usd)",
                *[f"COALESCE(SUM({c}), 0)" for c in TOKEN_COLUMNS],
            ]
            known_cost = "COUNT(cost_usd)"
        selected = list(dimensions)
        if bucket is not None:
            size = BUCKET_SECONDS[bucket]
            selected.append(
                f"(CAST({time_expression} AS INTEGER) / {size}) * {size} AS bucket_start"
            )
        group_clause = ", ".join(
            [*dimensions, *(["bucket_start"] if bucket is not None else [])]
        )
        query = (
            f"SELECT {', '.join([*selected, *sums, known_cost])} FROM {table} "
            f"WHERE {time_expression} >= ? AND {time_expression} < ?"
            + (
                f" GROUP BY {group_clause} ORDER BY {group_clause}"
                if group_clause
                else ""
            )
        )
        until_value = (
            until or datetime.now(timezone.utc) + timedelta(days=1)
        ).timestamp()
        with self._lock:
            rows = self._connection.execute(
                query, (since.timestamp(), until_value)
            ).fetchall()
        return [
            _totals_row(row, dimensions, bucket is not None, is_rollup) for row in rows
        ]


def _totals_row(
    row: sqlite3.Row, dimensions: list[str], is_bucketed: bool, is_rollup: bool
) -> TotalsRow:
    values = list(row)
    group = {
        dimension: (None if is_rollup and values[index] == "" else values[index])
        for index, dimension in enumerate(dimensions)
    }
    offset = len(dimensions)
    bucket_start = None
    if is_bucketed:
        bucket_start = datetime.fromtimestamp(values[offset], tz=timezone.utc)
        offset += 1
    calls, unknown_cost_calls, cost, *token_sums, known_cost_calls = values[offset:]
    return TotalsRow(
        group=group,
        bucket_start=bucket_start,
        calls=calls or 0,
        unknown_cost_calls=unknown_cost_calls or 0,
        cost_usd=_summed_cost(cost) if known_cost_calls and cost is not None else None,
        tokens=dict(zip(TOKEN_COLUMNS, (int(value or 0) for value in token_sums))),
    )


def _optional_str(value: object | None) -> str | None:
    return None if value is None else str(value)


def _summed_cost(cost: float) -> Decimal:
    """A SQLite sum as dollars, without the float noise summing adds (0.0016, not 0.0015999999999999999)."""
    return Decimal(repr(round(cost, _COST_DECIMAL_PLACES)))
