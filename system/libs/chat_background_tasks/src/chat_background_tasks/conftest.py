import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def marker_root(tmp_path: Path) -> Path:
    return tmp_path / "background_tasks"


@pytest.fixture
def exited_pid() -> int:
    """The pid of a process that has already exited, which a marker naming it is stale by."""
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


def _sleeping_process_named(directory: Path, name: str) -> subprocess.Popen[bytes]:
    sleep = shutil.which("sleep")
    assert sleep is not None
    directory.mkdir()
    executable = directory / name
    # A link, not a copy: macOS kills a copied system binary, and a process run through a link is
    # named after the link.
    executable.symlink_to(sleep)
    return subprocess.Popen([str(executable), "60"])


@pytest.fixture
def live_claude_pid(tmp_path: Path) -> Iterator[int]:
    """The pid of a live process whose executable is named ``claude``, as an agent's main claude is."""
    process = _sleeping_process_named(tmp_path / "claude-bin", "claude")
    yield process.pid
    process.kill()
    process.wait()


@pytest.fixture
def live_other_pid(tmp_path: Path) -> Iterator[int]:
    """The pid of a live process that is not a claude."""
    process = _sleeping_process_named(tmp_path / "other-bin", "sleeper")
    yield process.pid
    process.kill()
    process.wait()
