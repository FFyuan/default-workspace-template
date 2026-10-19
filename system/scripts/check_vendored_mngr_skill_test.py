"""Tests for the vendored-skill check: the committed copy of the Imbue Studio skill must equal the
skill at the pinned mngr commit, read through an injected reader so no test touches GitHub."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parent / "check_vendored_mngr_skill.py"
_spec = importlib.util.spec_from_file_location("check_vendored_mngr_skill", _SCRIPT)
assert _spec is not None and _spec.loader is not None
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)

_PUBLIC_SHA = "a" * 40
_INTERNAL_SHA = "b" * 40


def _write_pin(root: Path, repo_url: str, rev: str) -> None:
    (root / "pyproject.toml").write_text(
        "[tool.uv.sources]\n"
        f'imbue-mngr = {{ git = "{repo_url}", rev = "{rev}", subdirectory = "libs/mngr" }}\n'
    )


def _write_vendored(root: Path, text: str) -> None:
    vendored = root / checker.SKILL_VENDORED_PATH
    vendored.parent.mkdir(parents=True)
    vendored.write_text(text)


def test_a_matching_copy_passes(tmp_path: Path) -> None:
    _write_pin(tmp_path, "https://github.com/imbue-ai/mngr", _PUBLIC_SHA)
    _write_vendored(tmp_path, "the skill\n")

    checker.check_vendored_skill(tmp_path, lambda pin: "the skill\n")


def test_a_differing_copy_names_the_pinned_commit(tmp_path: Path) -> None:
    _write_pin(tmp_path, "https://github.com/imbue-ai/mngr", _PUBLIC_SHA)
    _write_vendored(tmp_path, "an edited skill\n")

    with pytest.raises(checker.VendoredSkillError, match=_PUBLIC_SHA[:12]):
        checker.check_vendored_skill(tmp_path, lambda pin: "the skill\n")


def test_a_missing_copy_is_reported(tmp_path: Path) -> None:
    _write_pin(tmp_path, "https://github.com/imbue-ai/mngr", _PUBLIC_SHA)

    with pytest.raises(checker.VendoredSkillError, match="missing"):
        checker.check_vendored_skill(tmp_path, lambda pin: "the skill\n")


def test_the_reader_is_handed_the_pin_from_pyproject(tmp_path: Path) -> None:
    _write_pin(tmp_path, "https://github.com/imbue-ai/mngr-internal", _INTERNAL_SHA)
    _write_vendored(tmp_path, "the skill\n")
    seen: list[checker.GitPin] = []

    def read(pin: checker.GitPin) -> str:
        seen.append(pin)
        return "the skill\n"

    checker.check_vendored_skill(tmp_path, read)

    assert [(pin.git_url, pin.rev) for pin in seen] == [("https://github.com/imbue-ai/mngr-internal", _INTERNAL_SHA)]


def test_the_raw_url_points_at_the_skill_in_the_pinned_repo_and_commit() -> None:
    pin = checker.GitPin(git_url="https://github.com/imbue-ai/mngr", rev=_PUBLIC_SHA)

    assert checker.raw_file_url(pin) == (
        f"https://raw.githubusercontent.com/imbue-ai/mngr/{_PUBLIC_SHA}/apps/minds/skills_plugin/skills/imbue-studio/SKILL.md"
    )


def test_a_private_pin_without_a_token_asks_for_a_local_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(checker.INTERNAL_GIT_TOKEN_ENV_VAR, raising=False)
    pin = checker.GitPin(git_url="https://github.com/imbue-ai/mngr-internal", rev=_INTERNAL_SHA)

    with pytest.raises(checker.VendoredSkillError, match="--mngr-repo"):
        checker.read_skill_from_github(pin)
