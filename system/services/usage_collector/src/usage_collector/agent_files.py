"""Following the mngr_usage event files of every agent on the workspace's host.

Agent harnesses write their usage events to the agent's own file
(``<host dir>/agents/<agent>/events/<source>/usage/events.jsonl``), and mngr
preserves a destroyed agent's files under ``<host dir>/preserved/``. Those
files are the durable record, so agent events need no spool: the collector
reads each file from where it left off, about once a second, and remembers
its place in the store across restarts.

Only lines that are model_call events (they carry a ``schema_version`` and an
``attribution``) are ingested; the older snapshot events the same files hold
are left to ``mngr usage``. A file that shrank or was replaced is read again
from the start, which re-sends events the store already holds and dedupes.
"""

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Final

from loguru import logger

from usage_collector.store import UsageStore

EVENT_FILE_GLOBS: Final[tuple[str, ...]] = (
    "agents/*/events/*/usage/events.jsonl",
    "preserved/*/events/*/usage/events.jsonl",
)
# Bounds one pass over a file that grew a lot while the collector was down.
_MAX_BYTES_PER_PASS: Final[int] = 8 * 1024 * 1024


def is_model_call_line(record: object) -> bool:
    return (
        isinstance(record, dict)
        and "schema_version" in record
        and "attribution" in record
    )


def event_files(host_dir: Path) -> Iterator[Path]:
    for pattern in EVENT_FILE_GLOBS:
        yield from sorted(host_dir.glob(pattern))


def follow_agent_event_files(
    host_dir: Path, store: UsageStore, ingest: Callable[[object], object]
) -> int:
    """Ingest the model_call lines added to every agent event file since the last pass. Returns how many were read."""
    read = 0
    for path in event_files(host_dir):
        try:
            stat = path.stat()
        except OSError:
            continue
        inode, offset = store.file_position(path)
        if inode != stat.st_ino or stat.st_size < offset:
            offset = 0
        if stat.st_size == offset:
            continue
        try:
            with path.open("rb") as handle:
                handle.seek(offset)
                chunk = handle.read(_MAX_BYTES_PER_PASS)
        except OSError as e:
            logger.warning("Could not read agent usage file {}: {}", path, e)
            continue
        # Only whole lines: a writer may be partway through the last one.
        complete = chunk[: chunk.rfind(b"\n") + 1]
        for line in complete.splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning("Skipped an unreadable line in {}: {}", path, e)
                continue
            if is_model_call_line(record):
                ingest(record)
                read += 1
        store.set_file_position(path, stat.st_ino, offset + len(complete))
    return read
