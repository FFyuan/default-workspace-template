"""What the library's tests and the Routines app's tests both build: a workspace root the stores can commit to,
and a service over the real stores with the time, the chat app and the feed handed in."""

import subprocess
import threading
import time
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from typing import Final

from routines.data_types import LastRun
from routines.definitions import FileDefinitionStore
from routines.interfaces import ChatAppInterface
from routines.interfaces import ClockInterface
from routines.interfaces import NotifierInterface
from routines.interfaces import RepositoryInterface
from routines.interfaces import StateStoreInterface
from routines.ledger import FileLedger
from routines.paths import RoutinesPaths
from routines.primitives import RoutineId
from routines.registry import registry_path_of
from routines.runner import Runner
from routines.service import RoutinesService
from routines.state import FileStateStore

# The tests' clock: a fixed zone eight hours behind UTC with no daylight saving, so the schedules read the
# same everywhere, and a moment that is 07:00 local on a Tuesday.
TEST_ZONE: Final[timezone] = timezone(timedelta(hours=-8))
TEST_NOW: Final[datetime] = datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)
# The routine most of the library's tests are about.
TEST_ROUTINE_ID: Final[RoutineId] = RoutineId("inbox-digest")


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
        registry_path=registry_path_of(paths.repo_root, {}),
        definitions=definitions,
        states=states,
        ledger=ledger,
        chat_app=chat_app,
        clock=clock,
        runner=runner,
    )


def wait_for_last_run(states: StateStoreInterface, routine_id: RoutineId, timeout_seconds: float) -> LastRun:
    """The routine's last run once a run spawned in a process of its own has closed its books; polled, since the
    spawning side never waits on a run. Fails when none lands within the time."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        last_run = states.read(routine_id).last_run
        if last_run is not None:
            return last_run
        threading.Event().wait(0.1)
    raise AssertionError(f"the spawned run of {routine_id} never finished within {timeout_seconds} seconds")
