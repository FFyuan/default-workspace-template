"""Tests for the vendored-skill writer and check: the committed copy of the Imbue Studio skill is
written from, and must equal, the skill at the pinned mngr commit, read through an injected reader
so no test touches GitHub."""

from __future__ import annotations

from pathlib import Path

import pytest
import vendor_mngr_skill
from list_mngr_plugins import GitPin

_PUBLIC_SHA = "a" * 40
_INTERNAL_SHA = "b" * 40


def _write_pin(root: Path, repo_url: str, rev: str) -> None:
    (root / "pyproject.toml").write_text(
        "[tool.uv.sources]\n"
        f'imbue-mngr = {{ git = "{repo_url}", rev = "{rev}", subdirectory = "libs/mngr" }}\n'
    )


def _write_vendored(root: Path, text: str) -> None:
    vendored = root / vendor_mngr_skill.SKILL_VENDORED_PATH
    vendored.parent.mkdir(parents=True)
    vendored.write_text(text)


def test_writing_copies_the_skill_at_the_given_commit(tmp_path: Path) -> None:
    pin = GitPin(git_url="https://github.com/imbue-ai/mngr", rev=_PUBLIC_SHA)

    is_changed = vendor_mngr_skill.write_vendored_skill(tmp_path, pin, lambda pin: f"skill at {pin.rev}\n")

    assert is_changed
    assert (tmp_path / vendor_mngr_skill.SKILL_VENDORED_PATH).read_text() == f"skill at {_PUBLIC_SHA}\n"


def test_writing_leaves_a_matching_copy_untouched(tmp_path: Path) -> None:
    _write_vendored(tmp_path, "the skill\n")
    vendored = tmp_path / vendor_mngr_skill.SKILL_VENDORED_PATH
    before = vendored.stat().st_mtime_ns
    pin = GitPin(git_url="https://github.com/imbue-ai/mngr", rev=_PUBLIC_SHA)

    is_changed = vendor_mngr_skill.write_vendored_skill(tmp_path, pin, lambda pin: "the skill\n")

    assert not is_changed
    assert vendored.stat().st_mtime_ns == before


def test_a_matching_copy_passes_the_check(tmp_path: Path) -> None:
    _write_pin(tmp_path, "https://github.com/imbue-ai/mngr", _PUBLIC_SHA)
    _write_vendored(tmp_path, "the skill\n")

    vendor_mngr_skill.check_vendored_skill(tmp_path, lambda pin: "the skill\n")


def test_a_differing_copy_fails_the_check_naming_the_pinned_commit(tmp_path: Path) -> None:
    _write_pin(tmp_path, "https://github.com/imbue-ai/mngr", _PUBLIC_SHA)
    _write_vendored(tmp_path, "an edited skill\n")

    with pytest.raises(vendor_mngr_skill.VendoredSkillError, match=_PUBLIC_SHA[:12]):
        vendor_mngr_skill.check_vendored_skill(tmp_path, lambda pin: "the skill\n")


def test_a_missing_copy_fails_the_check(tmp_path: Path) -> None:
    _write_pin(tmp_path, "https://github.com/imbue-ai/mngr", _PUBLIC_SHA)

    with pytest.raises(vendor_mngr_skill.VendoredSkillError, match="missing"):
        vendor_mngr_skill.check_vendored_skill(tmp_path, lambda pin: "the skill\n")


def test_the_check_reads_the_pin_from_pyproject(tmp_path: Path) -> None:
    _write_pin(tmp_path, "https://github.com/imbue-ai/mngr-internal", _INTERNAL_SHA)
    _write_vendored(tmp_path, "the skill\n")
    seen: list[GitPin] = []

    def read(pin: GitPin) -> str:
        seen.append(pin)
        return "the skill\n"

    vendor_mngr_skill.check_vendored_skill(tmp_path, read)

    assert [(pin.git_url, pin.rev) for pin in seen] == [("https://github.com/imbue-ai/mngr-internal", _INTERNAL_SHA)]


def test_the_raw_url_points_at_the_skill_in_the_pinned_repo_and_commit() -> None:
    pin = GitPin(git_url="https://github.com/imbue-ai/mngr", rev=_PUBLIC_SHA)

    assert vendor_mngr_skill.raw_file_url(pin) == (
        f"https://raw.githubusercontent.com/imbue-ai/mngr/{_PUBLIC_SHA}/apps/minds/skills_plugin/skills/imbue-studio/SKILL.md"
    )


def test_a_private_pin_without_a_token_asks_for_a_local_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(vendor_mngr_skill.INTERNAL_GIT_TOKEN_ENV_VAR, raising=False)
    pin = GitPin(git_url="https://github.com/imbue-ai/mngr-internal", rev=_INTERNAL_SHA)

    with pytest.raises(vendor_mngr_skill.VendoredSkillError, match="--mngr-repo"):
        vendor_mngr_skill.read_skill_from_github(pin)
