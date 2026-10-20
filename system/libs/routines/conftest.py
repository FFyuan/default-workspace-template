import json
import threading
from collections.abc import Generator
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from routines.definitions import FileDefinitionStore
from routines.ledger import FileLedger
from routines.mock_chat_app_test import ScriptedChatApp
from routines.mock_clock_test import FakeClock
from routines.mock_http_server_test import FakeHttpServer
from routines.mock_notifier_test import RecordingNotifier
from routines.mock_repository_test import RecordingRepository
from routines.paths import RoutinesPaths
from routines.runner import Runner
from routines.state import FileStateStore
from routines.testing import TEST_NOW
from routines.testing import TEST_ZONE
from routines.testing import init_git_workspace
from routines.testing import make_workspace_paths


@pytest.fixture
def paths(tmp_path: Path) -> RoutinesPaths:
    return make_workspace_paths(tmp_path / "workspace")


@pytest.fixture
def git_paths(paths: RoutinesPaths) -> RoutinesPaths:
    """The same root as a git repository with one commit, for the stores that commit."""
    return init_git_workspace(paths)


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


@pytest.fixture
def http_server() -> Generator[FakeHttpServer, None, None]:
    holder: list[FakeHttpServer] = []

    class Handler(BaseHTTPRequestHandler):
        def _serve(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b""
            body = json.loads(raw) if raw else None
            status, answer = holder[0].take(
                self.command, self.path, {key.lower(): value for key, value in self.headers.items()}, body
            )
            payload = json.dumps(answer).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            self._serve()

        def do_POST(self) -> None:
            self._serve()

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    holder.append(FakeHttpServer(url=f"http://127.0.0.1:{server.server_port}"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield holder[0]
    finally:
        server.shutdown()
        server.server_close()
