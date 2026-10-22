"""`github_access.py` against a stand-in `latchkey`, run as the skill runs it."""

from pathlib import Path

import pytest
from latchkey_testing import FakeLatchkey

_SCRIPT = Path(__file__).resolve().parent / "github_access.py"


_GRANTED_GIT = [{"github-git:octo": ["github-git-write"]}]


def test_check_passes_only_when_both_kinds_of_access_are_granted(
    fake_latchkey: FakeLatchkey,
) -> None:
    fake_latchkey.set_state(api=True, rules=[])
    missing_git = fake_latchkey.run(_SCRIPT, "check")
    assert missing_git.returncode == 1
    assert "api: permitted" in missing_git.stdout
    assert "git-write: NOT permitted" in missing_git.stdout

    fake_latchkey.set_state(api=True, rules=_GRANTED_GIT)
    assert fake_latchkey.run(_SCRIPT, "check").returncode == 0


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

    assert fake_latchkey.run(_SCRIPT, "check", "--need", "git-write").returncode == 0


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

    assert fake_latchkey.run(_SCRIPT, "check", "--need", "git-write").returncode == 1


def test_wait_returns_once_the_approval_lands(fake_latchkey: FakeLatchkey) -> None:
    fake_latchkey.set_state(grant_after=4)

    completed = fake_latchkey.run(
        _SCRIPT, "wait", "--timeout-seconds", "10", "--interval-seconds", "0.1"
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "permitted" in completed.stdout


def test_wait_gives_up_at_its_timeout(fake_latchkey: FakeLatchkey) -> None:
    completed = fake_latchkey.run(
        _SCRIPT, "wait", "--timeout-seconds", "0.5", "--interval-seconds", "0.1"
    )

    assert completed.returncode == 1
    assert "NOT permitted" in completed.stderr


_DESKTOP_DOWN = (
    "Desktop host-1 (laptop) is unreachable: connect ECONNREFUSED 127.0.0.1:42379"
)


def test_an_unreachable_desktop_is_unknown_not_a_missing_grant(
    fake_latchkey: FakeLatchkey,
) -> None:
    """A permission request would go through the same unreachable app, so do not prompt one."""
    fake_latchkey.set_state(api=True, permissions_error=_DESKTOP_DOWN)

    completed = fake_latchkey.run(_SCRIPT, "check")

    assert completed.returncode == 2
    assert "NOT permitted" not in completed.stdout
    assert f"git-write: UNKNOWN ({_DESKTOP_DOWN})" in completed.stdout


def test_a_missing_grant_still_reads_as_missing_beside_an_unknown(
    fake_latchkey: FakeLatchkey,
) -> None:
    fake_latchkey.set_state(api=False, permissions_error=_DESKTOP_DOWN)

    assert fake_latchkey.run(_SCRIPT, "check").returncode == 1


def test_wait_polls_through_an_unreachable_desktop(fake_latchkey: FakeLatchkey) -> None:
    fake_latchkey.set_state(permissions_error=_DESKTOP_DOWN, grant_after=4)

    completed = fake_latchkey.run(
        _SCRIPT, "wait", "--timeout-seconds", "10", "--interval-seconds", "0.1"
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
