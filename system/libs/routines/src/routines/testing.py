"""What the library's tests and the Routines app's tests both build: a workspace root the stores can commit to,
and a service over the real stores with the time, the chat app and the feed handed in."""

import subprocess
from pathlib import Path

from routines.definitions import FileDefinitionStore
from routines.interfaces import ChatAppInterface
from routines.interfaces import ClockInterface
from routines.interfaces import NotifierInterface
from routines.interfaces import RepositoryInterface
from routines.ledger import FileLedger
from routines.paths import RoutinesPaths
from routines.runner import Runner
from routines.service import RoutinesService
from routines.state import FileStateStore


def make_workspace_paths(root: Path) -> RoutinesPaths:
    """A fresh workspace root with the definitions directory in place."""
    (root / "system" / "routines").mkdir(parents=True)
    return RoutinesPaths(repo_root=root)


def init_git_workspace(paths: RoutinesPaths) -> RoutinesPaths:
    """Make the root a git repository with one commit, so the stores that commit can."""
    root = paths.repo_root
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    (root / "README.md").write_text("a workspace\n")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True)
    return paths


def build_test_service(
    paths: RoutinesPaths,
    repository: RepositoryInterface,
    clock: ClockInterface,
    chat_app: ChatAppInterface,
    notifier: NotifierInterface,
) -> RoutinesService:
    """The service over the real file stores at the paths, with everything else as given."""
    definitions = FileDefinitionStore(paths=paths, repository=repository)
    states = FileStateStore(paths=paths)
    ledger = FileLedger(paths=paths)
    runner = Runner(
        paths=paths,
        definitions=definitions,
        states=states,
        ledger=ledger,
        chat_app=chat_app,
        notifier=notifier,
        clock=clock,
    )
    return RoutinesService(
        paths=paths,
        registry_path=paths.repo_root / "data" / ".state" / "apps.toml",
        definitions=definitions,
        states=states,
        ledger=ledger,
        chat_app=chat_app,
        clock=clock,
        runner=runner,
    )
