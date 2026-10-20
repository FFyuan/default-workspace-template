from imbue.imbue_common.model_update import to_update
from routines.data_types import RoutineState
from routines.primitives import RoutineId
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
