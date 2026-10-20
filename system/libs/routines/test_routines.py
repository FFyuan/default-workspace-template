"""A routine runs through a real tick: the tick spawns a runner process, which records the run."""

import json
import os
import subprocess
import sys
import threading
import time

from routines.paths import REPO_ROOT_ENV
from routines.paths import RoutinesPaths
from routines.primitives import RoutineId
from routines.state import FileStateStore

WAIT_SECONDS = 8.0


def _routines(paths: RoutinesPaths, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "routines.cli", *args],
        cwd=paths.repo_root,
        env={**os.environ, REPO_ROOT_ENV: str(paths.repo_root)},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_a_due_routine_runs_through_a_real_tick_and_shows_up_as_worked(git_paths: RoutinesPaths) -> None:
    marker = git_paths.repo_root / "ran.txt"
    added = _routines(
        git_paths,
        "add",
        "hello",
        "--title",
        "Hello",
        "--what",
        "Says hello.",
        "--every",
        "1m",
        "--",
        "sh",
        "-c",
        f"echo hello > {marker}",
    )
    assert added.returncode == 0, added.stderr

    tick = _routines(git_paths, "tick")
    assert tick.returncode == 0, tick.stderr
    assert "started hello" in tick.stdout

    states = FileStateStore(paths=git_paths)
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline and states.read(RoutineId("hello")).last_run is None:
        threading.Event().wait(0.1)
    state = states.read(RoutineId("hello"))
    assert state.last_run is not None, "the spawned run never finished"
    assert state.last_run.outcome == "SUCCEEDED"
    assert marker.read_text().strip() == "hello"

    listing = json.loads(_routines(git_paths, "list", "--format", "json").stdout)
    assert listing["routines"][0]["health"] == "WORKING"
    assert listing["routines"][0]["last_run_text"].startswith("Worked just now, automatic")

    again = _routines(git_paths, "tick")
    assert "started hello" not in again.stdout, "a routine that just succeeded is not due again"
