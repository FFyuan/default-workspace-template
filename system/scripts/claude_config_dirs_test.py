"""Tests for claude_config_dirs.py, which tells the tool refresh where Claude keeps plugins."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest
from imbue.chat import accounts

_SCRIPT = Path(__file__).parent / "claude_config_dirs.py"
_spec = importlib.util.spec_from_file_location("claude_config_dirs", _SCRIPT)
assert _spec is not None and _spec.loader is not None
claude_config_dirs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(claude_config_dirs)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # Every index write also rewrites the create defaults beside mngr's project config.
    monkeypatch.setenv("MNGR_PROJECT_CONFIG_DIR", str(tmp_path / "project-config"))
    return tmp_path / "home"


def _add_account(home: Path, lane: str) -> Path:
    account_id, path = accounts.mint_account_dir(home)
    accounts.commit_account(account_id, lane, lane, home)
    return path


def test_lists_the_default_dir_and_only_the_claude_accounts(home: Path) -> None:
    first_claude = _add_account(home, "anthropic")
    _add_account(home, "openai")
    second_claude = _add_account(home, "anthropic")

    assert claude_config_dirs.claude_config_dirs(home) == [
        home / ".claude",
        first_claude,
        second_claude,
    ]


def test_a_workspace_with_no_accounts_has_only_the_default_dir(home: Path) -> None:
    assert claude_config_dirs.claude_config_dirs(home) == [home / ".claude"]


def test_an_account_whose_folder_is_gone_is_skipped(home: Path) -> None:
    removed = _add_account(home, "anthropic")
    shutil.rmtree(removed)

    assert claude_config_dirs.claude_config_dirs(home) == [home / ".claude"]
