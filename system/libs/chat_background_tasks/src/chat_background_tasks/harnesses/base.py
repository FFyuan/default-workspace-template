"""What a harness's hooks do with its own background tasks, and what each harness supplies to them.

A harness whose hooks are handed its pending background tasks records them as
``harness-<harness>-*`` markers. Its turn-end hook makes the chat's markers match the list it is
handed, keeping a still-listed task's start time and removing the ones no longer listed; its
session-start hook removes those of a harness process that is gone, and on a resume tells the
agent which of its tasks the restart ended (``lost_tasks_notice``), since nothing else will: a
rebind, a memory shed's revival and any other restart of the agent end them silently. Both act
only for the agent's main harness process, and only on that process's own markers and dead ones:
after a handoff the chat's other agent may be a live process whose markers are its own.

A ``HarnessTaskHooks`` subclass supplies what differs per harness: which process a hook speaks
for, the shape of the task list it is handed, and how a resume is told apart.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple

from chat_background_tasks.markers import (
    BackgroundTask,
    TaskSource,
    chat_dir,
    is_task_live,
    now_iso,
    process_start_time,
    read_markers,
    remove_marker,
    write_marker,
)


class HookCaller(NamedTuple):
    """The chat a hook writes markers in, and the harness process whose exit makes them stale."""

    chat_id: str
    pid: int


class PendingTask(NamedTuple):
    """One task still pending in the list a harness hands its turn-end hook."""

    id: str
    # The harness's own type for the task.
    kind: str
    description: str
    command: str


class HarnessTaskHooks(ABC):
    """One harness's hooks over the markers of its own background tasks."""

    @property
    @abstractmethod
    def harness(self) -> str:
        """The harness's name, as its markers record it."""

    @abstractmethod
    def hook_caller(self, environ: Mapping[str, str]) -> HookCaller | None:
        """The chat and process a hook run with ``environ`` speaks for, or None when it must do nothing."""

    @abstractmethod
    def pending_tasks(self, payload: object) -> list[PendingTask] | None:
        """The pending tasks a turn-end hook's input lists, or None when it carries no task list."""

    @abstractmethod
    def is_resume(self, payload: object) -> bool:
        """Whether a session-start hook's input starts an earlier session again."""

    def is_harness_task(self, task: BackgroundTask) -> bool:
        return task.source is TaskSource.HARNESS and task.harness == self.harness

    def record_turn_end(self, root: Path, caller: HookCaller, payload: object) -> None:
        """Make the caller's markers in its chat match the input's task list: write each listed
        task, and remove the ones no longer listed and those whose process is gone."""
        pending = self.pending_tasks(payload)
        if pending is None:
            return
        existing = {
            task.id: task
            for task in read_markers(chat_dir(root, caller.chat_id))
            if self.is_harness_task(task)
        }
        started_at, pid_start = now_iso(), process_start_time(caller.pid)
        for entry in pending:
            previous = existing.get(entry.id)
            task = BackgroundTask(
                source=TaskSource.HARNESS,
                id=entry.id,
                description=entry.description,
                started_at=previous.started_at if previous is not None else started_at,
                pid=caller.pid,
                harness=self.harness,
                kind=entry.kind,
                command=entry.command,
                pid_start=pid_start,
            )
            if previous != task:
                write_marker(root, caller.chat_id, task)
        listed = {entry.id for entry in pending}
        for task_id in existing.keys() - listed:
            if is_marker_ours(existing[task_id], caller.pid):
                self.remove_task(root, caller.chat_id, task_id)

    def clear(self, root: Path, caller: HookCaller) -> list[BackgroundTask]:
        """Remove the chat's markers a new harness process cannot have, its own and dead ones, and
        return them."""
        removed = [
            task
            for task in read_markers(chat_dir(root, caller.chat_id))
            if self.is_harness_task(task) and is_marker_ours(task, caller.pid)
        ]
        for task in removed:
            self.remove_task(root, caller.chat_id, task.id)
        return removed

    def remove_task(self, root: Path, chat_id: str, task_id: str) -> None:
        remove_marker(root, chat_id, TaskSource.HARNESS, task_id, self.harness)


def is_marker_ours(task: BackgroundTask, pid: int) -> bool:
    """Whether a hook fired by the harness process at ``pid`` may remove this marker: its own, or one
    whose process is gone. A handoff's other agent shares the chat, and its markers stay its own."""
    return task.pid == pid or not is_task_live(task)


def lost_tasks_notice(tasks: list[BackgroundTask]) -> str:
    """What a resumed agent is told of the background tasks its restart ended, which will never
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
