import os
from pathlib import Path
from typing import Any

import pytest

from chat_background_tasks import claude, markers
from chat_background_tasks.markers import BackgroundTask, TaskSource
from chat_background_tasks.testing import main_claude_env, runner_task, shell_entry

_CHAT_ID = "agent-0123456789abcdef0123456789abcdef"
_OTHER_CHAT_ID = "agent-fedcba9876543210fedcba9876543210"


def _main_claude_env(work_dir: Path, **extra: str) -> dict[str, str]:
    return main_claude_env(work_dir, _CHAT_ID, **extra)


def _env_with_recorded_main_claude(
    tmp_path: Path, main_pid: int, **extra: str
) -> dict[str, str]:
    state_dir = tmp_path / "agent-state"
    state_dir.mkdir(exist_ok=True)
    (state_dir / claude.CLAUDE_MAIN_PID_FILE_NAME).write_text(f"{main_pid}\n")
    return _main_claude_env(tmp_path, MNGR_AGENT_STATE_DIR=str(state_dir), **extra)


def _stop(root: Path, env: dict[str, str], *entries: dict[str, Any]) -> None:
    """What the Stop hook does with ``env`` and a Stop input listing ``entries``."""
    chat_id = claude.hook_chat_id(env)
    if chat_id:
        claude.record_stop(
            root,
            chat_id,
            {"background_tasks": list(entries)},
            claude.hook_claude_pid(env),
        )


def _clear(root: Path, env: dict[str, str]) -> None:
    """What the SessionStart hook does with ``env``."""
    chat_id = claude.hook_chat_id(env)
    if chat_id:
        claude.clear(root, chat_id, claude.hook_claude_pid(env))


def _live_ids(root: Path, chat_id: str = _CHAT_ID) -> list[str]:
    return [task.id for task in markers.list_live_tasks(root, chat_id)]


def test_a_stop_records_every_waking_kind_and_skips_the_rest(
    marker_root: Path, tmp_path: Path
) -> None:
    _stop(
        marker_root,
        _main_claude_env(tmp_path),
        shell_entry("shell-1"),
        {"id": "monitor-1", "type": "monitor", "description": "watch CI"},
        {"id": "workflow-1", "type": "workflow", "description": "review"},
        {"id": "agent-1", "type": "subagent", "description": "explore"},
        {"id": "cloud-1", "type": "cloud session", "description": "elsewhere"},
        {"type": "shell", "description": "no id"},
    )

    live = markers.list_live_tasks(marker_root, _CHAT_ID)
    assert {(task.id, task.kind) for task in live} == {
        ("shell-1", "shell"),
        ("monitor-1", "monitor"),
        ("workflow-1", "workflow"),
        ("agent-1", "subagent"),
    }
    assert all(claude.is_claude_task(task) and task.pid == os.getpid() for task in live)
    [shell] = [task for task in live if task.id == "shell-1"]
    assert (shell.description, shell.command) == ("tail logs", "tail -f log")


def test_a_later_stop_keeps_a_listed_tasks_start_and_prunes_the_unlisted_ones(
    marker_root: Path, tmp_path: Path
) -> None:
    env = _main_claude_env(tmp_path)
    _stop(marker_root, env, shell_entry("kept"), shell_entry("done"))
    [kept_before] = [
        task
        for task in markers.list_live_tasks(marker_root, _CHAT_ID)
        if task.id == "kept"
    ]
    markers.write_marker(
        marker_root, _CHAT_ID, runner_task("runner", "2026-10-08T10:00:00+00:00")
    )
    # Its start is backdated, so a rewrite with a fresh start would show.
    markers.write_marker(
        marker_root,
        _CHAT_ID,
        kept_before._replace(started_at="2026-10-08T09:00:00+00:00"),
    )

    _stop(marker_root, env, shell_entry("kept"))

    live = {task.id: task for task in markers.list_live_tasks(marker_root, _CHAT_ID)}
    assert set(live) == {"kept", "runner"}
    assert live["kept"].started_at == "2026-10-08T09:00:00+00:00"


@pytest.mark.parametrize("payload", [{"hook_event_name": "Stop"}, "not an object"])
def test_a_stop_with_no_task_list_leaves_the_markers_alone(
    marker_root: Path, tmp_path: Path, payload: object
) -> None:
    env = _main_claude_env(tmp_path)
    _stop(marker_root, env, shell_entry("one"))

    claude.record_stop(marker_root, _CHAT_ID, payload, claude.hook_claude_pid(env))

    assert _live_ids(marker_root) == ["one"]


