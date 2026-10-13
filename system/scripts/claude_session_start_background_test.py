"""The SessionStart upkeep hook returns at once and leaves its jobs running in the background.

Claude Code takes no prompt until every SessionStart hook exits, so what these pin is
that the hook's own run stays short however slow the jobs are, that the jobs still run
(at a lower CPU priority), that the plugin run is throttled per config dir and project
path, and that the warnings a previous run logged reach the next session's context.
Recording ``claude`` and ``uv`` shims stand in for the real binaries.
"""

import os
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from imbue.mngr.utils.polling import wait_for

_HOOK = Path(__file__).with_name("claude_session_start_background.sh")
_PLUGIN_SCRIPT = Path(__file__).with_name("claude_update_plugin.sh")
_TWO_DAYS_SECONDS = 2 * 24 * 3600
_SLOW_JOB_SECONDS = 3
_HOOK_RETURN_BUDGET_SECONDS = 2.0
# The jobs run at a lower CPU priority on purpose, so a busy machine starves them;
# the waits allow for that, and the module's per-test limit sits above them.
_JOB_WAIT_SECONDS = 30.0

pytestmark = pytest.mark.timeout(_JOB_WAIT_SECONDS * 3)

# Each shim appends "<its niceness> <args>" to $SHIM_LOG after a delay, so a test can
# tell the jobs ran, how they were prioritized, and that the hook did not wait for them.
# The uv shim also prints $UV_STDERR on stderr, as uv prints its own warnings. A call
# whose args start with $SHIM_FAIL_ARGS fails whatever $SHIM_EXIT says.
_SHIM = """#!/usr/bin/env bash
sleep "${SHIM_DELAY:-0}"
niceness=$(python3 -c 'import os; print(os.nice(0))')
printf '%s %s %s\\n' "$(basename "$0")" "$niceness" "$*" >> "$SHIM_LOG"
if [[ "$1 $2" == "plugin marketplace" && "$3" == "list" ]]; then
    printf '  > imbue-code-guardian\\n  > claude-code-plugins\\n'
fi
if [[ "$(basename "$0")" == uv && -n "${UV_STDERR:-}" ]]; then
    printf '%s\\n' "$UV_STDERR" >&2
fi
if [[ -n "${SHIM_FAIL_ARGS:-}" && "$*" == "$SHIM_FAIL_ARGS"* ]]; then
    exit 1
fi
exit "${SHIM_EXIT:-0}"
"""


