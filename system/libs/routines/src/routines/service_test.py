import pytest

from routines.data_types import RoutineDefinition
from routines.errors import RunInFlightError
from routines.locks import held_lock
from routines.mock_chat_app_test import ScriptedChatApp
from routines.mock_clock_test import FakeClock
from routines.mock_notifier_test import RecordingNotifier
from routines.mock_repository_test import RecordingRepository
from routines.paths import RoutinesPaths
from routines.primitives import RoutineId
from routines.testing import build_test_service

SYNC = RoutineId("nightly-sync")


def test_a_routine_whose_run_lock_is_held_cannot_be_removed(
    paths: RoutinesPaths,
    repository: RecordingRepository,
    clock: FakeClock,
    chat_app: ScriptedChatApp,
    notifier: RecordingNotifier,
) -> None:
    service = build_test_service(paths, repository, clock, chat_app, notifier)
    service.add(
        SYNC,
        RoutineDefinition.model_validate({"title": "Nightly sync", "what": "Syncs.", "every": "1d", "command": ["true"]}),
    )

    with held_lock(paths.run_lock_path(SYNC), "A run"), pytest.raises(RunInFlightError):
        service.remove(SYNC)

    assert service.definitions.load(SYNC).definition is not None
    service.remove(SYNC)
    assert not paths.definition_path(SYNC).exists()
    assert not paths.routine_state_dir(SYNC).exists()