def test_clearing_removes_only_the_claude_markers(
    marker_root: Path, tmp_path: Path
) -> None:
    env = _main_claude_env(tmp_path)
    _stop(marker_root, env, shell_entry("one"))
    markers.write_marker(
        marker_root, _CHAT_ID, runner_task("runner", "2026-10-08T10:00:00+00:00")
    )

    _clear(marker_root, env)

    assert [task.source for task in markers.list_live_tasks(marker_root, _CHAT_ID)] == [
        TaskSource.RUN_IN_BACKGROUND
    ]


@pytest.mark.parametrize(
    "overrides",
    [
        {"MNGR_CLAUDE_SUBAGENT_PROXY_CHILD": "1"},
        {"MAIN_CLAUDE_SESSION_ID": ""},
        {"CLAUDE_PROJECT_DIR": "/somewhere/else"},
        {"MNGR_AGENT_ID": ""},
        {"CLAUDE_PID": ""},
    ],
    ids=[
        "subagent-proxy-child",
        "no-main-session",
        "other-project-dir",
        "not-an-agent",
        "no-claude-pid",
    ],
)
def test_a_claude_that_is_not_the_agents_main_session_writes_nothing(
    tmp_path: Path, overrides: dict[str, str]
) -> None:
    assert claude.hook_chat_id(_main_claude_env(tmp_path) | overrides) == ""


def test_the_chat_app_stamped_chat_id_keys_the_claude_markers(
    marker_root: Path, tmp_path: Path
) -> None:
    _stop(
        marker_root,
        _main_claude_env(tmp_path, MINDS_CHAT_ID=_OTHER_CHAT_ID),
        shell_entry("one"),
    )

    assert markers.is_busy(marker_root, _OTHER_CHAT_ID)
    assert not markers.is_busy(marker_root, _CHAT_ID)


def test_a_nested_claude_neither_records_nor_clears_while_the_main_claude_lives(
    marker_root: Path, tmp_path: Path, live_claude_pid: int
) -> None:
    _stop(
        marker_root,
        _main_claude_env(tmp_path, CLAUDE_PID=str(live_claude_pid)),
        shell_entry("main-task"),
    )
    nested_env = _env_with_recorded_main_claude(tmp_path, live_claude_pid)

    _clear(marker_root, nested_env)
    _stop(marker_root, nested_env, shell_entry("nested-task"))

    assert _live_ids(marker_root) == ["main-task"]


@pytest.mark.parametrize("owner", ["exited", "not-claude"])
def test_a_recorded_main_claude_that_is_gone_does_not_block_its_successor(
    marker_root: Path, tmp_path: Path, exited_pid: int, live_other_pid: int, owner: str
) -> None:
    recorded = exited_pid if owner == "exited" else live_other_pid

    _stop(
        marker_root,
        _env_with_recorded_main_claude(tmp_path, recorded),
        shell_entry("one"),
    )

    assert markers.is_busy(marker_root, _CHAT_ID)


def test_a_stop_leaves_another_live_claudes_markers_and_prunes_dead_ones(
    marker_root: Path, tmp_path: Path, live_claude_pid: int, exited_pid: int
) -> None:
    for task_id, pid in (("successor", live_claude_pid), ("gone", exited_pid)):
        markers.write_marker(
            marker_root,
            _CHAT_ID,
            BackgroundTask(
                source=TaskSource.HARNESS,
                id=task_id,
                description="",
                started_at="2026-10-08T09:00:00+00:00",
                pid=pid,
                harness=claude.CLAUDE_HARNESS,
            ),
        )

    _stop(marker_root, _main_claude_env(tmp_path))

    assert [
        task.id
        for task in markers.read_markers(markers.chat_dir(marker_root, _CHAT_ID))
    ] == ["successor"]


def test_a_stop_does_not_record_a_task_it_lists_as_over(
    marker_root: Path, tmp_path: Path
) -> None:
    _stop(
        marker_root,
        _main_claude_env(tmp_path),
        shell_entry("running"),
        {**shell_entry("completed"), "status": "completed"},
        {**shell_entry("killed"), "status": "killed"},
    )

    assert _live_ids(marker_root) == ["running"]