def _install_shims(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name in ("claude", "uv"):
        shim = bin_dir / name
        shim.write_text(_SHIM)
        shim.chmod(0o755)
    return bin_dir


def _scripts_dir(tmp_path: Path) -> Path:
    """Where the copies sit: ``system/scripts`` under ``tmp_path``, which the hook
    therefore takes as the repo root holding its ``data/.state``."""
    return tmp_path / "system" / "scripts"


def _install_scripts(tmp_path: Path) -> Path:
    """Copy the hook and the plugin script it starts, backdated two days.

    The hook also runs the plugin script when that script is newer than its stamp, so
    the tests run copies whose age they control rather than the checkout's files."""
    scripts_dir = _scripts_dir(tmp_path)
    hook = scripts_dir / _HOOK.name
    if not hook.exists():
        scripts_dir.mkdir(parents=True)
        two_days_ago = time.time() - _TWO_DAYS_SECONDS
        for script in (_HOOK, _PLUGIN_SCRIPT):
            copied = scripts_dir / script.name
            shutil.copy2(script, copied)
            os.utime(copied, (two_days_ago, two_days_ago))
    return hook


def _run_hook(
    tmp_path: Path,
    delay_seconds: int,
    exit_code: int = 0,
    uv_stderr_line: str = "",
    job_timeout_seconds: int = 60,
    failing_args: str = "",
) -> tuple[subprocess.CompletedProcess[str], float]:
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    env = {
        **os.environ,
        "PATH": f"{_install_shims(tmp_path)}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(tmp_path / "home"),
        "CLAUDE_CONFIG_DIR": str(tmp_path / "config"),
        "SHIM_LOG": str(tmp_path / "shim.log"),
        "SHIM_DELAY": str(delay_seconds),
        "SHIM_EXIT": str(exit_code),
        "UV_STDERR": uv_stderr_line,
        "SHIM_FAIL_ARGS": failing_args,
        "CLAUDE_SESSION_START_JOB_TIMEOUT_SECONDS": str(job_timeout_seconds),
    }
    started = time.monotonic()
    result = subprocess.run(
        ["bash", str(_install_scripts(tmp_path))],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result, time.monotonic() - started


def _wait_until(condition: Callable[[], bool], what: str) -> None:
    wait_for(
        condition,
        timeout=_JOB_WAIT_SECONDS,
        error_message=f"{what} within {_JOB_WAIT_SECONDS}s",
    )


def _shim_calls(tmp_path: Path) -> list[str]:
    shim_log = tmp_path / "shim.log"
    return shim_log.read_text().splitlines() if shim_log.exists() else []


def _wait_for_shim_calls(
    tmp_path: Path, predicate_text: str, expected_count: int
) -> list[str]:
    _wait_until(
        lambda: (
            sum(predicate_text in line for line in _shim_calls(tmp_path))
            >= expected_count
        ),
        f"no {expected_count} shim call(s) matching {predicate_text!r}",
    )
    return _shim_calls(tmp_path)


def _state_dir(tmp_path: Path) -> Path:
    (state_dir,) = (tmp_path / "data" / ".state" / "claude-session-start").iterdir()
    return state_dir


def test_the_hook_returns_before_its_slow_jobs_and_they_run_at_lower_priority(
    tmp_path: Path,
) -> None:
    result, elapsed = _run_hook(tmp_path, delay_seconds=_SLOW_JOB_SECONDS)

    assert result.returncode == 0
    assert elapsed < _HOOK_RETURN_BUDGET_SECONDS
    _wait_for_shim_calls(tmp_path, "plugin marketplace list", expected_count=1)
    lines = _wait_for_shim_calls(tmp_path, "sync --all-packages", expected_count=1)
    base_niceness = os.nice(0)
    job_niceness = {int(line.split()[1]) for line in lines}
    assert job_niceness == {min(base_niceness + 10, 19)}


def test_the_plugin_run_is_throttled_but_uv_sync_runs_every_session(
    tmp_path: Path,
) -> None:
    _run_hook(tmp_path, delay_seconds=0)
    _wait_for_shim_calls(tmp_path, "plugin update", expected_count=2)
    _wait_for_shim_calls(tmp_path, "sync --all-packages", expected_count=1)
    # The hook touches the stamp before it starts a plugin run, so a stamp it leaves
    # alone means it started none; an hour old is well inside the throttle window.
    stamp = _state_dir(tmp_path) / "plugin_update.stamp"
    an_hour_ago_ns = (int(time.time()) - 3600) * 1_000_000_000
    os.utime(stamp, ns=(an_hour_ago_ns, an_hour_ago_ns))

    _run_hook(tmp_path, delay_seconds=0)

    assert stamp.stat().st_mtime_ns == an_hour_ago_ns
    _wait_for_shim_calls(tmp_path, "sync --all-packages", expected_count=2)


def test_a_stale_stamp_lets_the_plugin_run_again(tmp_path: Path) -> None:
    _run_hook(tmp_path, delay_seconds=0)
    _wait_for_shim_calls(tmp_path, "plugin update", expected_count=2)
    stamp = _state_dir(tmp_path) / "plugin_update.stamp"
    a_day_ago = time.time() - 24 * 3600
    os.utime(stamp, (a_day_ago, a_day_ago))

    _run_hook(tmp_path, delay_seconds=0)

    _wait_for_shim_calls(tmp_path, "plugin marketplace list", expected_count=2)


def test_a_changed_plugin_script_runs_again_inside_the_throttle_window(
    tmp_path: Path,
) -> None:
    _run_hook(tmp_path, delay_seconds=0)
    _wait_for_shim_calls(tmp_path, "plugin update", expected_count=2)
    an_hour_ago = time.time() - 3600
    os.utime(_state_dir(tmp_path) / "plugin_update.stamp", (an_hour_ago, an_hour_ago))
    (_scripts_dir(tmp_path) / _PLUGIN_SCRIPT.name).touch()

    _run_hook(tmp_path, delay_seconds=0)

    _wait_for_shim_calls(tmp_path, "plugin marketplace list", expected_count=2)


def test_the_next_session_reports_what_the_previous_runs_warned_about(
    tmp_path: Path,
) -> None:
    # Every shim call fails: the plugin install and uv sync both log warnings.
    _run_hook(tmp_path, delay_seconds=0, exit_code=1)
    _wait_for_shim_calls(tmp_path, "sync --all-packages", expected_count=1)
    _wait_for_shim_calls(tmp_path, "plugin install", expected_count=2)
    state_dir = _state_dir(tmp_path)
    _wait_until(
        lambda: all(
            "warning:" in (state_dir / name).read_text()
            for name in ("plugin_update.log", "uv_sync.log")
        ),
        "the background runs logged no warning",
    )

    result, _ = _run_hook(tmp_path, delay_seconds=0)

    assert "warning: failed to install plugin(s)" in result.stdout
    assert "warning: uv sync --all-packages failed" in result.stdout


def test_a_warning_from_a_run_that_succeeded_is_reported_to_one_session_only(
    tmp_path: Path,
) -> None:
    # Only the updates fail: the run warns but succeeds, so its stamp and its log both
    # stay until the next run, hours later.
    _run_hook(tmp_path, delay_seconds=0, failing_args="plugin update")
    _wait_for_shim_calls(tmp_path, "plugin update", expected_count=2)
    plugin_log = _state_dir(tmp_path) / "plugin_update.log"
    _wait_until(
        lambda: plugin_log.read_text().count("warning: could not update plugin") == 2,
        "the plugin run logged no update warnings",
    )

    reporting_session, _ = _run_hook(tmp_path, delay_seconds=0)
    later_session, _ = _run_hook(tmp_path, delay_seconds=0)

    assert "warning: could not update plugin" in reporting_session.stdout
    assert "warning: could not update plugin" not in later_session.stdout


def test_a_failed_plugin_install_is_retried_by_the_next_session(tmp_path: Path) -> None:
    _run_hook(tmp_path, delay_seconds=0, exit_code=1)
    _wait_for_shim_calls(tmp_path, "plugin install", expected_count=2)
    stamp = _state_dir(tmp_path) / "plugin_update.stamp"
    _wait_until(lambda: not stamp.exists(), "the failed plugin run left its stamp")

    _run_hook(tmp_path, delay_seconds=0)

    _wait_for_shim_calls(tmp_path, "plugin marketplace list", expected_count=2)


def test_warnings_a_tool_prints_on_stderr_are_not_reported(tmp_path: Path) -> None:
    tool_warning = (
        "warning: `VIRTUAL_ENV=/elsewhere` does not match the project environment path"
    )
    _run_hook(tmp_path, delay_seconds=0, uv_stderr_line=tool_warning)
    _wait_for_shim_calls(tmp_path, "sync --all-packages", expected_count=1)
    _wait_for_shim_calls(tmp_path, "plugin update", expected_count=2)
    uv_stderr_log = _state_dir(tmp_path) / "uv_sync.stderr.log"
    _wait_until(
        lambda: tool_warning in uv_stderr_log.read_text(),
        "uv's stderr warning never reached its log",
    )

    result, _ = _run_hook(tmp_path, delay_seconds=0)

    assert "VIRTUAL_ENV" not in result.stdout


def test_a_job_that_outlives_its_time_limit_is_killed_and_counts_as_failed(
    tmp_path: Path,
) -> None:
    if shutil.which("timeout") is None:
        pytest.skip("the run-time cap needs GNU timeout, which a bare macOS lacks")
    _run_hook(tmp_path, delay_seconds=_SLOW_JOB_SECONDS, job_timeout_seconds=1)
    state_dir = _state_dir(tmp_path)

    _wait_until(
        lambda: not (state_dir / "plugin_update.stamp").exists(),
        "the timed-out plugin run left its stamp",
    )
    _wait_until(
        lambda: "failed (exit 124)" in (state_dir / "uv_sync.log").read_text(),
        "the timed-out uv sync logged no warning",
    )
    _wait_until(
        lambda: (
            "warning: the plugin install/update was stopped"
            in (state_dir / "plugin_update.log").read_text()
        ),
        "the timed-out plugin run logged no warning",
    )
    assert _shim_calls(tmp_path) == []
