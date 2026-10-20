"""What is on the disk, measured only when the user asks (``docs/system/specs/system-monitor.md`` section 4.4).

Walking the disk is slow under gVisor and the figures go stale at once, so nothing here runs on a timer:
``DiskScanner.start`` runs one walk on a thread of the app, the result is kept with its time until the app
stops, and the page says when it was taken. Each row is one ``du`` (GNU: the container is Linux), and the
rest of the disk's used space is the last row.
"""

import subprocess
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

WORKSPACE_DIR: Final[Path] = Path("/home/user/workspace")
HOME_DIR: Final[Path] = Path("/home/user")
APP_DATA_DIR: Final[Path] = Path("data/.apps")
UPLOADS_DIR: Final[Path] = Path("data/uploads")
CACHE_DIRS: Final[tuple[Path, ...]] = (
    Path(".cache"),
    Path(".npm"),
    Path(".local/share/uv"),
    Path(".local/share/pnpm"),
)
DU_TIMEOUT_SECONDS: Final[float] = 120.0
KIB: Final[int] = 1024

# Measures a set of paths, answering their size in bytes, or None when they could not be measured.
Measure = Callable[[list[Path], list[Path]], int | None]


def du_bytes(paths: list[Path], excludes: list[Path]) -> int | None:
    """The size of ``paths`` together, less anything under ``excludes``, from one ``du``; None when it fails."""
    existing = [path for path in paths if path.exists()]
    if not existing:
        return 0
    command = [
        "du",
        "-sk",
        "--total",
        *(f"--exclude={exclude}" for exclude in excludes),
        *map(str, existing),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=DU_TIMEOUT_SECONDS
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    # du exits 1 when something could not be read but still prints every total it could measure.
    for line in reversed(result.stdout.splitlines()):
        size_text, _, label = line.partition("\t")
        if label == "total" and size_text.isdigit():
            return int(size_text) * KIB
    return None


def scan(
    disk_used: int,
    workspace: Path = WORKSPACE_DIR,
    home: Path = HOME_DIR,
    measure: Measure = du_bytes,
) -> tuple[list[dict[str, Any]], list[str]]:
    """The rows of what is on the disk, and the ids of the rows that could not be measured."""
    app_data, uploads = workspace / APP_DATA_DIR, workspace / UPLOADS_DIR
    rows: list[dict[str, Any]] = []
    missing: list[str] = []

    def row(
        row_id: str, label: str, hint: str, paths: list[Path], excludes: list[Path]
    ) -> int:
        size = measure(paths, excludes)
        if size is None:
            missing.append(row_id)
            return 0
        rows.append(
            {"id": row_id, "label": label, "hint": hint, "bytes": size, "items": []}
        )
        return size

    counted = row(
        "workspace",
        "Workspace files",
        "documents, project folders, the workspace's own code",
        [workspace],
        [app_data, uploads],
    )
    counted += row("uploads", "Uploads", "files attached to chats", [uploads], [])
    app_items: list[dict[str, Any]] = []
    app_dirs = (
        sorted(path for path in app_data.iterdir() if path.is_dir())
        if app_data.is_dir()
        else []
    )
    for app_dir in app_dirs:
        size = measure([app_dir], [])
        if size is not None:
            app_items.append({"name": app_dir.name, "bytes": size})
    app_items.sort(key=lambda item: item["bytes"], reverse=True)
    rows.append(
        {
            "id": "apps",
            "label": "App data",
            "hint": "what your apps store",
            "bytes": sum(item["bytes"] for item in app_items),
            "items": app_items,
        }
    )
    counted += rows[-1]["bytes"]
    counted += row(
        "caches",
        "Package caches",
        "safe to clear; downloaded again when needed",
        [home / cache for cache in CACHE_DIRS],
        [],
    )
    rows.append(
        {
            "id": "other",
            "label": "Everything else",
            "hint": "the workspace's tools and the rest of the disk",
            "bytes": max(0, disk_used - counted),
            "items": [],
        }
    )
    return rows, missing


class DiskScanner:
    """Runs at most one walk at a time on a thread, and keeps the last result with its time."""

    def __init__(
        self,
        run: Callable[[], tuple[list[dict[str, Any]], list[str]]],
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._run = run
        self._clock = clock
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._state: dict[str, Any] = {
            "state": "idle",
            "scanned_at": None,
            "rows": [],
            "missing": [],
        }

    def start(self) -> bool:
        """Start a walk unless one is running; whether this call started one."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._state = {**self._state, "state": "scanning"}
            self._thread = threading.Thread(
                target=self._walk, name="disk-scan", daemon=True
            )
            self._thread.start()
            return True

    def _walk(self) -> None:
        rows, missing = self._run()
        with self._lock:
            self._state = {
                "state": "done",
                "scanned_at": self._clock().isoformat(),
                "rows": rows,
                "missing": missing,
            }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def wait(self, timeout_seconds: float) -> None:
        """Block until the running walk ends (tests)."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout_seconds)
