"""Tests for run_job.sh, the completion-tracked recurring-job runner.

The script is exercised as a real subprocess with its documented test hooks:
``MINDS_JOB_STATE_DIR`` roots the state under tmp_path and
``MINDS_JOB_NOW_EPOCH`` / ``MINDS_JOB_NOW_HOUR`` pin the clock, so every
due/catch-up/retry decision is deterministic. The wrapped command is a tiny
bash snippet that records its invocations to a marker file.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_SCRIPT = Path(__file__).parent / "run_job.sh"

_DAY = 86400
_BASE_NOW = 1_700_000_000


def _run(
    tmp_path: Path,
    *args: str,
    now: int = _BASE_NOW,
    hour: int = 12,
    command: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    marker = tmp_path / "ran"
    default_command = ["bash", "-c", f"echo run >> {marker}"]
    return subprocess.run(
        ["bash", str(_SCRIPT), "job", *args, *(command or default_command)],
        env={
            "PATH": "/usr/bin:/bin",
            "MINDS_JOB_STATE_DIR": str(tmp_path / "state"),
            "MINDS_JOB_NOW_EPOCH": str(now),
            "MINDS_JOB_NOW_HOUR": str(hour),
        },
        capture_output=True,
        text=True,
        check=False,
    )


def _runs(tmp_path: Path) -> int:
    marker = tmp_path / "ran"
    if not marker.exists():
        return 0
    return len(marker.read_text().splitlines())


def _state(tmp_path: Path, name: str) -> str | None:
    path = tmp_path / "state" / "job" / name
    if not path.exists():
        return None
    return path.read_text().strip()


def test_first_run_fires_and_records_completion(tmp_path: Path) -> None:
    result = _run(tmp_path, "--every", "7d")
    assert result.returncode == 0, result.stderr
    assert _runs(tmp_path) == 1
    assert _state(tmp_path, "last_attempt") == str(_BASE_NOW)
    assert _state(tmp_path, "last_success") == str(_BASE_NOW)


def test_first_run_waits_for_due_hour(tmp_path: Path) -> None:
    assert _run(tmp_path, "--every", "7d", "--at", "3", hour=1).returncode == 0
    assert _runs(tmp_path) == 0
    assert _run(tmp_path, "--every", "7d", "--at", "3", hour=3).returncode == 0
    assert _runs(tmp_path) == 1


def test_covered_window_is_silent(tmp_path: Path) -> None:
    _run(tmp_path, "--every", "7d")
    result = _run(tmp_path, "--every", "7d", now=_BASE_NOW + 6 * _DAY)
    assert result.returncode == 0
    assert _runs(tmp_path) == 1


def test_due_again_after_interval(tmp_path: Path) -> None:
    _run(tmp_path, "--every", "7d")
    _run(tmp_path, "--every", "7d", now=_BASE_NOW + 7 * _DAY)
    assert _runs(tmp_path) == 2


def test_sub_daily_interval(tmp_path: Path) -> None:
    _run(tmp_path, "--every", "15m")
    _run(tmp_path, "--every", "15m", now=_BASE_NOW + 14 * 60)
    assert _runs(tmp_path) == 1
    _run(tmp_path, "--every", "15m", now=_BASE_NOW + 15 * 60)
    assert _runs(tmp_path) == 2


def test_due_day_waits_for_hour_but_extra_day_fires_any_hour(tmp_path: Path) -> None:
    _run(tmp_path, "--every", "7d", "--at", "3", hour=3)
    assert _runs(tmp_path) == 1
    # Due day, before 3 AM: wait.
    _run(tmp_path, "--every", "7d", "--at", "3", now=_BASE_NOW + 7 * _DAY, hour=0)
    assert _runs(tmp_path) == 1
    # A whole extra day missed: fire the first minute back, whatever the hour.
    _run(tmp_path, "--every", "7d", "--at", "3", now=_BASE_NOW + 8 * _DAY, hour=0)
    assert _runs(tmp_path) == 2


def test_failed_run_leaves_window_uncovered_and_retries_after_gap(
    tmp_path: Path,
) -> None:
    failing = ["bash", "-c", "exit 1"]
    result = _run(tmp_path, "--every", "7d", command=failing)
    assert result.returncode == 1
    assert _state(tmp_path, "last_success") is None
    assert _state(tmp_path, "failures") == "1"
    # Within the retry gap: silent skip.
    _run(tmp_path, "--every", "7d", now=_BASE_NOW + 60)
    assert _runs(tmp_path) == 0
    # Past the gap: retried; success clears the failure counter.
    _run(tmp_path, "--every", "7d", now=_BASE_NOW + 120)
    assert _runs(tmp_path) == 1
    assert _state(tmp_path, "failures") is None
    assert _state(tmp_path, "last_success") == str(_BASE_NOW + 120)


def test_killed_run_is_detected_and_retried(tmp_path: Path) -> None:
    # A run that died mid-flight leaves last_attempt with no last_success --
    # seed that state directly, as a crash would.
    state = tmp_path / "state" / "job"
    state.mkdir(parents=True)
    (state / "last_attempt").write_text(f"{_BASE_NOW}\n")
    _run(tmp_path, "--every", "7d", now=_BASE_NOW + 120)
    assert _runs(tmp_path) == 1


def test_repeated_failure_escalates(tmp_path: Path) -> None:
    failing = ["bash", "-c", "exit 1"]
    _run(tmp_path, "--every", "7d", command=failing)
    _run(tmp_path, "--every", "7d", now=_BASE_NOW + 120, command=failing)
    result = _run(tmp_path, "--every", "7d", now=_BASE_NOW + 240, command=failing)
    assert _state(tmp_path, "failures") == "3"
    assert "3 consecutive attempts" in result.stdout


def test_custom_retry_gap(tmp_path: Path) -> None:
    failing = ["bash", "-c", "exit 1"]
    _run(tmp_path, "--every", "7d", "--retry-after", "1h", command=failing)
    _run(tmp_path, "--every", "7d", "--retry-after", "1h", now=_BASE_NOW + 59 * 60)
    assert _runs(tmp_path) == 0
    _run(tmp_path, "--every", "7d", "--retry-after", "1h", now=_BASE_NOW + 60 * 60)
    assert _runs(tmp_path) == 1


_GRACE = ("--every", "1h", "--wake-grace", "10m")


def _tick_each_minute(tmp_path: Path, start: int, minutes: int) -> None:
    """Tick the way cron does, once a minute, ``minutes`` times from ``start``."""
    for minute in range(minutes):
        _run(tmp_path, *_GRACE, now=start + minute * 60)


def test_wake_grace_holds_the_first_run_after_a_fresh_start(tmp_path: Path) -> None:
    # No tick has been recorded yet, which is what a new workspace looks like.
    _tick_each_minute(tmp_path, _BASE_NOW, 10)
    assert _runs(tmp_path) == 0
    _run(tmp_path, *_GRACE, now=_BASE_NOW + 10 * 60)
    assert _runs(tmp_path) == 1


def test_wake_grace_holds_a_catch_up_run_after_the_machine_slept(
    tmp_path: Path,
) -> None:
    _tick_each_minute(tmp_path, _BASE_NOW, 11)
    assert _runs(tmp_path) == 1
    woke = _BASE_NOW + 10 * 60 + 3 * 3600

    _tick_each_minute(tmp_path, woke, 10)
    assert _runs(tmp_path) == 1
    _run(tmp_path, *_GRACE, now=woke + 10 * 60)
    assert _runs(tmp_path) == 2


def test_wake_grace_does_not_hold_a_run_that_comes_due_while_awake(
    tmp_path: Path,
) -> None:
    _tick_each_minute(tmp_path, _BASE_NOW, 71)
    assert _runs(tmp_path) == 2


def test_overlapping_tick_skips_while_lock_held(tmp_path: Path) -> None:
    import fcntl
    import shutil

    import pytest

    if shutil.which("flock") is None:
        pytest.skip(
            "flock(1) not available (macOS); overlap protection is container-only"
        )

    state = tmp_path / "state" / "job"
    state.mkdir(parents=True)
    lock = open(state / "lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        result = _run(tmp_path, "--every", "7d")
        assert result.returncode == 0
        assert _runs(tmp_path) == 0
    finally:
        lock.close()


def test_lock_fd_is_closed_for_the_command(tmp_path: Path) -> None:
    # A daemon the command starts must not inherit the lock fd; prove the
    # command itself cannot see fd 9.
    probe = ["bash", "-c", "! { true >&9; } 2>/dev/null"]
    result = _run(tmp_path, "--every", "7d", command=probe)
    assert result.returncode == 0, result.stderr
    assert _state(tmp_path, "last_success") is not None


def _run_in_workspace(workspace: Path, now: int = _BASE_NOW) -> subprocess.CompletedProcess[str]:
    """Run a copy of the runner placed in ``workspace``, with its default state root."""
    script = workspace / "system" / "libs" / "automations" / "run_job.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(_SCRIPT.read_text())
    return subprocess.run(
        [
            "bash",
            str(script),
            "job",
            "--every",
            "1h",
            "bash",
            "-c",
            f"echo run >> {workspace / 'ran'}",
        ],
        env={"PATH": "/usr/bin:/bin", "MINDS_JOB_NOW_EPOCH": str(now)},
        capture_output=True,
        text=True,
        check=False,
    )


def test_state_lives_under_the_workspaces_data_dir(tmp_path: Path) -> None:
    result = _run_in_workspace(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "data" / ".state" / "jobs" / "job" / "last_success").is_file()


def test_state_left_under_system_data_is_moved_into_place(tmp_path: Path) -> None:
    legacy = tmp_path / "system" / "data" / ".state" / "jobs" / "job"
    legacy.mkdir(parents=True)
    (legacy / "last_success").write_text(f"{_BASE_NOW}\n")

    result = _run_in_workspace(tmp_path, now=_BASE_NOW + 60)

    assert result.returncode == 0, result.stderr
    assert _runs(tmp_path) == 0
    assert (
        tmp_path / "data" / ".state" / "jobs" / "job" / "last_success"
    ).read_text() == f"{_BASE_NOW}\n"
    assert not (tmp_path / "system" / "data").exists()


def test_state_left_under_system_data_is_dropped_once_the_job_has_its_own(
    tmp_path: Path,
) -> None:
    _run_in_workspace(tmp_path)
    (tmp_path / "system" / "data" / ".state" / "jobs" / "job").mkdir(parents=True)

    result = _run_in_workspace(tmp_path, now=_BASE_NOW + 60)

    assert result.returncode == 0, result.stderr
    assert _runs(tmp_path) == 1
    assert not (tmp_path / "system" / "data").exists()


def test_bad_duration_is_a_usage_error(tmp_path: Path) -> None:
    result = _run(tmp_path, "--every", "7x")
    assert result.returncode == 2
    assert "bad duration" in result.stderr


def test_missing_arguments_are_a_usage_error(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(_SCRIPT), "job", "--every", "7d"],
        env={"PATH": "/usr/bin:/bin", "MINDS_JOB_STATE_DIR": str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "usage:" in result.stderr
