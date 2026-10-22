import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from workspace_usage.emit import emit_claude_session, emit_model_call


class _Recorder(BaseHTTPRequestHandler):
    received: list[tuple[str, dict[str, object]]] = []
    status = 200

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers["Content-Length"]))
        type(self).received.append((self.path, json.loads(body)))
        self.send_response(type(self).status)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def collector() -> Iterator[tuple[str, type[_Recorder]]]:
    handler = type("Recorder", (_Recorder,), {"received": [], "status": 200})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", handler
    server.shutdown()
    server.server_close()


def test_an_event_goes_straight_to_a_running_collector(
    tmp_path: Path, collector: tuple[str, type[_Recorder]]
) -> None:
    url, handler = collector
    environ = {"IMBUE_USAGE_COLLECTOR_URL": url, "IMBUE_USAGE_DATA_DIR": str(tmp_path)}

    assert emit_model_call({"event_id": "e-1"}, environ)
    assert emit_claude_session({"session_id": "s-1"}, environ)

    assert handler.received == [
        ("/v1/events", {"event_id": "e-1"}),
        ("/v1/claude-sessions", {"session_id": "s-1"}),
    ]
    assert not (tmp_path / "spool").exists()


def test_an_unreachable_collector_gets_the_report_spooled_by_kind(
    tmp_path: Path,
) -> None:
    environ = {
        "IMBUE_USAGE_COLLECTOR_URL": "http://127.0.0.1:1",
        "IMBUE_USAGE_DATA_DIR": str(tmp_path),
    }

    assert not emit_model_call({"event_id": "e-2"}, environ)
    assert not emit_claude_session({"session_id": "s-2"}, environ)

    [event_file] = (tmp_path / "spool" / "events").glob("*.json")
    [session_file] = (tmp_path / "spool" / "claude-sessions").glob("*.json")
    assert json.loads(event_file.read_text()) == {"event_id": "e-2"}
    assert json.loads(session_file.read_text()) == {"session_id": "s-2"}


def test_a_collector_error_spools_but_a_rejection_does_not(
    tmp_path: Path, collector: tuple[str, type[_Recorder]]
) -> None:
    url, handler = collector
    environ = {"IMBUE_USAGE_COLLECTOR_URL": url, "IMBUE_USAGE_DATA_DIR": str(tmp_path)}

    handler.status = 500
    emit_model_call({"event_id": "e-3"}, environ)
    handler.status = 400
    emit_model_call({"event_id": "e-4"}, environ)

    assert [
        json.loads(p.read_text())["event_id"]
        for p in (tmp_path / "spool" / "events").glob("*.json")
    ] == ["e-3"]
