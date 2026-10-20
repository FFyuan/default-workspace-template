"""`push_snapshot.py` over real git, with a local bare repo standing in for GitHub.

The gateway URL is mapped onto the bare repo with git's own `insteadOf`, set
through the environment the way any git config can be, so the script runs its
real push.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from publish_testing import git, write_finished_template
from push_snapshot import hint_for_push_failure

_SCRIPT = Path(__file__).resolve().parent / "push_snapshot.py"
_GATEWAY = "http://gateway.invalid"


class _Publish:
    """A template base, an assembled worktree with intermediate commits, and a remote."""

    def __init__(self, root: Path) -> None:
        self.worktree = root / "wt"
        self.worktree.mkdir()
        git(self.worktree, "init", "-q", "-b", "main", ".")
        git(self.worktree, "config", "user.email", "t@t.t")
        git(self.worktree, "config", "user.name", "T")
        (self.worktree / "pyproject.toml").write_text("[project]\nname = 'x'\n")
        git(self.worktree, "add", "-A")
        git(self.worktree, "commit", "-qm", "Template release")
        self.base = git(self.worktree, "rev-parse", "HEAD")

        (self.worktree / "system/apps/demo").mkdir(parents=True)
        (self.worktree / "system/apps/demo/config.py").write_text(
            "CHANNEL = 'team-private'\n"
        )
        git(self.worktree, "add", "-A")
        git(self.worktree, "commit", "-qm", "raw assembly")
        self.intermediate = git(self.worktree, "rev-parse", "HEAD")
        (self.worktree / "system/apps/demo/config.py").write_text("CHANNEL = None\n")
        write_finished_template(self.worktree, "[Open](https://github.com/octo/demo)\n")
        git(self.worktree, "add", "-A")
        git(self.worktree, "commit", "-qm", "generalize and finish the manifest")

        self.remote = root / "remotes/octo/demo.git"
        self.remote.parent.mkdir(parents=True)
        git(root, "init", "-q", "--bare", str(self.remote))
        self.root = root

    def env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.update(
            {
                "LATCHKEY_GATEWAY": _GATEWAY,
                "LATCHKEY_GATEWAY_PASSWORD": "pw",
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": f"url.{(self.root / 'remotes').as_uri()}/.insteadOf",
                "GIT_CONFIG_VALUE_0": f"{_GATEWAY}/gateway/https://github.com/",
            }
        )
        env.pop("LATCHKEY_GATEWAY_PERMISSIONS_OVERRIDE", None)
        return env

    def push(
        self, *extra: str, parent: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(_SCRIPT),
                "--worktree",
                str(self.worktree),
                "--parent",
                parent or self.base,
                "--repo",
                "octo/demo",
                "--message",
                "template: demo",
                *extra,
            ],
            env=self.env(),
            capture_output=True,
            text=True,
            timeout=60,
        )

    def remote_main(self) -> str:
        return subprocess.run(
            ["git", "rev-parse", "--verify", "-q", "refs/heads/main"],
            cwd=self.remote,
            capture_output=True,
            text=True,
        ).stdout.strip()


@pytest.fixture
def publish(tmp_path: Path) -> _Publish:
    return _Publish(tmp_path)


def test_one_snapshot_commit_on_the_base_is_published_and_nothing_in_between(
    publish: _Publish,
) -> None:
    completed = publish.push()

    assert completed.returncode == 0, completed.stdout + completed.stderr
    snapshot = publish.remote_main()
    assert completed.stdout.strip() == snapshot
    assert git(publish.remote, "rev-parse", f"{snapshot}^") == publish.base
    assert git(publish.remote, "rev-parse", f"{snapshot}^{{tree}}") == git(
        publish.worktree, "rev-parse", "HEAD^{tree}"
    )
    published = git(publish.remote, "rev-list", snapshot).splitlines()
    assert published == [snapshot, publish.base]
    assert publish.intermediate not in published


def test_a_dirty_worktree_is_refused_before_anything_is_pushed(
    publish: _Publish,
) -> None:
    (publish.worktree / "template.svg").write_text("<svg><rect/></svg>")

    completed = publish.push()

    assert completed.returncode == 1
    assert "uncommitted" in completed.stderr
    assert publish.remote_main() == ""


def test_a_failing_pre_push_gate_stops_the_push(publish: _Publish) -> None:
    (publish.worktree / "README.md").write_text(
        "[Open](https://github.com/MINDS_TEMPLATE_REPO_URL)\n"
    )
    git(publish.worktree, "commit", "-qam", "regress the readme")

    completed = publish.push()

    assert completed.returncode == 1
    assert "MINDS_TEMPLATE_REPO_URL" in completed.stderr
    assert publish.remote_main() == ""


def test_a_parent_that_does_not_resolve_is_refused(publish: _Publish) -> None:
    completed = publish.push(parent="0" * 40)

    assert completed.returncode == 1
    assert f"--parent '{'0' * 40}' is not a commit" in completed.stderr
    assert publish.remote_main() == ""


def test_an_update_fast_forwards_and_tags_the_new_version(publish: _Publish) -> None:
    first = publish.push()
    assert first.returncode == 0, first.stderr
    published_tip = publish.remote_main()
    (publish.worktree / "system/apps/demo/main.py").write_text("x = 2\n")
    git(publish.worktree, "add", "-A")
    git(publish.worktree, "commit", "-qm", "the v2 delta")

    second = publish.push("--tag", "template/demo/v2", parent=published_tip)

    assert second.returncode == 0, second.stdout + second.stderr
    new_tip = publish.remote_main()
    assert git(publish.remote, "rev-parse", f"{new_tip}^") == published_tip
    assert git(publish.remote, "rev-parse", "template/demo/v2^{commit}") == new_tip


def test_a_published_main_that_moved_is_never_overwritten(publish: _Publish) -> None:
    """A non-fast-forward means someone else pushed; a force would destroy their work."""
    assert publish.push().returncode == 0
    published_tip = publish.remote_main()
    (publish.worktree / "system/apps/demo/main.py").write_text("x = 3\n")
    git(publish.worktree, "add", "-A")
    git(publish.worktree, "commit", "-qm", "another change")

    stale = publish.push(parent=publish.base)

    assert stale.returncode == 1
    assert "moved" in stale.stderr
    assert publish.remote_main() == published_tip


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        (
            "! [remote rejected] main -> main (refusing to allow an OAuth App to create "
            "or update workflow `.github/workflows/ci.yml` without `workflow` scope)",
            "workflows",
        ),
        (
            " ! [rejected]        abc -> main (fetch first)\n"
            "error: failed to push some refs",
            "moved",
        ),
        (
            "error: RPC failed; HTTP 413 curl 22 The requested URL returned error: 413",
            "body cap",
        ),
        ('{"error": "request not permitted by the user"}', "github-git-write"),
    ],
)
def test_a_refused_push_is_explained_by_its_actual_cause(
    stderr: str, expected: str
) -> None:
    hint = hint_for_push_failure(stderr)

    assert hint is not None and expected in hint
