"""The tool refresh keeps agents' plugins and the venv current without a chat waiting on it.

What these pin: the hourly run syncs the venv, refreshes the Claude plugins in every
Claude config dir in use and the shared Codex install, at a lower CPU priority, and fails
when any of that failed so the runner retries; ``--claude-plugins`` never fails, so a
worker's provisioning cannot; and the SessionStart hook returns at once, reports each
run's warnings to one session, and starts an install only for a config dir that has never
had one. Recording ``claude`` and ``uv`` shims and a stub Codex refresh stand in for the
real programs, which need the network.
"""

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from imbue.mngr.utils.polling import wait_for

_SCRIPTS = Path(__file__).parent
_HOOK_RETURN_BUDGET_SECONDS = 2.0
_JOB_WAIT_SECONDS = 30.0

pytestmark = pytest.mark.timeout(_JOB_WAIT_SECONDS * 3)

# Each shim appends "<name> <niceness> <config dir> <args>" to $SHIM_LOG after
# $SHIM_DELAY seconds, and creates $SHIM_LOG.lock-inherited if it was handed the
# plugin refresh's lock (fd 8). `uv run` prints $SHIM_CONFIG_DIRS, standing in for
# claude_config_dirs.py. A call whose args start with $SHIM_FAIL_ARGS fails.
_SHIM = """#!/usr/bin/env bash
if { : >&8; } 2>/dev/null; then
    touch "$SHIM_LOG.lock-inherited"
fi
sleep "${SHIM_DELAY:-0}"
niceness=$(python3 -c 'import os; print(os.nice(0))')
printf '%s %s %s %s\\n' "$(basename "$0")" "$niceness" "${CLAUDE_CONFIG_DIR:--}" "$*" >> "$SHIM_LOG"
if [[ "$1 $2" == "plugin marketplace" && "$3" == "list" ]]; then
    printf '  > imbue-code-guardian\\n  > claude-code-plugins\\n'
fi
if [[ "$1" == run ]]; then
    printf '%s\\n' "$SHIM_CONFIG_DIRS"
fi
if [[ -n "${SHIM_FAIL_ARGS:-}" && "$*" == "$SHIM_FAIL_ARGS"* ]]; then
    exit 1
fi
"""

_CODEX_STUB = """#!/usr/bin/env bash
printf 'codex-refresh %s\\n' "$*" >> "$SHIM_LOG"
exit "${CODEX_STUB_EXIT:-0}"
"""


def _install(tmp_path: Path) -> Path:
    """Copy the scripts under ``tmp_path``, which they then take as the repo root."""
    scripts_dir = tmp_path / "system" / "scripts"
    if not scripts_dir.exists():
        scripts_dir.mkdir(parents=True)
        for name in ("refresh_agent_tools.sh", "claude_update_plugin.sh"):
            shutil.copy2(_SCRIPTS / name, scripts_dir / name)
        (scripts_dir / "codex_update_plugin.sh").write_text(_CODEX_STUB)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        for name in ("claude", "uv"):
            (bin_dir / name).write_text(_SHIM)
            (bin_dir / name).chmod(0o755)
    return scripts_dir / "refresh_agent_tools.sh"


