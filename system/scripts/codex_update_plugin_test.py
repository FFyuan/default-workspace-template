"""The provisioning installer must target the new agent, never its parent/account."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from imbue.mngr_codex.codex_config import get_codex_home

_SCRIPT = Path(__file__).with_name("codex_update_plugin.sh")
_SHIM = """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
with open(os.environ["SHIM_LOG"], "a") as log:
    log.write(json.dumps([os.environ["CODEX_HOME"], sys.argv[1:], os.environ.get("MNGR_AGENT_ID")]) + "\\n")
if " ".join(sys.argv[1:3]) == os.environ.get("SHIM_FAIL"):
    sys.exit(1)
home = Path(os.environ["CODEX_HOME"])
revision = os.environ.get("SHIM_REVISION", "1")
if sys.argv[1:3] == ["plugin", "marketplace"]:
    marketplace = home / ".tmp/marketplaces/imbue-code-guardian"
    marketplace.mkdir(parents=True, exist_ok=True)
    (marketplace / "revision").write_text(revision)
if sys.argv[1:3] == ["plugin", "add"]:
    (home / "plugins/cache/imbue-code-guardian/imbue-code-guardian" / revision).mkdir(parents=True, exist_ok=True)
    with (home / "config.toml").open("a") as config:
        config.write('\\n[plugins."imbue-code-guardian@imbue-code-guardian"]\\nenabled = true\\n')
