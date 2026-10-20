from pathlib import Path

import pytest
from flask.testing import FlaskClient

from routines.mock_chat_app_test import ScriptedChatApp
from routines.mock_clock_test import FakeClock
from routines.mock_notifier_test import RecordingNotifier
from routines.paths import RoutinesPaths
from routines.repository import GitRepository
from routines.service import RoutinesService
from routines.testing import TEST_NOW
from routines.testing import TEST_ZONE
from routines.testing import build_test_service
from routines.testing import init_git_workspace
from routines.testing import make_workspace_paths
from routines_app.mock_fix_chat_test import RecordingFixChatStarter
from routines_app.server import create_app


@pytest.fixture
def git_paths(tmp_path: Path) -> RoutinesPaths:
    return init_git_workspace(make_workspace_paths(tmp_path / "workspace"))


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
    return build_test_service(git_paths, repository, clock, chat_app, notifier)


@pytest.fixture
def static_directory(tmp_path: Path) -> Path:
    directory = tmp_path / "static"
    (directory / "assets").mkdir(parents=True)
    (directory / "index.html").write_text("<!doctype html><head><title>Routines</title></head><div id=app></div>")
    (directory / "assets" / "app.js").write_text("console.log('built');")
    return directory


@pytest.fixture
def fix_chat_starter() -> RecordingFixChatStarter:
    return RecordingFixChatStarter()


@pytest.fixture
def client(service: RoutinesService, static_directory: Path, fix_chat_starter: RecordingFixChatStarter) -> FlaskClient:
    return create_app(service, static_directory, is_preview=False, fix_chat_starter=fix_chat_starter).test_client()


@pytest.fixture
def preview_client(
    service: RoutinesService, static_directory: Path, fix_chat_starter: RecordingFixChatStarter
) -> FlaskClient:
    return create_app(service, static_directory, is_preview=True, fix_chat_starter=fix_chat_starter).test_client()
