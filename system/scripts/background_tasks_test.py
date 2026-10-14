"""Tests for background_tasks.py: the Claude hooks as ``.claude/settings.json`` wires them, and the
CLI that reads the markers through the chat app or, failing that, the files."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from chat_background_tasks import markers
from chat_background_tasks.listing import AGENTS_PATH
from chat_background_tasks.testing import main_claude_env, runner_task, shell_entry

_CHAT_ID = "agent-0123456789abcdef0123456789abcdef"
_OTHER_CHAT_ID = "agent-fedcba9876543210fedcba9876543210"
_SCRIPT = Path(__file__).parent / "background_tasks.py"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _main_claude_env(work_dir: Path, **extra: str) -> dict[str, str]:
    """The hook's environment, with the marker root the test's own fixture points at."""
    return main_claude_env(
        work_dir,
        _CHAT_ID,
        **{markers.MARKER_ROOT_ENV: os.environ[markers.MARKER_ROOT_ENV], **extra},
    )


def _wired_command(event: str) -> str:
    """The background_tasks.py command ``.claude/settings.json`` runs for ``event``."""
    settings = json.loads((_REPO_ROOT / ".claude" / "settings.json").read_text())
    [command] = [
        hook["command"]
        for matcher in settings["hooks"][event]
        for hook in matcher["hooks"]
        if "background_tasks.py" in hook["command"]
    ]
    return command


def _run_wired_hook(
    event: str, payload: dict[str, Any], env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-c", _wired_command(event)],
        input=json.dumps(payload),
        text=True,
        env=env,
        cwd=_REPO_ROOT,
        capture_output=True,
        check=True,
    )


@pytest.mark.parametrize("source", ["resume", "startup"])
def test_the_wired_claude_hooks_record_a_stop_and_a_restarted_claude_hears_what_it_lost(
    background_task_markers: Path, source: str
) -> None:
    """Runs the hook commands exactly as ``.claude/settings.json`` spells them, as Claude does. A
    resumed session is the same conversation, so Claude is told which of its tasks the restart
    ended (SessionStart's stdout is added to its context); a new one starts clean."""
    old_claude = subprocess.Popen(["sleep", "60"])
    try:
        _run_wired_hook(
            "Stop",
            {"background_tasks": [shell_entry("one", "Build the site")]},
            os.environ | _main_claude_env(_REPO_ROOT, CLAUDE_PID=str(old_claude.pid)),
        )
        [task] = markers.list_live_tasks(background_task_markers, _CHAT_ID)
        assert (task.description, task.pid) == ("Build the site", old_claude.pid)
    finally:
        old_claude.kill()
        old_claude.wait()

    started = _run_wired_hook(
        "SessionStart",
        {"hook_event_name": "SessionStart", "source": source},
        os.environ | _main_claude_env(_REPO_ROOT),
    )

    assert list(markers.chat_dir(background_task_markers, _CHAT_ID).iterdir()) == []
    if source == "resume":
        assert "- Build the site (`tail -f log`)" in started.stdout
    else:
        assert started.stdout == ""


@pytest.mark.parametrize("event", ["Stop", "SessionStart"])
def test_a_wired_claude_hook_whose_script_is_gone_still_exits_0(
    tmp_path: Path, event: str
) -> None:
    """Claude keeps the hooks it started with, so a session can outlive the script (a worktree
    checked out at an older commit). python3 exits 2 on a missing script, and a Stop hook's exit 2
    blocks Claude's stop."""
    env = os.environ | _main_claude_env(tmp_path)

    finished = subprocess.run(
        ["sh", "-c", _wired_command(event)],
        input="{}",
        text=True,
        env=env,
        cwd=tmp_path,
        capture_output=True,
    )

    assert finished.returncode == 0, finished.stderr


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _agents_answer(*agents: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    return 200, {"agents": list(agents)}


def test_list_answers_from_the_chat_app_with_agent_names(
    fake_chat_app: Any, background_task_markers: Path, tmp_path: Path
) -> None:
    marker = runner_task("from-app", "2026-10-08T10:00:00+00:00").to_json()
    fake_chat_app.get_answers[AGENTS_PATH] = _agents_answer(
        {
            "id": "agent-active",
            "name": "lead",
            "state": "WAITING",
            "chat_id": _CHAT_ID,
            "is_busy": True,
            "background_tasks": [marker],
        },
        {
            "id": "agent-idle",
            "name": "other",
            "state": "WAITING",
            "chat_id": "agent-idle",
            "is_busy": False,
            "background_tasks": [],
        },
    )
    # The files disagree; the chat app is the authority while it answers.
    markers.write_marker(
        background_task_markers,
        _OTHER_CHAT_ID,
        runner_task("on-disk", "2026-10-08T10:00:00+00:00"),
    )

    listed = _run_cli("list", "--format", "tsv", cwd=tmp_path)

    assert listed.returncode == 0, listed.stderr
    assert listed.stdout.splitlines() == [f"{_CHAT_ID}\tagent-active\tlead\ttrue\t1"]


def test_is_busy_counts_a_turn_in_flight_the_chat_app_reports(
    fake_chat_app: Any, tmp_path: Path
) -> None:
    fake_chat_app.get_answers[AGENTS_PATH] = _agents_answer(
        {
            "id": _CHAT_ID,
            "name": "lead",
            "state": "RUNNING",
            "chat_id": _CHAT_ID,
            "is_busy": True,
            "background_tasks": [],
        },
    )

    assert _run_cli("is-busy", _CHAT_ID, cwd=tmp_path).returncode == 0
    assert _run_cli("is-busy", _OTHER_CHAT_ID, cwd=tmp_path).returncode == 1


def test_a_chat_app_from_before_the_busy_fields_falls_back_to_the_files(
    fake_chat_app: Any, background_task_markers: Path, tmp_path: Path
) -> None:
    fake_chat_app.get_answers[AGENTS_PATH] = _agents_answer(
        {"id": _CHAT_ID, "name": "lead", "state": "WAITING"}
    )
    markers.write_marker(
        background_task_markers,
        _CHAT_ID,
        runner_task("on-disk", "2026-10-08T10:00:00+00:00"),
    )

    listed = _run_cli("list", cwd=tmp_path)

    assert listed.returncode == 0, listed.stderr
    answer = json.loads(listed.stdout)
    assert answer["source"] == "files"
    [chat] = answer["chats"]
    assert (chat["chat_id"], chat["active_agent_id"], chat["active_agent_name"]) == (
        _CHAT_ID,
        _CHAT_ID,
        "",
    )
    assert [task["id"] for task in chat["background_tasks"]] == ["on-disk"]
    assert _run_cli("is-busy", _CHAT_ID, cwd=tmp_path).returncode == 0


def test_an_unreachable_chat_app_falls_back_to_the_files(
    background_task_markers: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = tmp_path / "apps.toml"
    # A port nothing listens on: bind one, then let it go.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    registry.write_text(f'[[apps]]\nname = "chat"\nurl = "http://127.0.0.1:{port}"\n')
    monkeypatch.setenv("MINDS_APPS_FILE", str(registry))
    markers.write_marker(
        background_task_markers,
        _CHAT_ID,
        runner_task("on-disk", "2026-10-08T10:00:00+00:00"),
    )

    listed = _run_cli("list", "--chat", _CHAT_ID, "--format", "tsv", cwd=tmp_path)

    assert listed.stdout.splitlines() == [f"{_CHAT_ID}\t{_CHAT_ID}\t\ttrue\t1"]
    assert _run_cli("is-busy", _OTHER_CHAT_ID, cwd=tmp_path).returncode == 1
