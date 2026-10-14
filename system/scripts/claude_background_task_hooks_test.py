"""Tests for claude_background_task_hooks.py: the Stop and SessionStart hooks run exactly as
``.claude/settings.json`` wires them."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from chat_background_tasks import markers
from chat_background_tasks.testing import main_claude_env, shell_entry

_CHAT_ID = "agent-0123456789abcdef0123456789abcdef"
_SCRIPT_NAME = "claude_background_task_hooks.py"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _main_claude_env(work_dir: Path, **extra: str) -> dict[str, str]:
    """The hook's environment, with the marker root the test's own fixture points at."""
    return main_claude_env(
        work_dir,
        _CHAT_ID,
        **{markers.MARKER_ROOT_ENV: os.environ[markers.MARKER_ROOT_ENV], **extra},
    )


def _wired_command(event: str) -> str:
    """The hook command ``.claude/settings.json`` runs for ``event``."""
    settings = json.loads((_REPO_ROOT / ".claude" / "settings.json").read_text())
    [command] = [
        hook["command"]
        for matcher in settings["hooks"][event]
        for hook in matcher["hooks"]
        if _SCRIPT_NAME in hook["command"]
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
