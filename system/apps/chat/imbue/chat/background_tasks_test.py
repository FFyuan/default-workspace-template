import os
import subprocess
from pathlib import Path

from chat_background_tasks import markers
from chat_background_tasks.markers import TaskSource

from imbue.chat.background_tasks import BACKGROUND_TASKS_DIRNAME
from imbue.chat.background_tasks import BackgroundTask
from imbue.chat.background_tasks import BackgroundTaskReader
from imbue.chat.config import DEFAULT_CHAT_DATA_DIR
from imbue.chat.primitives import ChatId
from imbue.chat.testing import write_background_task_marker


def _dead_pid() -> int:
    process = subprocess.Popen(["true"])
    process.wait()
    return process.pid


def test_the_reader_reads_the_live_markers_the_library_writes(tmp_path: Path) -> None:
    """What the library reads arrives in the app's types: live markers oldest first, a stale one (its pid dead) and
    a malformed one skipped."""
    reader = BackgroundTaskReader(root=tmp_path / "background_tasks")
    chat_id = ChatId("agent-1")
    write_background_task_marker(
        reader, chat_id, "later", os.getpid(), "Watch the logs", "2026-10-08T12:05:00+00:00", harness="claude"
    )
    write_background_task_marker(
        reader, chat_id, "earlier", os.getpid(), "Rebuild the image", "2026-10-08T12:00:00+00:00"
    )
    write_background_task_marker(reader, chat_id, "stale", _dead_pid())
    (reader.chat_dir(chat_id) / "run_in_background-broken.json").write_text("{not json")

    assert reader.live_tasks(chat_id) == (
        BackgroundTask(
            source=TaskSource.RUN_IN_BACKGROUND,
            id="earlier",
            description="Rebuild the image",
            started_at="2026-10-08T12:00:00+00:00",
            pid=os.getpid(),
        ),
        BackgroundTask(
            source=TaskSource.HARNESS,
            id="later",
            description="Watch the logs",
            started_at="2026-10-08T12:05:00+00:00",
            pid=os.getpid(),
            harness="claude",
        ),
    )
    assert reader.live_tasks(ChatId("agent-without-markers")) == ()


def test_the_chat_app_reads_the_marker_root_the_writers_use_by_default() -> None:
    """The writers fall back to the library's default root when ``CHAT_BACKGROUND_TASKS_DIR`` is unset; the chat app
    reads its own data dir's ``background_tasks``. Both are repo-root relative and must name one directory."""
    assert DEFAULT_CHAT_DATA_DIR / BACKGROUND_TASKS_DIRNAME == markers.DEFAULT_MARKER_ROOT


def test_a_dead_runners_marker_is_claimed_once_and_nothing_else_is(tmp_path: Path) -> None:
    """A runner that died before reporting leaves its command's end untold. Its marker is handed to one caller, who
    tells the agent; a live runner's, and a harness's own (which its hooks clear), stay where they are."""
    reader = BackgroundTaskReader(root=tmp_path / "background_tasks")
    chat_id = ChatId("agent-1")
    dead = _dead_pid()
    write_background_task_marker(reader, chat_id, "stopped-later", dead, "Serve the docs", "2026-10-08T12:05:00+00:00")
    write_background_task_marker(reader, chat_id, "stopped", dead, "Build the site", "2026-10-08T12:00:00+00:00")
    write_background_task_marker(reader, chat_id, "running", os.getpid(), "Watch the logs")
    write_background_task_marker(reader, chat_id, "claude-gone", dead, harness="claude")

    claimed = reader.claim_unreported_runner_ends(chat_id)

    assert [(task.id, task.description) for task in claimed] == [
        ("stopped", "Build the site"),
        ("stopped-later", "Serve the docs"),
    ]
    assert reader.claim_unreported_runner_ends(chat_id) == ()
    assert sorted(path.name for path in reader.chat_dir(chat_id).iterdir()) == [
        "harness-claude-claude-gone.json",
        "run_in_background-running.json",
    ]
