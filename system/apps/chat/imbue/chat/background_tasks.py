"""The background tasks each chat waits on, read from the markers ``chat_background_tasks`` owns.

A chat is busy when its agent will resume on its own: its active agent has a turn in flight, or
its chat has a pending background task, whose completion starts one. Only the chat app knows the
first (the ``system/scripts/background_tasks.py`` CLI's file fallback, used when the app cannot
answer, sees the tasks alone). The pending tasks are one marker file each under
``<chat data dir>/background_tasks/<chat-id>/``, written by ``run_in_background.py`` and by a
harness's hooks. This module wraps what the library reads in this app's types.
"""

from pathlib import Path
from typing import Final

from chat_background_tasks import claude as claude_tasks
from chat_background_tasks import markers
from chat_background_tasks.markers import TaskSource
from loguru import logger
from pydantic import Field

from imbue.chat.primitives import ChatId
from imbue.imbue_common.frozen_model import FrozenModel

# The markers' root under the chat's data dir; the library's default and the agents'
# ``MINDS_BACKGROUND_TASKS_DIR`` name the same directory.
BACKGROUND_TASKS_DIRNAME: Final[str] = "background_tasks"


class BackgroundTask(FrozenModel):
    """One pending task: a live marker, in the shape the library writes it."""

    source: TaskSource = Field(
        description="Who recorded it: run_in_background (a command whose runner outlives the agent and reports how "
        "it ended to the chat), or harness (one of the harness's own tasks, which ends with the agent's process, "
        "unreported)"
    )
    id: str = Field(description="The task's id within its source")
    description: str = Field(description="What the task is, as its writer described it")
    started_at: str = Field(
        description="When the task started (ISO 8601, UTC); for a Claude task, when its Stop hook first recorded "
        "it, at the end of the turn that started it"
    )
    pid: int = Field(description="The process whose exit makes the marker stale")
    harness: str = Field(default="", description="The harness that recorded a harness task; '' otherwise")
    kind: str = Field(default="", description="The harness's type for a harness task; '' otherwise")
    command: str = Field(default="", description="The command a harness task runs, when it has one")
    pid_start: str = Field(
        default="", description="The pid's process start time, so a recycled pid cannot keep the marker live"
    )


class BackgroundTaskReader(FrozenModel):
    """Reads one chat's live tasks from the marker root."""

    root: Path = Field(description="The marker root: one directory per chat beneath it")

    def chat_dir(self, chat_id: ChatId) -> Path:
        """The directory a chat's markers are written to, which need not exist."""
        return markers.chat_dir(self.root, str(chat_id))

    def live_tasks(self, chat_id: ChatId) -> tuple[BackgroundTask, ...]:
        """The chat's tasks whose pid is alive, oldest first; malformed and stale markers are skipped."""
        return tuple(BackgroundTask(**task._asdict()) for task in markers.live_tasks_in(self.chat_dir(chat_id)))

    def remove_claude_tasks(self, chat_id: ChatId, task_ids: tuple[str, ...]) -> None:
        """Remove the chat's markers for these Claude tasks, which Claude has reported as over."""
        for task_id in task_ids:
            claude_tasks.remove_finished_task(self.root, str(chat_id), task_id)

    def create_root(self) -> None:
        """Create the marker root, so the shell's avatar, which watches it only once it exists, sees the first task
        as it lands."""
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning("Could not create the background task marker root {}: {}", self.root, e)
