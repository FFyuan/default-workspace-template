"""`github_access.py` against a stand-in `latchkey`, run as the skill runs it."""

import subprocess
import sys
from pathlib import Path

import pytest
from latchkey_testing import FakeLatchkey

_SCRIPT = Path(__file__).resolve().parent / "github_access.py"


def _run(fake: FakeLatchkey, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        env=fake.env(),
        capture_output=True,
        text=True,
        timeout=20,
    )


_GRANTED_GIT = [{"github-git:octo": ["github-git-write"]}]


def test_check_passes_only_when_both_kinds_of_access_are_granted(
    fake_latchkey: FakeLatchkey,
) -> None:
    fake_latchkey.set_state(api=True, rules=[])
    missing_git = _run(fake_latchkey, "check")
    assert missing_git.returncode == 1
    assert "api: permitted" in missing_git.stdout
    assert "git-write: NOT permitted" in missing_git.stdout

    fake_latchkey.set_state(api=True, rules=_GRANTED_GIT)
    assert _run(fake_latchkey, "check").returncode == 0


@pytest.mark.parametrize(
    "rules",
    [
        [{"github-git:octo": ["github-git-write"]}],
        [{"github-git": ["any"]}],
        [{"any": ["github-git-write"]}],
    ],
)
def test_an_account_scoped_or_catch_all_git_grant_counts(
    fake_latchkey: FakeLatchkey, rules: list[dict[str, list[str]]]
) -> None:
    """Approved grants are keyed `github-git:<account>`, never bare `github-git`."""
    fake_latchkey.set_state(rules=rules)

    assert _run(fake_latchkey, "check", "--need", "git-write").returncode == 0


@pytest.mark.parametrize(
    "rules",
    [
        [{"github-git:octo": ["github-git-read"]}],
        [{"github-rest-api:octo": ["github-write-all"]}],
        [{"github-gitlab": ["github-git-write"]}],
    ],
)
def test_a_grant_that_cannot_push_does_not_count(
    fake_latchkey: FakeLatchkey, rules: list[dict[str, list[str]]]
) -> None:
    fake_latchkey.set_state(rules=rules)

    assert _run(fake_latchkey, "check", "--need", "git-write").returncode == 1


def test_wait_returns_once_the_approval_lands(fake_latchkey: FakeLatchkey) -> None:
    fake_latchkey.set_state(grant_after=4)

    completed = _run(
        fake_latchkey, "wait", "--timeout-seconds", "10", "--interval-seconds", "0.1"
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "permitted" in completed.stdout


def test_wait_gives_up_at_its_timeout(fake_latchkey: FakeLatchkey) -> None:
    completed = _run(
        fake_latchkey, "wait", "--timeout-seconds", "0.5", "--interval-seconds", "0.1"
    )

    assert completed.returncode == 1
    assert "NOT permitted" in completed.stderr


def test_owner_prints_the_signed_in_login(fake_latchkey: FakeLatchkey) -> None:
    fake_latchkey.set_state(api=True, login="publisher-account")

    completed = _run(fake_latchkey, "owner")

    assert completed.returncode == 0
    assert completed.stdout.strip() == "publisher-account"
