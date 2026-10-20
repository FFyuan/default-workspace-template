import os
from pathlib import Path

import pytest

from routines.chat_app import HttpChatApp
from routines.errors import ChatAppError
from routines.errors import ChatCreateError
from routines.mock_clock_test import FakeClock
from routines.mock_http_server_test import FakeHttpServer
from routines.primitives import ChatStatusWord
from routines.primitives import RoutineId


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


def test_a_status_read_waits_out_a_not_ready_answer_too(
    tmp_path: Path, http_server: FakeHttpServer, clock: FakeClock
) -> None:
    """A chat app that has restarted answers 503 until its agent list is known; a poll is not a refusal then."""
    http_server.answer(
        "GET",
        "/api/chats",
        (503, {"detail": "agent list not known yet"}),
        (200, {"chats": [{"chat_id": "a", "status": "idle"}]}),
    )
    chat_app = _chat_app(tmp_path, http_server, clock)
    assert chat_app.chat_status("a") is ChatStatusWord.IDLE
    assert [request.path for request in http_server.requests] == ["/api/chats", "/api/chats"]


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


def _chat_app_with_fake_uv(tmp_path: Path, clock: FakeClock, script: str) -> tuple[HttpChatApp, Path]:
    """A chat app whose `uv run mngr create` is the given shell script, which can record its argv in ARGV_FILE."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "uv").write_text("#!/bin/sh\n" + script)
    (fake_bin / "uv").chmod(0o755)
    argv_file = tmp_path / "argv"
    environ = {
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
        "ARGV_FILE": str(argv_file),
        "MNGR_HOST_DIR": str(tmp_path / "no-such-host"),
    }
    registry = tmp_path / "apps.toml"
    registry.write_text('[[apps]]\nname = "chat"\nurl = "http://127.0.0.1:9"\n')
    return HttpChatApp(repo_root=tmp_path, registry_path=registry, environ=environ, clock=clock), argv_file


def test_the_chat_is_created_through_mngr_and_named_by_its_created_event(tmp_path: Path, clock: FakeClock) -> None:
    chat_app, argv_file = _chat_app_with_fake_uv(
        tmp_path,
        clock,
        'printf "%s\\n" "$@" > "$ARGV_FILE"\n'
        'echo \'{"event": "progress", "step": "creating"}\'\n'
        'echo \'{"event": "created", "agent_id": "agent-new"}\'\n',
    )

    chat_id = chat_app.create_chat("Morning digest", RoutineId("digest"), "/digest")

    assert chat_id == "agent-new"
    argv = argv_file.read_text().splitlines()
    assert argv[:4] == ["run", "--no-sync", "mngr", "create"]
    assert "--template" in argv and argv[argv.index("--template") + 1] == "automation"
    assert "--label" in argv and "routine=digest" in argv and "display_name=Morning digest" in argv
    assert argv[-2:] == ["--message", "/digest"]


def test_a_create_that_fails_is_refused_with_its_last_line(tmp_path: Path, clock: FakeClock) -> None:
    chat_app, _ = _chat_app_with_fake_uv(
        tmp_path, clock, 'echo "Signing in first." >&2\necho "No provider account is signed in." >&2\nexit 3\n'
    )
    with pytest.raises(ChatCreateError, match="No provider account is signed in"):
        chat_app.create_chat("Morning digest", RoutineId("digest"), "/digest")


def test_a_create_that_names_no_agent_is_refused(tmp_path: Path, clock: FakeClock) -> None:
    chat_app, _ = _chat_app_with_fake_uv(tmp_path, clock, 'echo \'{"event": "progress"}\'\n')
    with pytest.raises(ChatCreateError, match="named no agent"):
        chat_app.create_chat("Morning digest", RoutineId("digest"), "/digest")
