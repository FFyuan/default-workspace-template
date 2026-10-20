from pathlib import Path

import pytest

from routines.chat_app import HttpChatApp
from routines.errors import ChatAppError
from routines.mock_clock_test import FakeClock
from routines.mock_http_server_test import FakeHttpServer
from routines.primitives import ChatStatusWord


def _chat_app(tmp_path: Path, http_server: FakeHttpServer, clock: FakeClock) -> HttpChatApp:
    registry = tmp_path / "apps.toml"
    registry.write_text(f'[[apps]]\nname = "chat"\nurl = "{http_server.url}"\n')
    return HttpChatApp(repo_root=tmp_path, registry_path=registry, environ={}, clock=clock)


def test_the_status_is_read_from_the_chat_list_and_unknown_words_read_as_unknown(
    tmp_path: Path, http_server: FakeHttpServer, clock: FakeClock
) -> None:
    http_server.answer(
        "GET",
        "/api/chats",
        (200, {"chats": [{"chat_id": "a", "status": "working"}, {"chat_id": "b", "status": "dreaming"}]}),
    )
    chat_app = _chat_app(tmp_path, http_server, clock)
    assert chat_app.chat_status("a") is ChatStatusWord.WORKING
    assert chat_app.chat_status("b") is ChatStatusWord.UNKNOWN
    assert chat_app.chat_status("c") is None


def test_a_send_waits_out_a_not_ready_answer_and_a_refusal_is_an_error_in_the_apps_words(
    tmp_path: Path, http_server: FakeHttpServer, clock: FakeClock
) -> None:
    http_server.answer("POST", "/api/chats/a/message", (503, {"detail": "starting"}), (200, {}))
    http_server.answer("POST", "/api/chats/b/message", (409, {"detail": "the chat moved on"}))
    chat_app = _chat_app(tmp_path, http_server, clock)

    chat_app.send_message("a", "/digest")
    assert [request.path for request in http_server.requests] == ["/api/chats/a/message", "/api/chats/a/message"]
    body = http_server.requests[0].body
    assert body is not None and body["message"] == "/digest"
    with pytest.raises(ChatAppError, match="the chat moved on"):
        chat_app.send_message("b", "/digest")


def test_the_agents_newest_message_after_the_cursor_is_the_answer(
    tmp_path: Path, http_server: FakeHttpServer, clock: FakeClock
) -> None:
    http_server.answer("GET", "/api/chats/a/events?limit=1", (200, {"events": [{"event_id": "e9"}]}))
    http_server.answer(
        "GET",
        "/api/chats/a/events?after=e9&limit=200",
        (
            200,
            {
                "events": [
                    {"type": "assistant_message", "text": "first"},
                    {"type": "tool_use", "text": "x"},
                    {"type": "assistant_message", "text": "Done."},
                ]
            },
        ),
    )
    chat_app = _chat_app(tmp_path, http_server, clock)
    assert chat_app.latest_event_id("a") == "e9"
    assert chat_app.assistant_text_after("a", "e9") == "Done."


def test_a_cursor_a_cleared_chat_no_longer_has_falls_back_to_the_tail(
    tmp_path: Path, http_server: FakeHttpServer, clock: FakeClock
) -> None:
    http_server.answer("GET", "/api/chats/a/events?after=gone&limit=200", (404, {"detail": "no such event"}))
    http_server.answer(
        "GET", "/api/chats/a/events?limit=200", (200, {"events": [{"type": "assistant_message", "text": "Tail."}]})
    )
    assert _chat_app(tmp_path, http_server, clock).assistant_text_after("a", "gone") == "Tail."


def test_an_unreachable_chat_app_is_an_error_not_a_crash(tmp_path: Path, clock: FakeClock) -> None:
    registry = tmp_path / "apps.toml"
    registry.write_text('[[apps]]\nname = "chat"\nurl = "http://127.0.0.1:9"\n')
    chat_app = HttpChatApp(repo_root=tmp_path, registry_path=registry, environ={}, clock=clock)
    with pytest.raises(ChatAppError, match="could not be reached"):
        chat_app.chat_status("a")
