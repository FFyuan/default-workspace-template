import fcntl
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from routines.errors import RunInFlightError


@contextmanager
def held_lock(path: Path, what_is_held: str) -> Generator[None, None, None]:
    """Hold the file lock for the block; raises RunInFlightError at once when another process holds it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            raise RunInFlightError(f"{what_is_held} is already going.") from e
        yield
    finally:
        handle.close()


@contextmanager
def waited_lock(path: Path) -> Generator[None, None, None]:
    """Hold the file lock for the block, waiting for whoever holds it; for the short state writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        handle.close()


def is_lock_held(path: Path) -> bool:
    """Whether another process holds the lock right now."""
    if not path.exists():
        return False
    handle = path.open("a+")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        return False
    finally:
        handle.close()
