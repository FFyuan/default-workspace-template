import subprocess
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path

import pytest

from routines.definitions import FileDefinitionStore
from routines.ledger import FileLedger
from routines.mock_chat_app_test import ScriptedChatApp
from routines.mock_clock_test import FakeClock
from routines.mock_notifier_test import RecordingNotifier
from routines.mock_repository_test import RecordingRepository
from routines.paths import RoutinesPaths
from routines.runner import Runner
from routines.state import FileStateStore

# A fixed zone so the tests read the same everywhere: eight hours behind UTC, with no daylight saving.
TEST_ZONE = timezone(timedelta(hours=-8))
TEST_NOW = datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def paths(tmp_path: Path) -> RoutinesPaths:
    root = tmp_path / "workspace"
    (root / "system" / "routines").mkdir(parents=True)
    return RoutinesPaths(repo_root=root)


@pytest.fixture
def git_paths(paths: RoutinesPaths) -> RoutinesPaths:
    """The same root as a git repository with one commit, for the stores that commit."""
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=paths.repo_root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=paths.repo_root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=paths.repo_root, check=True)
    (paths.repo_root / "README.md").write_text("a workspace\n")
    subprocess.run(["git", "add", "README.md"], cwd=paths.repo_root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=paths.repo_root, check=True)
    return paths


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(current=TEST_NOW, zone=TEST_ZONE)


@pytest.fixture
def repository(paths: RoutinesPaths) -> RecordingRepository:
    return RecordingRepository(repo_root=paths.repo_root)


@pytest.fixture
def definitions(paths: RoutinesPaths, repository: RecordingRepository) -> FileDefinitionStore:
    return FileDefinitionStore(paths=paths, repository=repository)


@pytest.fixture
def states(paths: RoutinesPaths) -> FileStateStore:
    return FileStateStore(paths=paths)


@pytest.fixture
def ledger(paths: RoutinesPaths) -> FileLedger:
    return FileLedger(paths=paths)


@pytest.fixture
def chat_app() -> ScriptedChatApp:
    return ScriptedChatApp()


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()


@pytest.fixture
def runner(
    paths: RoutinesPaths,
    definitions: FileDefinitionStore,
    states: FileStateStore,
    ledger: FileLedger,
    chat_app: ScriptedChatApp,
    notifier: RecordingNotifier,
    clock: FakeClock,
) -> Runner:
    return Runner(
        paths=paths,
        definitions=definitions,
        states=states,
        ledger=ledger,
        chat_app=chat_app,
        notifier=notifier,
        clock=clock,
    )
