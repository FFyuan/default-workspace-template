"""Tests for the workspace's tour record."""

import json
from pathlib import Path

from imbue.system_interface.shell.tour import TOUR_FILENAME
from imbue.system_interface.shell.tour import TourStore


def test_the_tour_record_defaults_to_unseen_and_round_trips(tmp_path: Path) -> None:
    store = TourStore(state_directory=tmp_path)
    assert store.read() is False
    store.write(True)
    assert store.read() is True
    assert json.loads((tmp_path / TOUR_FILENAME).read_text()) == {"version": 1, "is_seen": True}
    store.write(False)
    assert store.read() is False


def test_an_unreadable_or_foreign_tour_record_reads_as_unseen(tmp_path: Path) -> None:
    store = TourStore(state_directory=tmp_path)
    (tmp_path / TOUR_FILENAME).write_text("{not json")
    assert store.read() is False
    (tmp_path / TOUR_FILENAME).write_text(json.dumps({"version": 2, "is_seen": True}))
    assert store.read() is False
    (tmp_path / TOUR_FILENAME).write_text(json.dumps({"version": 1, "is_seen": "not a flag"}))
    assert store.read() is False
