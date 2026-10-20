import json

from imbue.imbue_common.model_update import to_update
from routines.data_types import RoutineState
from routines.primitives import RoutineId
from routines.primitives import RunId
from routines.state import FileStateStore

DIGEST = RoutineId("inbox-digest")


def test_a_routine_with_no_state_file_starts_fresh(states: FileStateStore) -> None:
    assert states.read(DIGEST) == RoutineState()


def test_an_update_is_written_whole_and_read_back(states: FileStateStore) -> None:
    updated = states.update(
        DIGEST, lambda state: state.model_copy_update(to_update(state.field_ref().is_enabled, False))
    )
    assert updated.is_enabled is False
    assert states.read(DIGEST).is_enabled is False
    assert states.paths.state_path(DIGEST).is_file()


def test_a_state_file_that_does_not_parse_reads_fresh_and_is_set_aside_by_the_next_write(
    states: FileStateStore,
) -> None:
    path = states.paths.state_path(DIGEST)
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    assert states.read(DIGEST) == RoutineState()
    assert path.read_text() == "{not json", "a read never rewrites the file"

    updated = states.update(
        DIGEST, lambda state: state.model_copy_update(to_update(state.field_ref().is_enabled, False))
    )

    assert updated.is_enabled is False
    assert states.read(DIGEST).is_enabled is False
    assert path.with_suffix(".json.bad").read_text() == "{not json"


def test_removing_a_routine_drops_its_whole_state_directory(states: FileStateStore) -> None:
    states.update(DIGEST, lambda state: state)
    states.remove(DIGEST)
    assert not states.paths.routine_state_dir(DIGEST).exists()


def test_a_field_a_newer_writer_added_is_ignored_in_the_state_and_in_its_runs(states: FileStateStore) -> None:
    """The app may read a state file written by a newer library mid-update; one unknown field must not reset it."""
    path = states.paths.state_path(DIGEST)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "is_enabled": False,
                "newer_field": 1,
                "current_run": {
                    "run_id": str(RunId.generate()),
                    "pid": 1,
                    "trigger": "MANUAL",
                    "started_at": "2026-10-20T15:00:00+00:00",
                    "newer_field": 1,
                },
                "last_run": {
                    "run_id": str(RunId.generate()),
                    "trigger": "MANUAL",
                    "kind": "COMMAND",
                    "outcome": "SUCCEEDED",
                    "summary": "",
                    "started_at": "2026-10-20T14:00:00+00:00",
                    "finished_at": "2026-10-20T14:01:00+00:00",
                    "newer_field": 1,
                },
            }
        )
    )
    state = states.read(DIGEST)
    assert state.is_enabled is False
    assert state.current_run is not None and state.last_run is not None
