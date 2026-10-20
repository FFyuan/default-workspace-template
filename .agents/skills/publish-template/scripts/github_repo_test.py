"""`github_repo.py` against a stand-in `latchkey`, over a real git worktree."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from latchkey_testing import FakeLatchkey

_SCRIPT = Path(__file__).resolve().parent / "github_repo.py"
_CREATE = "POST https://api.github.com/user/repos"
_LOCKDOWN = "PATCH https://api.github.com/repos/octo/demo"
_TOPIC = "PUT https://api.github.com/repos/octo/demo/topics"
_README = (
    '<a href="https://studio.imbue.com/open?git_url=https://github.com/MINDS_TEMPLATE_REPO_URL">Open</a>\n'
    "` /use-template https://github.com/MINDS_TEMPLATE_REPO_URL`\n"
)


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _worktree(tmp_path: Path) -> Path:
    worktree = tmp_path / "wt"
    worktree.mkdir()
    _git(worktree, "init", "-q", ".")
    _git(worktree, "config", "user.email", "t@t.t")
    _git(worktree, "config", "user.name", "T")
    (worktree / "README.md").write_text(_README)
    _git(worktree, "add", "-A")
    _git(worktree, "commit", "-qm", "assembled")
    return worktree


def _run(fake: FakeLatchkey, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        env=fake.env(),
        capture_output=True,
        text=True,
        timeout=20,
    )


def _create(
    fake: FakeLatchkey,
    worktree: Path,
    *,
    name: str = "demo",
    visibility: str = "private",
) -> subprocess.CompletedProcess[str]:
    return _run(
        fake,
        "create",
        "--name",
        name,
        "--description",
        'The "Daily" digest',
        "--visibility",
        visibility,
        "--worktree",
        str(worktree),
    )


def _body_of(fake: FakeLatchkey, method_and_url: str) -> dict[str, object]:
    method, url = method_and_url.split(" ")
    for call in fake.calls():
        if url in call and method in call:
            return json.loads(call[call.index("-d") + 1])
    raise AssertionError(f"no {method_and_url} call in {fake.calls()}")


def test_create_makes_a_locked_down_repo_and_points_the_readme_at_it(
    fake_latchkey: FakeLatchkey, tmp_path: Path
) -> None:
    worktree = _worktree(tmp_path)
    fake_latchkey.set_state(
        responses={
            _CREATE: json.dumps({"name": "demo", "owner": {"login": "octo"}}),
            _LOCKDOWN: json.dumps({"name": "demo"}),
        }
    )

    completed = _create(fake_latchkey, worktree)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "octo/demo"
    assert _body_of(fake_latchkey, _CREATE) == {
        "name": "demo",
        "description": 'The "Daily" digest (minds template v2)',
        "private": True,
    }
    assert _body_of(fake_latchkey, _LOCKDOWN) == {
        "pull_request_creation_policy": "collaborators_only",
        "has_issues": False,
        "has_wiki": False,
        "has_projects": False,
        "has_discussions": False,
    }
    readme = (worktree / "README.md").read_text()
    assert "MINDS_TEMPLATE_REPO_URL" not in readme
    assert readme.count("https://github.com/octo/demo") == 2
    assert _git(worktree, "status", "--porcelain") == ""
    assert _git(worktree, "log", "-1", "--format=%s").startswith("readme:")


def test_a_public_repo_is_created_public(
    fake_latchkey: FakeLatchkey, tmp_path: Path
) -> None:
    fake_latchkey.set_state(
        responses={
            _CREATE: json.dumps({"name": "demo", "owner": {"login": "octo"}}),
            _LOCKDOWN: json.dumps({"name": "demo"}),
        }
    )

    assert (
        _create(fake_latchkey, _worktree(tmp_path), visibility="public").returncode == 0
    )
    assert _body_of(fake_latchkey, _CREATE)["private"] is False


def test_a_refused_create_leaves_the_worktree_alone(
    fake_latchkey: FakeLatchkey, tmp_path: Path
) -> None:
    worktree = _worktree(tmp_path)
    fake_latchkey.set_state(
        responses={_CREATE: json.dumps({"error": "request not permitted by the user"})}
    )

    completed = _create(fake_latchkey, worktree)

    assert completed.returncode == 1
    assert "github-rest-api" in completed.stderr
    assert (worktree / "README.md").read_text() == _README
    assert not any("PATCH" in call for call in fake_latchkey.calls())


def test_a_taken_name_says_so(fake_latchkey: FakeLatchkey, tmp_path: Path) -> None:
    fake_latchkey.set_state(
        responses={
            _CREATE: json.dumps(
                {
                    "message": "Repository creation failed.",
                    "errors": [{"message": "name already exists on this account"}],
                }
            )
        }
    )

    completed = _create(fake_latchkey, _worktree(tmp_path))

    assert completed.returncode == 1
    assert "name already exists" in completed.stderr


def test_a_failed_lockdown_is_a_follow_up_not_a_failure(
    fake_latchkey: FakeLatchkey, tmp_path: Path
) -> None:
    """The repo exists and is private by default, so the publish carries on."""
    worktree = _worktree(tmp_path)
    fake_latchkey.set_state(
        responses={
            _CREATE: json.dumps({"name": "demo", "owner": {"login": "octo"}}),
            _LOCKDOWN: json.dumps({"message": "Server Error"}),
        }
    )

    completed = _create(fake_latchkey, worktree)

    assert completed.returncode == 0
    assert "follow-up" in completed.stderr
    assert "MINDS_TEMPLATE_REPO_URL" not in (worktree / "README.md").read_text()


@pytest.mark.parametrize("name", ["-demo", "my repo", "demo/evil", ""])
def test_an_invalid_name_is_refused_before_anything_is_created(
    fake_latchkey: FakeLatchkey, tmp_path: Path, name: str
) -> None:
    completed = _create(fake_latchkey, _worktree(tmp_path), name=name)

    assert completed.returncode == 2
    assert fake_latchkey.calls() == []


def test_topic_tags_the_repo_as_a_template(fake_latchkey: FakeLatchkey) -> None:
    fake_latchkey.set_state(
        responses={_TOPIC: json.dumps({"names": ["minds-template"]})}
    )

    completed = _run(fake_latchkey, "topic", "--repo", "octo/demo")

    assert completed.returncode == 0, completed.stderr
    assert _body_of(fake_latchkey, _TOPIC) == {"names": ["minds-template"]}
