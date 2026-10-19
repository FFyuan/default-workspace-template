#!/usr/bin/env python3
"""Check that the vendored Imbue Studio skill matches the mngr commit this workspace pins.

``.agents/skills/imbue-studio/SKILL.md`` is a verbatim copy of
``apps/minds/skills_plugin/skills/imbue-studio/SKILL.md`` in the mngr repository, moved
by every pin move (the mngr repo's ``scripts/bump_dwt_mngr_pin.py`` copies it from the
pinned commit). This script reads the pin from ``pyproject.toml``, fetches the file at
that commit from GitHub, and fails when the committed copy differs, so a hand edit or
a pin moved without the copy is caught in CI rather than read by an agent.

    check_vendored_mngr_skill.py               # compare against the pinned commit on GitHub
    check_vendored_mngr_skill.py --mngr-repo P # compare against a local mngr checkout instead

A private pin is fetched with the ``MNGR_INTERNAL_GIT_TOKEN`` credential when the
environment holds one; without it, pass ``--mngr-repo``.
"""

import argparse
import os
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from list_mngr_plugins import PYPROJECT_PATH, GitPin, MngrPinError, read_mngr_source

SKILL_SOURCE_PATH = "apps/minds/skills_plugin/skills/imbue-studio/SKILL.md"
SKILL_VENDORED_PATH = ".agents/skills/imbue-studio/SKILL.md"
INTERNAL_GIT_TOKEN_ENV_VAR = "MNGR_INTERNAL_GIT_TOKEN"
_FETCH_TIMEOUT_SECONDS = 60
_GIT_TIMEOUT_SECONDS = 60

# Reads the skill's text at the pinned commit; injectable so the comparison is testable offline.
SkillReader = Callable[[GitPin], str]


class VendoredSkillError(Exception):
    """The vendored skill could not be checked, or does not match the pin."""


def raw_file_url(pin: GitPin) -> str:
    """The GitHub raw URL of the skill at the pinned commit."""
    return f"{pin.git_url.replace('https://github.com/', 'https://raw.githubusercontent.com/')}/{pin.rev}/{SKILL_SOURCE_PATH}"


def read_skill_from_github(pin: GitPin) -> str:
    """Fetch the skill at the pinned commit; a private pin needs the token in the environment."""
    request = urllib.request.Request(raw_file_url(pin))
    token = os.environ.get(INTERNAL_GIT_TOKEN_ENV_VAR, "")
    if pin.is_internal:
        if not token:
            raise VendoredSkillError(
                f"the pin names the private repo and {INTERNAL_GIT_TOKEN_ENV_VAR} is unset; "
                "pass --mngr-repo <checkout> to compare locally"
            )
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=_FETCH_TIMEOUT_SECONDS) as response:
            return response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise VendoredSkillError(f"could not fetch {SKILL_SOURCE_PATH} at {pin.rev[:12]}: {exc}") from exc


def read_skill_from_checkout(mngr_repo: Path) -> SkillReader:
    """A reader that takes the skill from a local mngr checkout at the pinned commit."""

    def read(pin: GitPin) -> str:
        try:
            return subprocess.run(
                ["git", "-C", str(mngr_repo), "show", f"{pin.rev}:{SKILL_SOURCE_PATH}"],
                check=True,
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT_SECONDS,
            ).stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise VendoredSkillError(f"could not read {SKILL_SOURCE_PATH} at {pin.rev[:12]} from {mngr_repo}: {exc}") from exc

    return read


def check_vendored_skill(root: Path, read_skill: SkillReader) -> None:
    """Raise VendoredSkillError unless the vendored copy equals the skill at the pinned commit."""
    pin = read_mngr_source((root / PYPROJECT_PATH).read_text())
    vendored = root / SKILL_VENDORED_PATH
    if not vendored.is_file():
        raise VendoredSkillError(f"{SKILL_VENDORED_PATH} is missing")
    if vendored.read_text(encoding="utf-8") != read_skill(pin):
        raise VendoredSkillError(
            f"{SKILL_VENDORED_PATH} differs from {SKILL_SOURCE_PATH} at the pinned mngr commit {pin.rev[:12]}; "
            "re-run the pin move in the mngr repo (just dwt-mngr-pin*), which copies the skill, rather than editing it here"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", default=".", help="the workspace root (default: cwd)")
    parser.add_argument(
        "--mngr-repo", help="a local mngr checkout to read the pinned commit from, instead of GitHub"
    )
    args = parser.parse_args(argv)
    read_skill = read_skill_from_checkout(Path(args.mngr_repo).resolve()) if args.mngr_repo else read_skill_from_github
    try:
        check_vendored_skill(Path(args.repo_root).resolve(), read_skill)
    except (MngrPinError, VendoredSkillError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"{SKILL_VENDORED_PATH} matches the pinned mngr commit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
