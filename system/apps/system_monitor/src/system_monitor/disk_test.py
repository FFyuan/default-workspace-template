"""Tests for the on-demand walk of the disk: the rows, a row that cannot be measured, the real ``du``, and the
scanner that runs one walk at a time."""

from datetime import datetime, timezone
from pathlib import Path

from system_monitor import disk


def test_the_rows_cover_the_buckets_and_the_rest_of_the_disk(tmp_path: Path) -> None:
    workspace, home = tmp_path / "workspace", tmp_path / "home"
    for app in ("recipe-box", "habit-tracker"):
        (workspace / "data" / ".apps" / app).mkdir(parents=True)
    (home / ".cache").mkdir(parents=True)
    sizes = {
        str(workspace): 3000,
        str(workspace / "data" / "uploads"): 1200,
        str(workspace / "data" / ".apps" / "recipe-box"): 610,
        str(workspace / "data" / ".apps" / "habit-tracker"): 290,
        str(home / ".cache"): 2400,
    }
    measured: list[tuple[list[Path], list[Path]]] = []

    def measure(paths: list[Path], excludes: list[Path]) -> int | None:
        measured.append((paths, excludes))
        return sum(sizes.get(str(path), 0) for path in paths)

    rows, missing = disk.scan(10_000, workspace, home, measure)

    assert missing == []
    assert [(row["id"], row["bytes"]) for row in rows] == [
        ("workspace", 3000),
        ("uploads", 1200),
        ("apps", 900),
        ("caches", 2400),
        ("other", 2500),
    ]
    assert rows[2]["items"] == [
        {"name": "recipe-box", "bytes": 610},
        {"name": "habit-tracker", "bytes": 290},
    ]
    # The workspace is measured without the app data and uploads that get rows of their own.
    assert measured[0] == (
        [workspace],
        [workspace / "data" / ".apps", workspace / "data" / "uploads"],
    )


def test_a_row_that_cannot_be_measured_is_reported_missing_and_the_rest_never_goes_negative(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    for app in ("recipe-box", "habit-tracker"):
        (workspace / "data" / ".apps" / app).mkdir(parents=True)

    def measure(paths: list[Path], excludes: list[Path]) -> int | None:
        if paths in ([workspace], [workspace / "data" / ".apps" / "habit-tracker"]):
            return None
        return 9000

    rows, missing = disk.scan(100, workspace, tmp_path / "home", measure)

    assert missing == ["workspace", "apps"]
    assert [row["id"] for row in rows] == ["uploads", "apps", "caches", "other"]
    # The App data row keeps the apps it could measure.
    assert rows[1]["items"] == [{"name": "recipe-box", "bytes": 9000}]
    assert rows[-1]["bytes"] == 0


def test_du_measures_a_tree_less_its_excludes_and_a_missing_path_is_nothing(
    tmp_path: Path,
) -> None:
    tree = tmp_path / "tree"
    (tree / "keep").mkdir(parents=True)
    (tree / "skip").mkdir()
    (tree / "keep" / "big").write_bytes(b"x" * 200_000)
    (tree / "skip" / "bigger").write_bytes(b"x" * 400_000)

    whole = disk.du_bytes([tree], [])
    kept = disk.du_bytes([tree], [tree / "skip"])

    assert whole is not None and kept is not None
    assert whole >= 600_000 and 200_000 <= kept < 400_000
    assert disk.du_bytes([tmp_path / "missing"], []) == 0


def test_the_scanner_runs_one_walk_at_a_time_and_keeps_the_result_with_its_time() -> (
    None
):
    started = []
    scanner = disk.DiskScanner(
        run=lambda: (
            started.append(1),
            (
                [{"id": "other", "label": "x", "hint": "", "bytes": 1, "items": []}],
                ["caches"],
            ),
        )[1],
        clock=lambda: datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc),
    )

    assert scanner.snapshot() == {
        "state": "idle",
        "scanned_at": None,
        "rows": [],
        "missing": [],
    }
    assert scanner.start() is True
    scanner.wait(5.0)
    result = scanner.snapshot()

    assert result["state"] == "done"
    assert result["scanned_at"] == "2026-10-20T15:00:00+00:00"
    assert result["rows"][0]["id"] == "other" and result["missing"] == ["caches"]
    assert started == [1]


def test_a_walk_that_cannot_read_the_disk_ends_failed_rather_than_scanning() -> None:
    def run() -> tuple[list[dict[str, object]], list[str]]:
        raise OSError("no such disk")

    scanner = disk.DiskScanner(
        run=run, clock=lambda: datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)
    )

    assert scanner.start() is True
    scanner.wait(5.0)

    assert scanner.snapshot() == {
        "state": "failed",
        "scanned_at": "2026-10-20T15:00:00+00:00",
        "rows": [],
        "missing": [],
    }
    # A failed walk does not block the next one.
    assert scanner.start() is True
    scanner.wait(5.0)
