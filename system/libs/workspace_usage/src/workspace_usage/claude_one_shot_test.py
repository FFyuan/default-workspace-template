from pathlib import Path

from workspace_usage.claude_one_shot import (
    build_claude_session_report,
    claude_session_args,
    report_claude_one_shot,
)


def test_session_args_name_the_session() -> None:
    assert claude_session_args("0b4c") == ["--session-id", "0b4c"]


def test_report_carries_the_context_and_purpose() -> None:
    report = build_claude_session_report(
        config_dir=Path("/accounts/a1"),
        session_id="4d2f8e61-9a07-4c3b-b5e8-1f6d0a7c2e93",
        context={"origin_kind": "CHAT", "origin_id": "chat-1"},
        workspace_id="ws-1",
        purpose="CHAT_TITLE",
    )

    assert report == {
        "config_dir": "/accounts/a1",
        "session_id": "4d2f8e61-9a07-4c3b-b5e8-1f6d0a7c2e93",
        "attribution": {
            "workspace_id": "ws-1",
            "origin_kind": "CHAT",
            "origin_id": "chat-1",
            "purpose": "CHAT_TITLE",
        },
        "billing_mode": "UNKNOWN",
        "delete_log": True,
    }


def test_report_without_a_context_uses_the_processes_own(tmp_path: Path) -> None:
    environ = {
        "IMBUE_USAGE_COLLECTOR_URL": "http://127.0.0.1:1",
        "IMBUE_USAGE_DATA_DIR": str(tmp_path),
        "IMBUE_USAGE_CONTEXT": "origin_kind=ROUTINE,origin_id=nightly",
        "MNGR_AGENT_ID": "ws-2",
    }

    assert not report_claude_one_shot(
        Path("/accounts/a1"), "4d2f8e61-9a07-4c3b-b5e8-1f6d0a7c2e93", environ=environ
    )

    [spooled] = (tmp_path / "spool" / "claude-sessions").glob("*.json")
    assert '"origin_kind":"ROUTINE"' in spooled.read_text()
