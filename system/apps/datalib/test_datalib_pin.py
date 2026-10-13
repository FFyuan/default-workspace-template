"""The datalib pieces outside this directory agree with each other: one pinned version, and a program nothing starts."""

import configparser
import re
from pathlib import Path
from typing import Final

# system/apps/datalib/test_datalib_pin.py -> the repository root.
_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
_ENV_D_UNIT: Final[Path] = _REPO_ROOT / "system/scripts/env.d/2000-datalib-binaries.sh"
_SKILL: Final[Path] = _REPO_ROOT / ".agents/skills/datalib/SKILL.md"
_PROGRAM_CONF: Final[Path] = _REPO_ROOT / "system/supervisord.conf.d/datalib.conf"

_PINNED_VERSION: Final[re.Pattern[str]] = re.compile(r'^readonly PINNED_VERSION="(v[0-9.]+)"$', re.MULTILINE)
_ANY_VERSION: Final[re.Pattern[str]] = re.compile(r"\bv\d+\.\d+\.\d+\b")


def test_skill_names_only_the_version_the_env_d_unit_installs() -> None:
    """The skill links datalib's agent guide at a tag; a tag other than the installed one describes other binaries."""
    pinned = _PINNED_VERSION.search(_ENV_D_UNIT.read_text())
    assert pinned is not None, f"{_ENV_D_UNIT} declares no PINNED_VERSION"
    assert set(_ANY_VERSION.findall(_SKILL.read_text())) == {pinned.group(1)}


def test_datalib_program_does_not_start_on_its_own() -> None:
    """An autostarted program registers the app, which would list Datalib in every workspace."""
    parser = configparser.RawConfigParser()
    parser.read(_PROGRAM_CONF)
    assert parser.get("program:datalib", "autostart") == "false"