def _run(
    tmp_path: Path,
    *args: str,
    config_dir: str = "default-config",
    config_dirs: tuple[str, ...] = ("default-config",),
    delay_seconds: int = 0,
    failing_args: str = "",
    codex_exit: int = 0,
    job_timeout_seconds: int = 60,
) -> tuple[subprocess.CompletedProcess[str], float]:
    script = _install(tmp_path)
    env = {
        **os.environ,
        "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(tmp_path / "home"),
        "CLAUDE_CONFIG_DIR": str(tmp_path / config_dir),
        "SHIM_LOG": str(tmp_path / "shim.log"),
        "SHIM_DELAY": str(delay_seconds),
        "SHIM_FAIL_ARGS": failing_args,
        "SHIM_CONFIG_DIRS": "\n".join(str(tmp_path / name) for name in config_dirs),
        "CODEX_STUB_EXIT": str(codex_exit),
        "AGENT_TOOLS_JOB_TIMEOUT_SECONDS": str(job_timeout_seconds),
    }
    started = time.monotonic()
    result = subprocess.run(
        ["bash", str(script), *args],
        cwd=tmp_path / "bin",
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return result, time.monotonic() - started


def _calls(tmp_path: Path) -> list[str]:
    log = tmp_path / "shim.log"
    return log.read_text().splitlines() if log.exists() else []


def _calls_matching(tmp_path: Path, text: str) -> list[str]:
    return [line for line in _calls(tmp_path) if text in line]


def _wait_for_calls(tmp_path: Path, text: str, count: int) -> None:
    wait_for(
        lambda: len(_calls_matching(tmp_path, text)) >= count,
        timeout=_JOB_WAIT_SECONDS,
        error_message=f"no {count} call(s) matching {text!r} within {_JOB_WAIT_SECONDS}s",
    )


def _claude_state_dirs(tmp_path: Path) -> list[Path]:
    root = tmp_path / "data" / ".state" / "agent-tools" / "claude"
    return sorted(root.iterdir()) if root.exists() else []


def test_the_hourly_run_refreshes_the_venv_every_claude_config_dir_and_codex(
    tmp_path: Path,
) -> None:
    result, _ = _run(tmp_path, config_dirs=("default-config", "account-a", "account-b"))

    assert result.returncode == 0, result.stdout + result.stderr
    calls = _calls(tmp_path)
    assert any(
        call.startswith("uv ") and call.endswith("sync --all-packages")
        for call in calls
    )
    for name in ("default-config", "account-a", "account-b"):
        installs = [
            call
            for call in calls
            if f" {tmp_path / name} plugin install --scope project " in call
        ]
        assert len(installs) == 2, (
            f"expected both plugins installed in {name}, got {calls}"
        )
    assert "codex-refresh --refresh-shared" in calls
    assert len(_claude_state_dirs(tmp_path)) == 3
    assert all(
        (state_dir / "installed").exists() for state_dir in _claude_state_dirs(tmp_path)
    )
    assert not (tmp_path / "shim.log.lock-inherited").exists()


def test_the_hourly_run_works_at_a_lower_priority(tmp_path: Path) -> None:
    _run(tmp_path)

    job_calls = [
        call
        for call in _calls(tmp_path)
        if call.startswith("claude ") or "sync --all-packages" in call
    ]
    assert job_calls
    assert {int(call.split()[1]) for call in job_calls} == {min(os.nice(0) + 10, 19)}


@pytest.mark.parametrize(
    ("failing_args", "codex_exit"),
    [("plugin install", 0), ("sync --all-packages", 0), ("", 1)],
)
def test_the_hourly_run_fails_when_any_part_failed_so_it_is_retried(
    tmp_path: Path, failing_args: str, codex_exit: int
) -> None:
    result, _ = _run(tmp_path, failing_args=failing_args, codex_exit=codex_exit)

    assert result.returncode == 1
    # A failure in one part does not stop the others.
    assert _calls_matching(tmp_path, "sync --all-packages")
    assert _calls_matching(tmp_path, "plugin install")
    assert "codex-refresh --refresh-shared" in _calls(tmp_path)


def test_a_failed_install_leaves_the_config_dir_unmarked(tmp_path: Path) -> None:
    result, _ = _run(tmp_path, failing_args="plugin install")

    assert "warning: failed to install plugin(s)" in result.stdout
    (state_dir,) = _claude_state_dirs(tmp_path)
    assert not (state_dir / "installed").exists()


def test_the_one_dir_mode_never_fails_and_says_what_went_wrong(tmp_path: Path) -> None:
    result, _ = _run(tmp_path, "--claude-plugins", failing_args="plugin install")

    assert result.returncode == 0
    assert "warning: failed to install plugin(s)" in result.stdout
    assert all(f" {tmp_path / 'default-config'} " in call for call in _calls(tmp_path))
    assert not _calls_matching(tmp_path, "sync --all-packages")


def test_the_one_dir_mode_installs_into_the_dir_it_is_given(tmp_path: Path) -> None:
    result, _ = _run(tmp_path, "--claude-plugins", str(tmp_path / "new-account"))

    assert result.returncode == 0, result.stdout + result.stderr
    assert _calls(tmp_path)
    assert all(f" {tmp_path / 'new-account'} " in call for call in _calls(tmp_path))


def test_the_hook_returns_at_once_and_installs_into_a_config_dir_that_never_had_one(
    tmp_path: Path,
) -> None:
    result, elapsed = _run(tmp_path, "--session-start", delay_seconds=3)

    assert result.returncode == 0
    assert elapsed < _HOOK_RETURN_BUDGET_SECONDS
    _wait_for_calls(tmp_path, "plugin update", count=2)
    assert all(f" {tmp_path / 'default-config'} " in call for call in _calls(tmp_path))
    assert not _calls_matching(tmp_path, "sync --all-packages")
    wait_for(
        lambda: all(
            (state_dir / "installed").exists()
            for state_dir in _claude_state_dirs(tmp_path)
        ),
        timeout=_JOB_WAIT_SECONDS,
        error_message="the background install never marked the config dir",
    )


def test_the_hook_starts_nothing_for_a_config_dir_that_has_its_plugins(
    tmp_path: Path,
) -> None:
    _run(tmp_path)
    calls_before = _calls(tmp_path)

    _run(tmp_path, "--session-start")
    _run(tmp_path, "--session-start", config_dir="other-config")
    _wait_for_calls(tmp_path, f" {tmp_path / 'other-config'} plugin update", count=2)

    assert _calls(tmp_path)[: len(calls_before)] == calls_before
    assert not [
        call
        for call in _calls(tmp_path)[len(calls_before) :]
        if f" {tmp_path / 'default-config'} " in call
    ]


def test_the_next_session_reports_what_the_last_run_warned_about_once(
    tmp_path: Path,
) -> None:
    _run(tmp_path, failing_args="plugin update")
    _run(
        tmp_path,
        "--claude-plugins",
        str(tmp_path / "other-config"),
        failing_args="plugin update",
    )

    reporting, _ = _run(tmp_path, "--session-start")
    later, _ = _run(tmp_path, "--session-start")
    other_dir, _ = _run(tmp_path, "--session-start", config_dir="other-config")

    assert reporting.stdout.count("warning: could not update plugin") == 2
    assert "warning: could not update plugin" not in later.stdout
    # Each config dir's warnings go to a session on that config dir.
    assert other_dir.stdout.count("warning: could not update plugin") == 2


def test_a_failed_venv_sync_is_reported_to_the_next_session(tmp_path: Path) -> None:
    _run(tmp_path, failing_args="sync --all-packages")

    result, _ = _run(tmp_path, "--session-start")

    assert "warning: uv sync --all-packages failed" in result.stdout


def test_a_job_that_outlives_its_time_limit_is_stopped_and_reported(
    tmp_path: Path,
) -> None:
    if shutil.which("timeout") is None:
        pytest.skip("the run-time cap needs GNU timeout, which a bare macOS lacks")

    result, _ = _run(tmp_path, delay_seconds=3, job_timeout_seconds=1)

    assert result.returncode == 1
    assert "warning: uv sync --all-packages failed (exit 124)" in result.stdout
    assert "warning: the plugin install/update for" in result.stdout


def test_a_run_already_going_for_a_config_dir_is_left_to_finish(tmp_path: Path) -> None:
    if shutil.which("flock") is None:
        pytest.skip("overlap protection needs flock(1), which macOS lacks")
    first = subprocess.Popen(
        ["bash", str(_install(tmp_path)), "--claude-plugins"],
        env={
            **os.environ,
            "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(tmp_path / "home"),
            "CLAUDE_CONFIG_DIR": str(tmp_path / "default-config"),
            "SHIM_LOG": str(tmp_path / "shim.log"),
            "SHIM_DELAY": "2",
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_calls(tmp_path, "plugin marketplace list", count=1)
        _run(tmp_path, "--claude-plugins")
    finally:
        first.wait(timeout=_JOB_WAIT_SECONDS)

    assert len(_calls_matching(tmp_path, "plugin marketplace list")) == 1
