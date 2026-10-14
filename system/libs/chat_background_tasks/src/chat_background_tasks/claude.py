"""Claude's background tasks as markers: what its Stop and SessionStart hooks record and clear.

Claude Code hands its Stop hook the session's ``background_tasks`` list. The Stop hook copies the
ones still pending into ``harness-claude-*`` markers, keeping a still-listed task's start time and
removing the ones no longer listed; the SessionStart hook (startup and resume) removes those of a
Claude process that is gone, and on a resume tells Claude which of its tasks the restart ended
(``lost_tasks_notice``), since nothing else will: a rebind, a memory shed's revival and any other
restart of the agent end them silently. Both act only for the agent's main Claude, never a nested one, and
only on that Claude's own markers and dead ones: after a handoff the chat's other agent may be a
live Claude whose markers are its own.

A turn the user interrupts, or one that fails, runs no Stop hook, so its finished tasks would read
as pending until the next Stop or Claude's exit; the chat app removes such a marker once the
transcript reports the task over (``remove_finished_task``).
"""

import subprocess
from collections.abc import Mapping
from pathlib import Path

from chat_background_tasks.markers import (
    BackgroundTask,
    TaskSource,
    chat_dir,
    is_pid_alive,
    is_task_live,
    json_object,
    now_iso,
    own_chat_id,
    process_start_time,
    read_markers,
    remove_marker,
    write_marker,
)

CLAUDE_HARNESS = "claude"
# The ``type`` labels of Claude Code's Stop-hook ``background_tasks`` entries recorded as markers.
CLAUDE_KINDS = ("shell", "monitor", "workflow", "subagent")
# The statuses Claude Code gives a task that is over; an entry with one is not recorded.
CLAUDE_FINISHED_STATUSES = ("completed", "failed", "killed")
# Where mngr records the pid of the claude process that owns an agent, under its state dir.
CLAUDE_MAIN_PID_FILE_NAME = "claude_main_pid"


def is_claude_task(task: BackgroundTask) -> bool:
    return task.source is TaskSource.HARNESS and task.harness == CLAUDE_HARNESS


def hook_chat_id(environ: Mapping[str, str]) -> str:
    """The chat whose Claude markers this hook may write, or '' when it must do nothing.

    Only the agent's main Claude session writes: not mngr's subagent-proxy children, not a
    Claude outside an mngr agent, not a nested Claude started in another directory, and not one
    started in the work dir while the agent's main Claude (the one mngr records as owning the
    agent) is alive. A Claude that does not name its own pid (``CLAUDE_PID``) writes nothing
    either: its markers would have no process to go stale by.
    """
    if environ.get("MNGR_CLAUDE_SUBAGENT_PROXY_CHILD") or not environ.get(
        "MAIN_CLAUDE_SESSION_ID"
    ):
        return ""
    raw_pid = environ.get("CLAUDE_PID", "")
    if not (raw_pid.isdigit() and int(raw_pid) > 0):
        return ""
    project_dir, work_dir = (
        environ.get("CLAUDE_PROJECT_DIR", ""),
        environ.get("MNGR_AGENT_WORK_DIR", ""),
    )
    if (
        not project_dir
        or not work_dir
        or Path(project_dir).resolve() != Path(work_dir).resolve()
    ):
        return ""
    if is_shadowed_by_main_claude(environ, int(raw_pid)):
        return ""
    return own_chat_id(environ)


def hook_claude_pid(environ: Mapping[str, str]) -> int:
    """The Claude process whose exit makes its markers stale: ``CLAUDE_PID``, which Claude Code sets
    for its hooks (a hook's parent is only the shell it runs the hook command through). Call only
    once ``hook_chat_id`` has answered a chat, which checks it."""
    return int(environ["CLAUDE_PID"])


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


def tasks_from_stop_input(
    payload: object,
    pid: int,
    pid_start: str,
    existing: Mapping[str, BackgroundTask],
    started_at: str,
) -> list[BackgroundTask] | None:
    """The Claude markers a Stop input calls for, or None when it carries no task list to copy.

    A task already marked keeps its start time.
    """
    fields = json_object(payload)
    entries = None if fields is None else fields.get("background_tasks")
    if not isinstance(entries, list):
        return None
    tasks: list[BackgroundTask] = []
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
        previous = existing.get(task_id)
        tasks.append(
            BackgroundTask(
                source=TaskSource.HARNESS,
                id=task_id,
                description=description if isinstance(description, str) else "",
                started_at=previous.started_at if previous is not None else started_at,
                pid=pid,
                harness=CLAUDE_HARNESS,
                kind=str(kind),
                command=command if isinstance(command, str) else "",
                pid_start=pid_start,
            )
        )
    return tasks


def is_marker_ours(task: BackgroundTask, pid: int) -> bool:
    """Whether a hook fired by the claude at ``pid`` may remove this Claude marker: its own, or one
    whose claude is gone. A handoff's other agent shares the chat, and its markers stay its own."""
    return task.pid == pid or not is_task_live(task)


def record_stop(root: Path, chat_id: str, payload: object, pid: int) -> None:
    """Make this claude's markers in the chat match the Stop input's task list: write each listed
    task, and remove the ones no longer listed and those whose claude is gone."""
    existing = {
        task.id: task
        for task in read_markers(chat_dir(root, chat_id))
        if is_claude_task(task)
    }
    tasks = tasks_from_stop_input(
        payload, pid, process_start_time(pid), existing, now_iso()
    )
    if tasks is None:
        return
    for task in tasks:
        if existing.get(task.id) != task:
            write_marker(root, chat_id, task)
    listed = {task.id for task in tasks}
    for task_id in existing.keys() - listed:
        if is_marker_ours(existing[task_id], pid):
            remove_finished_task(root, chat_id, task_id)


def clear(root: Path, chat_id: str, pid: int) -> list[BackgroundTask]:
    """Remove the chat's Claude markers a new claude process cannot have, its own and dead ones, and
    return them."""
    removed = [
        task
        for task in read_markers(chat_dir(root, chat_id))
        if is_claude_task(task) and is_marker_ours(task, pid)
    ]
    for task in removed:
        remove_finished_task(root, chat_id, task.id)
    return removed


def lost_tasks_notice(tasks: list[BackgroundTask]) -> str:
    """What a resumed Claude is told of the background tasks its restart ended, which will never
    report; '' when there were none."""
    if not tasks:
        return ""
    lines = [
        "These background tasks of yours were running when this session last stopped. The "
        "restart ended them and they will not report; start again any you still need:"
    ]
    for task in tasks:
        command = f" (`{task.command}`)" if task.command else ""
        lines.append(f"- {task.description or task.id}{command}")
    lines.append(
        "A command you started through run_in_background.py is different: its report, "
        "saying how it ended, still arrives in this chat."
    )
    return "\n".join(lines)


def remove_finished_task(root: Path, chat_id: str, task_id: str) -> None:
    remove_marker(root, chat_id, TaskSource.HARNESS, task_id, CLAUDE_HARNESS)
