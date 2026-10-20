import json
import shutil
from collections.abc import Callable

from loguru import logger
from pydantic import ValidationError

from routines.data_types import RoutineState
from routines.interfaces import StateStoreInterface
from routines.locks import waited_lock
from routines.primitives import RoutineId


class FileStateStore(StateStoreInterface):
    """One JSON file per routine, rewritten whole under the routine's state lock."""

    def read(self, routine_id: RoutineId) -> RoutineState:
        path = self.paths.state_path(routine_id)
        if not path.is_file():
            return RoutineState()
        try:
            return RoutineState.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, ValidationError) as e:
            logger.warning(
                "Starting {} from a fresh state: its state file could not be read ({})",
                routine_id,
                e,
            )
            return RoutineState()

    def update(self, routine_id: RoutineId, transform: Callable[[RoutineState], RoutineState]) -> RoutineState:
        with waited_lock(self.paths.state_lock_path(routine_id)):
            updated = transform(self.read(routine_id))
            path = self.paths.state_path(routine_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(updated.model_dump(mode="json"), indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(path)
            return updated

    def remove(self, routine_id: RoutineId) -> None:
        shutil.rmtree(self.paths.routine_state_dir(routine_id), ignore_errors=True)
