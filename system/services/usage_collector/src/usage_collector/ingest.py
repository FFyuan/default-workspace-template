"""The one path every model_call takes into the store: validate, price, insert, publish."""

import json
from collections.abc import Callable, Mapping
from enum import auto
from pathlib import Path

from imbue.imbue_common.enums import UpperCaseStrEnum
from imbue.mngr_usage.model_call import ModelCallEvent, price_model_call
from loguru import logger
from pydantic import ValidationError
from workspace_usage.emit import SPOOL_SUFFIX

from usage_collector.claude_sessions import (
    ClaudeSessionNotFoundError,
    ClaudeSessionReport,
    read_reported_session,
)
from usage_collector.feed import UsageFeed
from usage_collector.store import UsageStore

REJECTED_DIR_NAME = "rejected"


class IngestOutcome(UpperCaseStrEnum):
    STORED = auto()
    DUPLICATE = auto()
    REJECTED = auto()


IngestCounts = dict[IngestOutcome, int]


def empty_counts() -> IngestCounts:
    return {outcome: 0 for outcome in IngestOutcome}


def describe_counts(counts: Mapping[IngestOutcome, int]) -> dict[str, int]:
    return {str(outcome).lower(): count for outcome, count in counts.items()}


class Ingestor:
    """Validates raw events against the model_call schema, prices token-only ones, stores and publishes them."""

    def __init__(self, store: UsageStore, feed: UsageFeed) -> None:
        self._store = store
        self._feed = feed

    def ingest(self, payload: object) -> tuple[IngestOutcome, str | None]:
        """Ingest one raw event. Returns the outcome and, for a rejected event, why."""
        try:
            event = ModelCallEvent.model_validate(payload)
        except ValidationError as e:
            return IngestOutcome.REJECTED, str(e)
        return self.ingest_event(event), None

    def ingest_event(self, event: ModelCallEvent) -> IngestOutcome:
        priced = price_model_call(event)
        if not self._store.insert(priced):
            return IngestOutcome.DUPLICATE
        self._feed.publish(priced)
        return IngestOutcome.STORED

    def ingest_many(self, payloads: list[object]) -> IngestCounts:
        counts = empty_counts()
        for payload in payloads:
            outcome, reason = self.ingest(payload)
            counts[outcome] += 1
            if reason is not None:
                logger.warning("Rejected a model_call event: {}", reason)
        return counts

    def ingest_claude_session(self, payload: object) -> tuple[IngestCounts, str | None]:
        """Read a reported claude -p session's calls from its log. Returns the counts and, if rejected, why."""
        counts = empty_counts()
        try:
            report = ClaudeSessionReport.model_validate(payload)
            events = read_reported_session(report)
        except (ValidationError, ClaudeSessionNotFoundError) as e:
            counts[IngestOutcome.REJECTED] += 1
            return counts, str(e)
        for event in events:
            counts[self.ingest_event(event)] += 1
        return counts, None

    def drain_events_spool(self, spool_dir: Path) -> IngestCounts:
        return _drain(spool_dir, self.ingest)

    def drain_claude_sessions_spool(self, spool_dir: Path) -> IngestCounts:
        def _ingest_session(payload: object) -> tuple[IngestOutcome, str | None]:
            counts, reason = self.ingest_claude_session(payload)
            return (
                (IngestOutcome.REJECTED, reason)
                if reason is not None
                else (IngestOutcome.STORED, None)
            )

        return _drain(spool_dir, _ingest_session)


def _drain(
    spool_dir: Path, ingest: Callable[[object], tuple[IngestOutcome, str | None]]
) -> IngestCounts:
    """Ingest every spooled report and delete its file; a rejected one is kept aside under ``rejected/``."""
    counts = empty_counts()
    if not spool_dir.is_dir():
        return counts
    for path in sorted(spool_dir.glob(f"*{SPOOL_SUFFIX}")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            outcome, reason = IngestOutcome.REJECTED, f"unreadable spool file: {e}"
        else:
            outcome, reason = ingest(payload)
        counts[outcome] += 1
        if outcome == IngestOutcome.REJECTED:
            logger.warning("Rejected spooled report {}: {}", path.name, reason)
            rejected_dir = spool_dir / REJECTED_DIR_NAME
            rejected_dir.mkdir(exist_ok=True)
            path.rename(rejected_dir / path.name)
        else:
            path.unlink(missing_ok=True)
    return counts
