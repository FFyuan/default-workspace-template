import subprocess
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path

import pytest
from flask.testing import FlaskClient

from routines.definitions import FileDefinitionStore
from routines.ledger import FileLedger
from routines.mock_chat_app_test import ScriptedChatApp
from routines.mock_clock_test import FakeClock
from routines.mock_notifier_test import RecordingNotifier
from routines.paths import RoutinesPaths
from routines.repository import GitRepository
from routines.runner import Runner
from routines.service import RoutinesService
from routines.state import FileStateStore
from routines_app.server import create_app

TEST_ZONE = timezone(timedelta(hours=-8))
TEST_NOW = datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def git_paths(tmp_path: Path) -> RoutinesPaths:
    root = tmp_path / "workspace"
    (root / "system" / "routines").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    (root / "README.md").write_text("a workspace\n")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True)
    return RoutinesPaths(repo_root=root)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(current=TEST_NOW, zone=TEST_ZONE)


@pytest.fixture
def chat_app() -> ScriptedChatApp:
    return ScriptedChatApp()


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()


@pytest.fixture
def service(
    git_paths: RoutinesPaths, clock: FakeClock, chat_app: ScriptedChatApp, notifier: RecordingNotifier
) -> RoutinesService:
    repository = GitRepository(repo_root=git_paths.repo_root, clock=clock)
    definitions = FileDefinitionStore(paths=git_paths, repository=repository)
    states = FileStateStore(paths=git_paths)
    ledger = FileLedger(paths=git_paths)
    runner = Runner(
        paths=git_paths,
        definitions=definitions,
        states=states,
        ledger=ledger,
        chat_app=chat_app,
        notifier=notifier,
        clock=clock,
    )
    return RoutinesService(
        paths=git_paths,
        definitions=definitions,
        states=states,
        ledger=ledger,
        chat_app=chat_app,
        clock=clock,
        runner=runner,
    )


@pytest.fixture
def static_directory(tmp_path: Path) -> Path:
    directory = tmp_path / "static"
    (directory / "assets").mkdir(parents=True)
    (directory / "index.html").write_text("<!doctype html><title>Routines</title><div id=app></div>")
    (directory / "assets" / "app.js").write_text("console.log('built');")
    return directory


@pytest.fixture
def client(service: RoutinesService, static_directory: Path) -> FlaskClient:
    return create_app(service, static_directory, is_preview=False).test_client()


@pytest.fixture
def preview_client(service: RoutinesService, static_directory: Path) -> FlaskClient:
    return create_app(service, static_directory, is_preview=True).test_client()
