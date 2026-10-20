#!/usr/bin/env python3
"""Record a template publish in the workspace's `docs/VERSION_HISTORY.md`, committed.

    python3 record_publish.py --workspace /home/user/workspace --slug <slug> \\
        --repo-url github.com/<owner>/<repo> --note <one line> --source-sha <sha>

Run only after the push succeeded: an unpublished version is never recorded. Used
by `publish-template` (note `first published`) and `update-published-template`
(a line on what changed), so both write the same lines:

    ## Templates

    ### <slug>  --  <repo-url>
    - v1  2026-10-20  first published                    1a2b3c4
    - v2  2026-11-02  adds a reminders column            5d6e7f8

The version is computed -- one past the highest already under the slug's heading
-- and the sha is the source workspace commit the snapshot was cut from. Recording
the same note at the same sha again changes nothing, so a retried step never
duplicates an entry. Two templates published from one commit on one day have
their own headings, so they never collide.

The workspace's `## Workspace` origin line is seeded first if it is missing, and a
deleted ledger is recreated from the shipped starter -- both with `update-self`'s
own helpers, so the format lives in one place. The commit stages exactly this one
file on whatever branch the workspace is on. Prints the version recorded.
"""

from __future__ import annotations

import argparse
import datetime
import importlib
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

_LEDGER = "docs/VERSION_HISTORY.md"
_TEMPLATES_HEADING = "## Templates"
_WORKSPACE_HEADING = "## Workspace"
# Wide enough for the usual notes, so the shas line up; a longer note keeps a
# two-space gap instead of landing flush against its sha.
_NOTE_WIDTH = 35
_VERSION_PATTERN = re.compile(r"^- v(\d+)\s")


class RecordPublishError(Exception):
    """Raised when the entry cannot be written or committed."""


def _update_self_module(name: str) -> ModuleType:
    """A module from `update-self`'s scripts, which own the ledger's shared format."""
    scripts = Path(__file__).resolve().parents[2] / "update-self" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    return importlib.import_module(name)


def template_line(version: int, date: str, note: str, sha: str) -> str:
    padded = note.ljust(_NOTE_WIDTH)
    if len(padded) - len(note) < 2:
        padded = note + "  "
    return f"- v{version}  {date}  {padded}{sha}"


def _next_heading(lines: list[str], start: int, prefixes: tuple[str, ...]) -> int:
    for index in range(start, len(lines)):
        if lines[index].startswith(prefixes):
            return index
    return len(lines)


def add_template_entry(
    lines: list[str], slug: str, repo_url: str, note: str, sha: str, date: str
) -> int | None:
    """Add the entry in place; the version recorded, or None if it already was."""
    if _TEMPLATES_HEADING not in lines:
        lines.extend(["", _TEMPLATES_HEADING, ""])
    section = lines.index(_TEMPLATES_HEADING)
    section_end = _next_heading(lines, section + 1, ("## ",))
    heading = next(
        (
            index
            for index in range(section + 1, section_end)
            if lines[index].startswith(f"### {slug}  --  ")
        ),
        None,
    )
    if heading is None:
        position = section_end
        while position - 1 > section and not lines[position - 1].strip():
            position -= 1
        lines[position:position] = ["", f"### {slug}  --  {repo_url}"]
        heading = position + 1

    block_end = _next_heading(lines, heading + 1, ("## ", "### "))
    entries = [index for index in range(heading + 1, block_end) if lines[index].strip()]
    for index in entries:
        if lines[index].endswith(sha) and f"  {note}" in lines[index]:
            return None
    versions = [
        int(match.group(1))
        for match in (_VERSION_PATTERN.match(lines[index]) for index in entries)
        if match
    ]
    version = max(versions, default=0) + 1
    position = entries[-1] + 1 if entries else heading + 1
    lines.insert(position, template_line(version, date, note, sha))
    if position + 1 < len(lines) and lines[position + 1].startswith("#"):
        lines.insert(position + 1, "")
    return version


def _git(workspace: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=workspace, check=True, capture_output=True, text=True
    ).stdout.strip()


def record(
    workspace: Path, slug: str, repo_url: str, note: str, source_sha: str, date: str
) -> int | None:
    ledger = _update_self_module("update_ledger")
    runner = _update_self_module("update_runtime").Runner()
    path = workspace / _LEDGER
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(ledger.VERSION_HISTORY_STARTER)
    lines = path.read_text().splitlines()
    if not any("created from" in line for line in lines):
        if _WORKSPACE_HEADING not in lines:
            lines.extend(["", _WORKSPACE_HEADING, ""])
        ledger.insert_under_workspace(
            lines, ledger.origin_line(workspace, runner), first=True
        )
    sha = _git(workspace, "rev-parse", "--short=7", source_sha)
    version = add_template_entry(lines, slug, repo_url, note, sha, date)
    if version is None:
        return None
    path.write_text("\n".join(lines) + "\n")
    message = (
        f"version history: published template {slug} v1"
        if version == 1
        else f"version history: updated template {slug} to v{version}"
    )
    _git(workspace, "add", _LEDGER)
    try:
        _git(workspace, "commit", "-q", "-m", message)
    except subprocess.CalledProcessError as e:
        subprocess.run(
            ["git", "reset", "-q", "--", _LEDGER], cwd=workspace, check=False
        )
        raise RecordPublishError(
            f"the entry is written to {_LEDGER} but committing it failed "
            f"({e.stderr.strip()}); the template IS published -- commit that one "
            "file by hand, never re-push"
        ) from e
    return version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record a template publish in docs/VERSION_HISTORY.md."
    )
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--repo-url", required=True, help="github.com/<owner>/<repo>")
    parser.add_argument("--note", required=True)
    parser.add_argument(
        "--source-sha",
        required=True,
        help="The source commit the snapshot was cut from",
    )
    parser.add_argument("--date", default=datetime.date.today().isoformat())
    args = parser.parse_args(argv)

    try:
        version = record(
            args.workspace.resolve(),
            args.slug,
            args.repo_url,
            args.note,
            args.source_sha,
            args.date,
        )
    except (RecordPublishError, subprocess.CalledProcessError) as e:
        print(f"record_publish: {e}", file=sys.stderr)
        return 1
    if version is None:
        print(f"already recorded: {args.slug} {args.note!r} at {args.source_sha}")
        return 0
    print(f"v{version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