"""


def _run(
    tmp_path: Path,
    *args: str,
    fail: str = "",
    provisioned: bool = True,
    agent: str = "agent state",
    revision: str = "1",
) -> tuple[subprocess.CompletedProcess[str], list[list[object]], Path]:
    state = tmp_path / agent
    home = get_codex_home(state)
    home.mkdir(parents=True, exist_ok=True)
    if provisioned:
        (home / "config.toml").write_text('model = "example"\n')
    shared = tmp_path / "account home"
    shared.mkdir(exist_ok=True)
    (shared / "config.toml").write_text("# untouched\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    shim = bin_dir / "codex"
    shim.write_text(_SHIM)
    shim.chmod(0o755)
    log = tmp_path / "calls.jsonl"
    log.unlink(missing_ok=True)
    result = subprocess.run(
        ["bash", str(_SCRIPT), *args],
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "MNGR_AGENT_STATE_DIR": str(state),
            "MNGR_AGENT_ID": f"agent-{agent.replace(' ', '-')}",
            "CODEX_HOME": str(shared),
            "SHIM_LOG": str(log),
            "SHIM_FAIL": fail,
            "CODE_GUARDIAN_MARKETPLACE": "imbue-ai/code-guardian@main",
            "SHIM_REVISION": revision,
            "CODEX_PLUGIN_SHARED_COPY_DIR": str(_shared_root(tmp_path)),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert (shared / "config.toml").read_text() == "# untouched\n"
    return (
        result,
        [json.loads(line) for line in log.read_text().splitlines()]
        if log.exists()
        else [],
        home,
    )


def _shared_root(tmp_path: Path) -> Path:
    return tmp_path / "plugin copies"


def _shared_copy(tmp_path: Path) -> Path:
    return (_shared_root(tmp_path) / "current").resolve()


def _installed(home: Path) -> tuple[str, list[str]]:
    """The marketplace revision and the plugin versions installed in a Codex home."""
    revision = (home / ".tmp/marketplaces/imbue-code-guardian/revision").read_text()
    plugin = home / "plugins/cache/imbue-code-guardian/imbue-code-guardian"
    return revision, sorted(path.name for path in plugin.iterdir())


def _refresh(
    tmp_path: Path, revision: str, fail: str = ""
) -> tuple[subprocess.CompletedProcess[str], list[list[object]]]:
    """Run the hourly refresh of the shared copy, which has no agent of its own."""
    log = tmp_path / "calls.jsonl"
    log.unlink(missing_ok=True)
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("MNGR_AGENT_STATE_DIR", "CODEX_HOME")
    }
    result = subprocess.run(
        ["bash", str(_SCRIPT), "--refresh-shared"],
        env={
            **env,
            "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}",
            "SHIM_LOG": str(log),
            "SHIM_FAIL": fail,
            "SHIM_REVISION": revision,
            "CODEX_PLUGIN_SHARED_COPY_DIR": str(_shared_root(tmp_path)),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    calls = (
        [json.loads(line) for line in log.read_text().splitlines()]
        if log.exists()
        else []
    )
    return result, calls


def test_the_first_install_comes_from_github_and_becomes_the_shared_copy(
    tmp_path: Path,
) -> None:
    result, calls, home = _run(tmp_path)

    assert result.returncode == 0, result.stderr
    assert [call[1][:2] for call in calls] == [
        ["plugin", "marketplace"],
        ["plugin", "add"],
    ]
    assert _installed(_shared_copy(tmp_path)) == _installed(home) == ("1", ["1"])


def test_a_later_agent_copies_the_shared_install_without_running_codex(
    tmp_path: Path,
) -> None:
    _run(tmp_path, agent="first agent")

    result, calls, home = _run(tmp_path, agent="second agent", revision="2")

    assert result.returncode == 0, result.stderr
    assert calls == []
    assert _installed(home) == ("1", ["1"])


def test_a_copy_that_fails_partway_falls_back_to_installing_from_github(
    tmp_path: Path,
) -> None:
    _run(tmp_path, agent="first agent")
    # A file where the marketplace snapshot's parent folder goes: only the plugin
    # cache could be copied.
    blocked_home = get_codex_home(tmp_path / "second agent")
    blocked_home.mkdir(parents=True)
    (blocked_home / ".tmp").write_text("")

    result, calls, _ = _run(tmp_path, agent="second agent")

    assert result.returncode == 0, result.stderr
    assert [call[1][:2] for call in calls] == [
        ["plugin", "marketplace"],
        ["plugin", "add"],
    ]


def test_a_refresh_before_any_codex_agent_does_nothing(tmp_path: Path) -> None:
    _run(tmp_path, provisioned=False)

    result, calls = _refresh(tmp_path, revision="2")

    assert result.returncode == 0, result.stderr
    assert calls == []


def test_a_refresh_updates_the_shared_copy_for_the_next_agent(tmp_path: Path) -> None:
    _, _, first_home = _run(tmp_path, agent="first agent")
    first_copy = _shared_copy(tmp_path)

    result, calls = _refresh(tmp_path, revision="2")
    _, _, second_home = _run(tmp_path, agent="second agent")

    assert result.returncode == 0, result.stderr
    # It installs into a home of its own, with the config the last agent left.
    assert {call[0] for call in calls}.isdisjoint({str(first_home), str(second_home)})
    assert _installed(first_home) == ("1", ["1"])
    assert _installed(second_home) == ("2", ["2"])
    # The copy it replaced stays, since an agent may still be copying from it.
    assert first_copy.exists()
    assert not list(_shared_root(tmp_path).glob("refresh.??????"))


def test_a_failed_refresh_keeps_the_shared_copy_and_fails(tmp_path: Path) -> None:
    _run(tmp_path, agent="first agent")

    result, _ = _refresh(tmp_path, revision="2", fail="plugin add")

    assert result.returncode == 1
    assert "keep the previous one" in result.stdout
    assert _installed(_shared_copy(tmp_path)) == ("1", ["1"])


def test_only_the_two_newest_shared_copies_are_kept(tmp_path: Path) -> None:
    _run(tmp_path, agent="first agent")
    for number in (2, 3):
        _refresh(tmp_path, revision=str(number))

    assert len(list(_shared_root(tmp_path).glob("copy.*"))) == 2
    assert _installed(_shared_copy(tmp_path)) == ("3", ["3"])


def test_install_and_reprovision_target_mngrs_home(tmp_path: Path) -> None:
    for _ in range(2):
        # Without a shared copy, so each run installs from GitHub.
        shutil.rmtree(_shared_root(tmp_path), ignore_errors=True)
        result, calls, home = _run(tmp_path)
        assert result.returncode == 0, result.stderr
        assert all(call[0] == str(home) for call in calls)
        assert calls[-1][1] == [
            "plugin",
            "add",
            "imbue-code-guardian@imbue-code-guardian",
        ]
        assert "enabled = true" in (home / "config.toml").read_text()
        assert 'model = "example"' in (home / "config.toml").read_text()


@pytest.mark.parametrize("args,expected", [((), 0), (("--strict",), 1)])
def test_install_outage_warns_and_strict_fails(
    tmp_path: Path, args: tuple[str, ...], expected: int
) -> None:
    result, _, _ = _run(tmp_path, *args, fail="plugin add")
    assert result.returncode == expected
    assert "installation failed" in result.stderr


def test_marketplace_outage_still_attempts_cached_install(tmp_path: Path) -> None:
    result, calls, _ = _run(tmp_path, "--strict", fail="plugin marketplace")
    assert result.returncode == 0, result.stderr
    assert "cached marketplace" in result.stderr
    assert calls[-1][1] == ["plugin", "add", "imbue-code-guardian@imbue-code-guardian"]


def test_refuses_install_before_mngr_writes_config(tmp_path: Path) -> None:
    result, calls, _ = _run(tmp_path, provisioned=False)
    assert result.returncode == 1
    assert "must be provisioned" in result.stderr
    assert calls == []


def test_refuses_install_without_agent_state(tmp_path: Path) -> None:
    env = {
        key: value for key, value in os.environ.items() if key != "MNGR_AGENT_STATE_DIR"
    }
    result = subprocess.run(
        ["bash", str(_SCRIPT)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 1
    assert "refusing a shared-home install" in result.stderr


@pytest.mark.parametrize("args", [("--unknown",), ("--strict", "extra")])
def test_rejects_invalid_arguments(tmp_path: Path, args: tuple[str, ...]) -> None:
    result, calls, _ = _run(tmp_path, *args)
    assert result.returncode == 2
    assert calls == []
