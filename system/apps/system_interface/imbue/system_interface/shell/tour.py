"""Whether the workspace's show-around tour has run (the new-onboarding spec, section 3.4): one flag in ``tour.json``
under the shell's state directory. Absent or unusable means it has not, so a fresh workspace offers the tour once."""

from pathlib import Path
from typing import Final

from loguru import logger
from pydantic import Field
from pydantic import ValidationError

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.mutable_model import MutableModel
from imbue.system_interface.shell.state_files import STATE_FILES_LOCK
from imbue.system_interface.shell.state_files import read_json_object
from imbue.system_interface.shell.state_files import write_json_atomic

TOUR_FILENAME: Final[str] = "tour.json"
TOUR_FILE_VERSION: Final[int] = 1
TOUR_ROUTE: Final[str] = "/api/tour"


class TourRecord(FrozenModel):
    """The body of ``POST /api/tour`` and the answer of both tour routes."""

    is_seen: bool = Field(description="Whether the tour has started in this workspace, by itself or from the launcher")


class _TourDocument(FrozenModel):
    """The whole of ``tour.json``."""

    version: int = Field(description="The file format version")
    is_seen: bool = Field(description="Whether the tour has started in this workspace")


class TourStore(MutableModel):
    """Reads and writes ``tour.json`` under the shell's state lock."""

    state_directory: Path = Field(frozen=True, description="The shell's state directory")

    def _path(self) -> Path:
        return self.state_directory / TOUR_FILENAME

    def read(self) -> bool:
        """Whether the tour has run; False when nothing usable is stored (logged)."""
        with STATE_FILES_LOCK:
            raw = read_json_object(self._path())
        if raw is None:
            return False
        try:
            document = _TourDocument.model_validate(raw)
        except ValidationError as e:
            logger.warning("Ignored an unreadable tour record at {}: {}", self._path(), e.errors()[0]["msg"])
            return False
        if document.version != TOUR_FILE_VERSION:
            logger.warning("Ignored a tour record of version {!r} at {}", document.version, self._path())
            return False
        return document.is_seen

    def write(self, is_seen: bool) -> None:
        with STATE_FILES_LOCK:
            write_json_atomic(self._path(), _TourDocument(version=TOUR_FILE_VERSION, is_seen=is_seen).model_dump(mode="json"))
