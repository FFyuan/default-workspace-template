"""The run ledger: append-only events under the standard envelope, read from the tail."""

import gzip
import json
import os
import shutil
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Final

from loguru import logger
from pydantic import ValidationError

from imbue.imbue_common.pure import pure
from routines.data_types import RUN_BLOCKED_EVENT
from routines.data_types import RUN_FINISHED_EVENT
from routines.data_types import RUN_STARTED_EVENT
from routines.data_types import RunBlockedEvent
from routines.data_types import RunEvent
from routines.data_types import RunFinishedEvent
from routines.data_types import RunStartedEvent
from routines.interfaces import LedgerInterface
from routines.primitives import RoutineId
from routines.primitives import RunId

LEDGER_SIZE_CAP_BYTES: Final[int] = 16 * 1024 * 1024
_READ_CHUNK_BYTES: Final[int] = 64 * 1024


def _iter_lines_newest_first(path: Path) -> Iterator[str]:
    """The file's lines from the last to the first, read in chunks from the end."""
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        remainder = b""
        while position > 0:
            read_size = min(_READ_CHUNK_BYTES, position)
            position -= read_size
            handle.seek(position)
            chunk = handle.read(read_size) + remainder
            lines = chunk.split(b"\n")
            remainder = lines[0]
            for line in reversed(lines[1:]):
                if line.strip():
                    yield line.decode("utf-8", errors="replace")
        if remainder.strip():
            yield remainder.decode("utf-8", errors="replace")


@pure
def parse_run_event(line: str) -> RunEvent | None:
    """One ledger line as its event; None, with a warning, for a line that is not one."""
    try:
        raw = json.loads(line)
    except ValueError:
        logger.warning("Skipping a ledger line that is not JSON")
        return None
    if not isinstance(raw, dict):
        logger.warning("Skipping a ledger line that is not an object")
        return None
    event_type = raw.get("type")
    try:
        if event_type == RUN_STARTED_EVENT:
            return RunStartedEvent.model_validate(raw)
        if event_type == RUN_BLOCKED_EVENT:
            return RunBlockedEvent.model_validate(raw)
        if event_type == RUN_FINISHED_EVENT:
            return RunFinishedEvent.model_validate(raw)
    except ValidationError as e:
        logger.warning("Skipping a ledger line that does not validate: {}", e)
        return None
    logger.warning("Skipping a ledger event of an unknown type: {}", event_type)
    return None


class FileLedger(LedgerInterface):
    """The ledger as one JSON Lines file, archived with gzip once it is past the cap."""

    def append(self, event: RunEvent) -> None:
        path = self.paths.events_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")

    def recent_events(self, routine_id: RoutineId, run_limit: int) -> list[RunEvent]:
        path = self.paths.events_path
        if not path.is_file() or run_limit <= 0:
            return []
        events: list[RunEvent] = []
        starts_seen = 0
        for line in _iter_lines_newest_first(path):
            event = parse_run_event(line)
            if event is None or event.routine_id != routine_id:
                continue
            events.append(event)
            if isinstance(event, RunStartedEvent):
                starts_seen += 1
                if starts_seen >= run_limit:
                    break
        return events

    def events_of_run(self, routine_id: RoutineId, run_id: RunId) -> list[RunEvent]:
        path = self.paths.events_path
        if not path.is_file():
            return []
        events: list[RunEvent] = []
        for line in _iter_lines_newest_first(path):
            event = parse_run_event(line)
            if event is None or event.routine_id != routine_id or event.run_id != run_id:
                continue
            events.append(event)
            if isinstance(event, RunStartedEvent):
                break
        events.reverse()
        return events

    def rotate_if_large(self, now: datetime) -> bool:
        path = self.paths.events_path
        if not path.is_file() or path.stat().st_size < LEDGER_SIZE_CAP_BYTES:
            return False
        archive = path.with_name(f"events.{now.strftime('%Y-%m-%d')}.jsonl.gz")
        with path.open("rb") as source, gzip.open(archive, "wb") as target:
            shutil.copyfileobj(source, target)
        path.write_text("", encoding="utf-8")
        logger.info("Archived the run ledger to {}", archive.name)
        return True
