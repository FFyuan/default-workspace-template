"""Claude's adapter for the background-task hooks (``base``).

Claude Code hands its Stop hook the session's ``background_tasks`` list, and its SessionStart hook
a ``source`` saying whether the session is a resume. Only the agent's main Claude writes, never a
nested one.

A turn the user interrupts, or one that fails, runs no Stop hook, so its finished tasks would read
as pending until the next Stop or Claude's exit; the chat app removes such a marker once the
transcript reports the task over.
"""

import subprocess
from collections.abc import Mapping
from pathlib import Path

from chat_background_tasks.harnesses.base import (
    HarnessTaskHooks,
    HookCaller,
    PendingTask,
)
from chat_background_tasks.markers import is_pid_alive, json_object, own_chat_id

CLAUDE_HARNESS = "claude"
# The ``type`` labels of Claude Code's Stop-hook ``background_tasks`` entries recorded as markers.
CLAUDE_KINDS = ("shell", "monitor", "workflow", "subagent")
# The statuses Claude Code gives a task that is over; an entry with one is not recorded.
CLAUDE_FINISHED_STATUSES = ("completed", "failed", "killed")
# Where mngr records the pid of the claude process that owns an agent, under its state dir.
CLAUDE_MAIN_PID_FILE_NAME = "claude_main_pid"


class ClaudeTaskHooks(HarnessTaskHooks):
    @property
    def harness(self) -> str:
        return CLAUDE_HARNESS

    def hook_caller(self, environ: Mapping[str, str]) -> HookCaller | None:
        """Only the agent's main Claude session writes: not mngr's subagent-proxy children, not a
        Claude outside an mngr agent, not a nested Claude started in another directory, and not one
        started in the work dir while the agent's main Claude (the one mngr records as owning the
        agent) is alive. A Claude that does not name its own pid (``CLAUDE_PID``, which Claude Code
        sets for its hooks, whose parent is only the shell running the hook command) writes nothing
        either: its markers would have no process to go stale by.
        """
        if environ.get("MNGR_CLAUDE_SUBAGENT_PROXY_CHILD") or not environ.get(
            "MAIN_CLAUDE_SESSION_ID"
        ):
            return None
        raw_pid = environ.get("CLAUDE_PID", "")
        if not (raw_pid.isdigit() and int(raw_pid) > 0):
            return None
        project_dir, work_dir = (
            environ.get("CLAUDE_PROJECT_DIR", ""),
            environ.get("MNGR_AGENT_WORK_DIR", ""),
        )
        if (
            not project_dir
            or not work_dir
            or Path(project_dir).resolve() != Path(work_dir).resolve()
        ):
            return None
        pid = int(raw_pid)
        chat_id = own_chat_id(environ)
        if not chat_id or is_shadowed_by_main_claude(environ, pid):
            return None
        return HookCaller(chat_id=chat_id, pid=pid)

    def pending_tasks(self, payload: object) -> list[PendingTask] | None:
        fields = json_object(payload)
        entries = None if fields is None else fields.get("background_tasks")
        if not isinstance(entries, list):
            return None
        pending: list[PendingTask] = []
        for raw_entry in entries:
            entry = json_object(raw_entry)
            if entry is None:
                continue
            task_id, kind = entry.get("id"), entry.get("type")
            if not isinstance(task_id, str) or not task_id or kind not in CLAUDE_KINDS:
                continue
            if entry.get("status") in CLAUDE_FINISHED_STATUSES:
                continue
            description, command = entry.get("description"), entry.get("command")
            pending.append(
                PendingTask(
                    id=task_id,
                    kind=str(kind),
                    description=description if isinstance(description, str) else "",
                    command=command if isinstance(command, str) else "",
                )
            )
        return pending

    def is_resume(self, payload: object) -> bool:
        fields = json_object(payload)
        return fields is not None and fields.get("source") == "resume"


def recorded_main_claude_pid(environ: Mapping[str, str]) -> int | None:
    """The pid mngr's SessionStart hook recorded as the agent's main claude, or None when there is none."""
    state_dir = environ.get("MNGR_AGENT_STATE_DIR", "")
    if not state_dir:
        return None
    try:
        raw = (
            (Path(state_dir) / CLAUDE_MAIN_PID_FILE_NAME)
            .read_text(encoding="utf-8")
            .strip()
        )
    except OSError:
        return None
    return int(raw) if raw.isdigit() and int(raw) > 0 else None


def process_command_name(pid: int) -> str:
    """The process's executable name as ``ps`` reports it, or '' when it cannot say."""
    try:
        result = subprocess.run(
            ["ps", "-o", "comm=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip()


def is_shadowed_by_main_claude(environ: Mapping[str, str], claude_pid: int) -> bool:
    """Whether another live claude owns the agent, which makes this one a nested claude.

    The same rule as mngr's own hooks: a recorded owner that is dead, or whose pid now holds
    something other than claude, owns nothing, and no record at all lets the hook through.
    """
    main_pid = recorded_main_claude_pid(environ)
    return (
        main_pid is not None
        and main_pid != claude_pid
        and is_pid_alive(main_pid)
        and Path(process_command_name(main_pid)).name == "claude"
    )
