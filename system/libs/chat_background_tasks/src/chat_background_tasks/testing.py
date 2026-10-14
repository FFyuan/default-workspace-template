"""Shared helpers for the tests of the background-task markers and of the CLI and hooks over them."""

import os
from pathlib import Path
from typing import Any

from chat_background_tasks.markers import BackgroundTask, TaskSource


def main_claude_env(work_dir: Path, chat_id: str, **extra: str) -> dict[str, str]:
    """The environment of an agent's main Claude, whose hooks may write: this test process is its Claude."""
    return {
        "MAIN_CLAUDE_SESSION_ID": "session-1",
        "MNGR_AGENT_ID": chat_id,
        "MNGR_AGENT_WORK_DIR": str(work_dir),
        "CLAUDE_PROJECT_DIR": str(work_dir),
        "CLAUDE_PID": str(os.getpid()),
        **extra,
    }


def shell_entry(task_id: str, description: str = "tail logs") -> dict[str, Any]:
    """One running shell task as Claude Code lists it in a Stop input's ``background_tasks``."""
    return {
        "id": task_id,
        "type": "shell",
        "status": "running",
        "description": description,
        "command": "tail -f log",
    }


def runner_task(
    task_id: str, started_at: str, pid: int | None = None
) -> BackgroundTask:
    """A ``run_in_background`` task, kept live by this test process unless ``pid`` names another."""
    return BackgroundTask(
        source=TaskSource.RUN_IN_BACKGROUND,
        id=task_id,
        description=f"Task {task_id}",
        started_at=started_at,
        pid=os.getpid() if pid is None else pid,
    )
