import subprocess

import pytest

from routines.errors import DefinitionCommitError
from routines.mock_clock_test import FakeClock
from routines.paths import RoutinesPaths
from routines.repository import COULD_NOT_SAVE_MESSAGE
from routines.repository import GitRepository


def _log(paths: RoutinesPaths) -> list[str]:
    output = subprocess.run(
        ["git", "log", "--format=%s", "--name-only"], cwd=paths.repo_root, capture_output=True, text=True
    )
    return [line for line in output.stdout.splitlines() if line]


def test_a_commit_takes_only_the_named_path_and_leaves_other_staged_work_alone(
    git_paths: RoutinesPaths, clock: FakeClock
) -> None:
    repository = GitRepository(repo_root=git_paths.repo_root, clock=clock)
    definition = git_paths.definitions_dir / "digest.toml"
    definition.write_text('title = "x"\n')
    other = git_paths.repo_root / "someone-elses.txt"
    other.write_text("staged by another agent\n")
    subprocess.run(["git", "add", "someone-elses.txt"], cwd=git_paths.repo_root, check=True)

    repository.commit_path(definition, "routines: add digest")

    assert _log(git_paths)[:2] == ["routines: add digest", "system/routines/digest.toml"]
    status = subprocess.run(
        ["git", "status", "--short"], cwd=git_paths.repo_root, capture_output=True, text=True
    ).stdout
    assert "A  someone-elses.txt" in status


def test_a_deletion_is_committed_the_same_way(git_paths: RoutinesPaths, clock: FakeClock) -> None:
    repository = GitRepository(repo_root=git_paths.repo_root, clock=clock)
    definition = git_paths.definitions_dir / "digest.toml"
    definition.write_text('title = "x"\n')
    repository.commit_path(definition, "routines: add digest")
    definition.unlink()

    repository.commit_path(definition, "routines: remove digest")

    assert _log(git_paths)[0] == "routines: remove digest"


def test_a_path_with_nothing_to_commit_is_not_a_failure(git_paths: RoutinesPaths, clock: FakeClock) -> None:
    repository = GitRepository(repo_root=git_paths.repo_root, clock=clock)
    repository.commit_path(git_paths.repo_root / "README.md", "routines: nothing")
    assert _log(git_paths)[0] == "init"


def test_a_held_index_lock_is_retried_once_and_then_reported_in_the_users_words(
    git_paths: RoutinesPaths, clock: FakeClock
) -> None:
    repository = GitRepository(repo_root=git_paths.repo_root, clock=clock)
    definition = git_paths.definitions_dir / "digest.toml"
    definition.write_text('title = "x"\n')
    (git_paths.repo_root / ".git" / "index.lock").write_text("")

    with pytest.raises(DefinitionCommitError, match=COULD_NOT_SAVE_MESSAGE[:20]):
        repository.commit_path(definition, "routines: add digest")

    assert clock.pauses == [1.0]
