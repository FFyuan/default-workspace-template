"""`record_publish.py` writing the ledger of a real workspace-shaped repo."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent / "record_publish.py"
_REPO_ROOT = Path(__file__).resolve().parents[4]
_LEDGER = "docs/VERSION_HISTORY.md"
_TODAY = "2026-10-20"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A template release tagged minds-v0.9.1, then bootstrap's marker, then work."""
    root = tmp_path / "workspace"
    (root / "docs").mkdir(parents=True)
    _git(root, "init", "-q", ".")
    _git(root, "config", "user.email", "t@t.t")
    _git(root, "config", "user.name", "T")
    (root / _LEDGER).write_text((_REPO_ROOT / _LEDGER).read_text())
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "Template release")
    _git(root, "tag", "minds-v0.9.1")
    _git(root, "commit", "-q", "--allow-empty", "-m", "Initial workspace commit")
    (root / "app.py").write_text("x = 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "Build the app")
    return root


def _record(
    workspace: Path, note: str, *, slug: str = "inbox", sha: str = "HEAD"
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--workspace",
            str(workspace),
            "--slug",
            slug,
            "--repo-url",
            f"github.com/octo/{slug}",
            "--note",
            note,
            "--source-sha",
            sha,
            "--date",
            _TODAY,
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )


def _templates_block(workspace: Path, slug: str) -> list[str]:
    lines = (workspace / _LEDGER).read_text().splitlines()
    start = lines.index(f"### {slug}  --  github.com/octo/{slug}")
    block = []
    for line in lines[start + 1 :]:
        if line.startswith("#"):
            break
        if line.strip():
            block.append(line)
    return block


def test_a_first_publish_records_v1_and_seeds_where_the_workspace_started(
    workspace: Path,
) -> None:
    head = _git(workspace, "rev-parse", "--short=7", "HEAD")
    marker = _git(workspace, "rev-parse", "--short=7", "HEAD~1")
    (workspace / "app.py").write_text("x = 2\n")

    completed = _record(workspace, "first published")

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "v1"
    assert _templates_block(workspace, "inbox") == [
        f"- v1  {_TODAY}  {'first published':<35}{head}"
    ]
    ledger = (workspace / _LEDGER).read_text()
    assert re.search(
        rf"^- \d{{4}}-\d\d-\d\d  created from minds-v0\.9\.1 +{marker}$", ledger, re.M
    )
    assert (
        _git(workspace, "log", "-1", "--format=%s")
        == "version history: published template inbox v1"
    )
    assert _git(workspace, "show", "--name-only", "--format=", "HEAD") == _LEDGER
    assert _git(workspace, "status", "--porcelain") == "M app.py"


def test_recording_the_same_publish_again_changes_nothing(workspace: Path) -> None:
    source = _git(workspace, "rev-parse", "HEAD")
    assert _record(workspace, "first published", sha=source).returncode == 0
    commits = _git(workspace, "rev-list", "--count", "HEAD")

    again = _record(workspace, "first published", sha=source)

    assert again.returncode == 0
    assert "already recorded" in again.stdout
    assert _git(workspace, "rev-list", "--count", "HEAD") == commits


def test_an_update_appends_the_next_version_under_the_same_heading(
    workspace: Path,
) -> None:
    assert _record(workspace, "first published").returncode == 0
    (workspace / "app.py").write_text("x = 3\n")
    _git(workspace, "commit", "-qam", "Add reminders")
    head = _git(workspace, "rev-parse", "--short=7", "HEAD")

    completed = _record(workspace, "adds a reminders column")

    assert completed.stdout.strip() == "v2"
    assert _templates_block(workspace, "inbox")[-1] == (
        f"- v2  {_TODAY}  {'adds a reminders column':<35}{head}"
    )
    assert _git(workspace, "log", "-1", "--format=%s") == (
        "version history: updated template inbox to v2"
    )


def test_two_templates_from_one_commit_are_recorded_separately(
    workspace: Path,
) -> None:
    assert _record(workspace, "first published", slug="inbox").returncode == 0

    completed = _record(workspace, "first published", slug="digest")

    assert completed.stdout.strip() == "v1"
    assert len(_templates_block(workspace, "inbox")) == 1
    assert len(_templates_block(workspace, "digest")) == 1


def test_a_long_note_still_leaves_two_spaces_before_the_sha(workspace: Path) -> None:
    note = "rewrites the digest to group by sender and adds a weekly summary"
    head = _git(workspace, "rev-parse", "--short=7", "HEAD")

    assert _record(workspace, note).returncode == 0

    assert _templates_block(workspace, "inbox") == [f"- v1  {_TODAY}  {note}  {head}"]


def test_a_deleted_ledger_is_recreated_from_the_shipped_starter(
    workspace: Path,
) -> None:
    _git(workspace, "rm", "-q", _LEDGER)
    _git(workspace, "commit", "-qm", "drop the ledger")

    completed = _record(workspace, "first published")

    assert completed.returncode == 0, completed.stderr
    ledger = (workspace / _LEDGER).read_text()
    assert ledger.startswith("# Version history\n")
    assert (
        ledger.index("## Templates")
        < ledger.index("### inbox")
        < ledger.index("## Adopted templates")
    )
