import gzip
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from imbue.imbue_common.logging import format_nanosecond_iso_timestamp
from imbue.imbue_common.logging import generate_log_event_id
from routines.data_types import RUN_EVENTS_SOURCE
from routines.data_types import RUN_FINISHED_EVENT
from routines.data_types import RUN_STARTED_EVENT
from routines.data_types import RunFinishedEvent
from routines.data_types import RunStartedEvent
from routines.ledger import FileLedger
from routines.ledger import LEDGER_SIZE_CAP_BYTES
from routines.primitives import RoutineId
from routines.primitives import RunId
from routines.primitives import RunKind
from routines.primitives import RunOutcome
from routines.primitives import RunTrigger

DIGEST = RoutineId("inbox-digest")
OTHER = RoutineId("other")
NOW = datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)


def _started(routine_id: RoutineId, run_id: RunId, at: datetime) -> RunStartedEvent:
    return RunStartedEvent(
        timestamp=format_nanosecond_iso_timestamp(at),
        type=RUN_STARTED_EVENT,
        event_id=generate_log_event_id(),
        source=RUN_EVENTS_SOURCE,
        routine_id=routine_id,
        run_id=run_id,
        trigger=RunTrigger.SCHEDULED,
        kind=RunKind.COMMAND,
        command="true",
    )


def _finished(routine_id: RoutineId, run_id: RunId, at: datetime) -> RunFinishedEvent:
    return RunFinishedEvent(
        timestamp=format_nanosecond_iso_timestamp(at),
        type=RUN_FINISHED_EVENT,
        event_id=generate_log_event_id(),
        source=RUN_EVENTS_SOURCE,
        routine_id=routine_id,
        run_id=run_id,
        outcome=RunOutcome.SUCCEEDED,
        exit_code=0,
        duration_seconds=1.0,
        summary="",
        chat_id=None,
        warnings=(),
        output_tail="",
    )


def test_recent_events_cover_only_the_newest_runs_of_the_routine(ledger: FileLedger) -> None:
    run_ids = [RunId.generate() for _ in range(3)]
    for index, run_id in enumerate(run_ids):
        at = NOW + timedelta(minutes=index)
        ledger.append(_started(DIGEST, run_id, at))
        ledger.append(_finished(DIGEST, run_id, at + timedelta(seconds=1)))
    ledger.append(_started(OTHER, RunId.generate(), NOW + timedelta(minutes=5)))

    events = ledger.recent_events(DIGEST, run_limit=2)

    assert [event.run_id for event in events] == [run_ids[2], run_ids[2], run_ids[1], run_ids[1]]
    assert all(event.routine_id == DIGEST for event in events)


def test_the_events_of_one_run_come_back_oldest_first(ledger: FileLedger) -> None:
    run_id = RunId.generate()
    ledger.append(_started(DIGEST, run_id, NOW))
    ledger.append(_started(DIGEST, RunId.generate(), NOW + timedelta(minutes=1)))
    ledger.append(_finished(DIGEST, run_id, NOW + timedelta(seconds=2)))

    events = ledger.events_of_run(DIGEST, run_id)

    assert [type(event).__name__ for event in events] == ["RunStartedEvent", "RunFinishedEvent"]
    assert ledger.events_of_run(DIGEST, RunId.generate()) == []


def test_a_line_that_is_not_an_event_is_skipped(ledger: FileLedger) -> None:
    run_id = RunId.generate()
    ledger.append(_started(DIGEST, run_id, NOW))
    with ledger.paths.events_path.open("a") as handle:
        handle.write('not json\n{"type": "run_started"}\n')

    assert [event.run_id for event in ledger.recent_events(DIGEST, run_limit=5)] == [run_id]


def test_the_ledger_is_archived_once_past_the_cap(ledger: FileLedger) -> None:
    ledger.append(_started(DIGEST, RunId.generate(), NOW))
    assert ledger.rotate_if_large(NOW) is False
    with ledger.paths.events_path.open("a") as handle:
        handle.write("x" * LEDGER_SIZE_CAP_BYTES)

    assert ledger.rotate_if_large(NOW) is True

    assert not ledger.paths.events_path.exists()
    archive = ledger.paths.events_path.parent / "events.2026-10-20.jsonl.gz"
    with gzip.open(archive, "rt", encoding="utf-8") as handle:
        assert handle.read().count("run_started") == 1
    assert not (ledger.paths.events_path.parent / "events.jsonl.rotating").exists()
    # The next append starts the new file.
    run_id = RunId.generate()
    ledger.append(_started(DIGEST, run_id, NOW))
    assert [event.run_id for event in ledger.recent_events(DIGEST, run_limit=5)] == [run_id]


def test_a_second_archive_on_the_same_day_gets_its_own_name(ledger: FileLedger) -> None:
    for _ in range(2):
        ledger.append(_started(DIGEST, RunId.generate(), NOW))
        with ledger.paths.events_path.open("a") as handle:
            handle.write("x" * LEDGER_SIZE_CAP_BYTES)
        assert ledger.rotate_if_large(NOW) is True

    archives = sorted(path.name for path in ledger.paths.events_path.parent.glob("*.gz"))
    assert archives == ["events.2026-10-20.1.jsonl.gz", "events.2026-10-20.jsonl.gz"]


def test_a_file_a_dead_rotation_left_aside_is_archived_before_the_next(ledger: FileLedger) -> None:
    ledger.append(_started(DIGEST, RunId.generate(), NOW))
    left_aside = ledger.paths.events_path.parent / "events.jsonl.rotating"
    left_aside.write_text('{"type": "run_started", "left": "aside"}\n')

    assert ledger.rotate_if_large(NOW) is False

    assert not left_aside.exists()
    with gzip.open(ledger.paths.events_path.parent / "events.2026-10-20.jsonl.gz", "rt", encoding="utf-8") as handle:
        assert "aside" in handle.read()
    assert ledger.paths.events_path.is_file()
