import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent / "validate_template.py"
_spec = importlib.util.spec_from_file_location("validate_template", _SCRIPT)
assert _spec is not None and _spec.loader is not None
validate_template = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate_template)


def test_a_shallow_snapshot_dir_still_finds_the_sibling_schema() -> None:
    """The publish gate runs from a shallow mktemp dir, not from the repo.

    `build_template.sh` snapshots this script and the schema module into a
    directory like `/tmp/tmp.XXXXXX/` before its reset. An earlier version
    indexed a fixed four levels up for the in-repo fallback, which raised
    IndexError on a path that shallow -- while building the candidate list,
    so it blew up before the sibling copy was ever considered. That failed
    every real publish (exit 6) while passing tests that happened to run from
    a deeply-nested directory.
    """
    shallow = Path("/tmp/tmp.ABC123/validate_template.py")

    candidates = validate_template._schema_module_candidates(shallow)

    assert candidates[0] == Path("/tmp/tmp.ABC123/template_manifest.py")
    assert len(candidates) > 1


def test_the_sibling_snapshot_is_preferred_over_any_repo_copy() -> None:
    # The snapshot is taken before the worktree reset precisely so the gate
    # keeps working after the reset removes the in-repo copy; preferring the
    # repo would reintroduce the dependency the snapshot exists to remove.
    deep = Path("/a/b/c/d/e/scripts/validate_template.py")

    candidates = validate_template._schema_module_candidates(deep)

    assert candidates[0] == Path("/a/b/c/d/e/scripts/template_manifest.py")


def test_every_ancestor_is_offered_as_a_repo_root() -> None:
    # Walking ancestors rather than indexing a fixed depth is what makes the
    # in-repo fallback survive the script being moved or invoked from a
    # different nesting.
    deep = Path("/a/b/c/d/e/scripts/validate_template.py")

    candidates = validate_template._schema_module_candidates(deep)

    assert Path("/a/b/c/d/e") / validate_template._IN_REPO_SCHEMA_PATH in candidates
    assert Path("/a") / validate_template._IN_REPO_SCHEMA_PATH in candidates


_FIXTURE_TOML = """format = "v2"

[template]
slug = "demo"
title = "Demo"
description = "A demo."
thumbnail = "template.svg"
version = "v1"

[recipe]
include = ["system/apps/demo"]
"""

_FIXTURE_MARKDOWN = """---
title: Demo
description: A demo.
thumbnail: template.svg
format: v2
---

# Demo
"""


def _finished_template(root: Path, readme: str) -> Path:
    (root / "template.toml").write_text(_FIXTURE_TOML)
    (root / "template.md").write_text(_FIXTURE_MARKDOWN)
    (root / "template.svg").write_text("<svg></svg>")
    (root / "README.md").write_text(readme)
    return root


def test_pre_push_refuses_a_readme_still_carrying_the_repo_url_placeholder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The Open in Imbue Studio button is dead until the real owner/repo replaces it."""
    _finished_template(
        tmp_path,
        "[Open](https://studio.imbue.com/open?git_url=https://github.com/MINDS_TEMPLATE_REPO_URL)",
    )

    assert validate_template.main([str(tmp_path), "--skip-apt-check"]) == 0
    assert (
        validate_template.main([str(tmp_path), "--skip-apt-check", "--pre-push"]) == 1
    )
    assert "MINDS_TEMPLATE_REPO_URL" in capsys.readouterr().err


def test_pre_push_passes_once_the_repo_url_is_filled_in(tmp_path: Path) -> None:
    _finished_template(
        tmp_path,
        "[Open](https://studio.imbue.com/open?git_url=https://github.com/octo/demo)",
    )

    assert (
        validate_template.main([str(tmp_path), "--skip-apt-check", "--pre-push"]) == 0
    )
