import pytest

from imbue.imbue_common.model_update import to_update
from routines.data_types import RoutineDefinition
from routines.errors import DefinitionCommitError
from routines.errors import RunInFlightError
from routines.locks import held_lock
from routines.mock_chat_app_test import ScriptedChatApp
from routines.mock_clock_test import FakeClock
from routines.mock_notifier_test import RecordingNotifier
from routines.mock_repository_test import RecordingRepository
from routines.paths import RoutinesPaths
from routines.primitives import RoutineId
from routines.state import FileStateStore
from routines.testing import build_test_service

SYNC = RoutineId("nightly-sync")


def test_a_removal_whose_commit_is_refused_still_stops_the_chat_and_drops_the_state(
    paths: RoutinesPaths,
    clock: FakeClock,
    chat_app: ScriptedChatApp,
    notifier: RecordingNotifier,
) -> None:
    repository = RecordingRepository(repo_root=paths.repo_root)
    service = build_test_service(paths, repository, FileStateStore(paths=paths), clock, chat_app, notifier)
    service.add(
        SYNC, RoutineDefinition.model_validate({"title": "Digest", "what": "Digests.", "every": "1d", "skill": "x"})
    )
    service.states.update(SYNC, lambda state: state.model_copy_update(to_update(state.field_ref().chat_id, "agent-1")))
    repository.is_refusing = True

    with pytest.raises(DefinitionCommitError):
        service.remove(SYNC)

    assert chat_app.verbs == [("agent-1", "stop")]
    assert not paths.routine_state_dir(SYNC).exists()
    assert not paths.definition_path(SYNC).exists()


def test_a_routine_whose_run_lock_is_held_cannot_be_removed(
    paths: RoutinesPaths,
    repository: RecordingRepository,
    clock: FakeClock,
    chat_app: ScriptedChatApp,
    notifier: RecordingNotifier,
) -> None:
    service = build_test_service(paths, repository, FileStateStore(paths=paths), clock, chat_app, notifier)
    service.add(
        SYNC,
        RoutineDefinition.model_validate(
            {"title": "Nightly sync", "what": "Syncs.", "every": "1d", "command": ["true"]}
        ),
    )

    with held_lock(paths.run_lock_path(SYNC), "A run"), pytest.raises(RunInFlightError):
        service.remove(SYNC)

    assert service.definitions.load(SYNC).definition is not None
    service.remove(SYNC)
    assert not paths.definition_path(SYNC).exists()
    assert not paths.routine_state_dir(SYNC).exists()
