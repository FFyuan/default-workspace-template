"""The commands harden-contention.md gives a lead, run as written against a real ticket."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DOC = _REPO_ROOT / ".agents" / "shared" / "references" / "harden-contention.md"
_TK = _REPO_ROOT / "system" / "vendor" / "tk" / "ticket"
_BASH_BLOCK = re.compile(r"```bash\n(.*?)```", re.DOTALL)


def _bash_block_containing(marker: str) -> str:
    blocks = [
        block for block in _BASH_BLOCK.findall(_DOC.read_text()) if marker in block
    ]
    assert len(blocks) == 1, f"expected one bash block holding {marker!r} in {_DOC}"
    return blocks[0]


def _run_bash(
    script: str, env: dict[str, str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(sys.platform != "linux", reason="the workspace's sed is GNU sed")
def test_a_creation_a_catch_up_adds_is_found_by_the_single_flight_check(
    tmp_path: Path,
) -> None:
    """A lead that widens its pass records the added creation in its task file and its
    ticket's title, so another chat's single-flight check finds the pass by that creation and
    a chat taking the pass over leads it with every creation it now covers."""
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir()
    (bin_directory / "tk").symlink_to(_TK)
    tickets_directory = tmp_path / "tickets"
    tickets_directory.mkdir()
    env = {
        **os.environ,
        "PATH": f"{bin_directory}{os.pathsep}{os.environ['PATH']}",
        "TICKETS_DIR": str(tickets_directory),
    }
    env.pop("MNGR_AGENT_NAME", None)
    created = _run_bash(
        'tk create "update skill:text-stats" -t task -d "Worker: update-text-stats"',
        env,
        tmp_path,
    )
    assert created.returncode == 0, created.stderr
    ticket_id = created.stdout.strip()
    task_file = tmp_path / "task.md"
    task_file.write_text(
        "---\noperation: update\ncreations: skill:text-stats\n---\n\n# Task\n"
    )
    widen = (
        _bash_block_containing("ADDED=")
        .replace('"<each added creation, as type:name>"', '"skill:slug-title"')
        .replace("<TASK_FILE>", str(task_file))
        .replace("<ticket-id>", ticket_id)
    )
    single_flight = _bash_block_containing("tk ready > ").replace(
        "/tmp/harden-inflight.txt", str(tmp_path / "inflight.txt")
    )

    widened = _run_bash(widen, env, tmp_path)
    found = _run_bash(single_flight, {**env, "CREATIONS": "skill:slug-title"}, tmp_path)

    assert widened.returncode == 0, widened.stderr
    assert ticket_id in found.stdout
    assert "creations: skill:text-stats skill:slug-title\n" in task_file.read_text()
