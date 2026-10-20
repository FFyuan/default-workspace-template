from pydantic import Field

from routines.data_types import RoutineState
from routines.errors import StateRemovalError
from routines.primitives import RoutineId
from routines.state import FileStateStore


class RefusingRemovalStateStore(FileStateStore):
    """A state store whose directories cannot be deleted whole, as a file the process may not remove leaves them."""

    def remove(self, routine_id: RoutineId) -> None:
        raise StateRemovalError(f"Could not remove all of the state of {routine_id}: a file could not be deleted")


class OneRefusingStateStore(FileStateStore):
    """A state store whose file for one routine cannot be opened."""

    refused_id: RoutineId = Field(description="The routine whose state read fails")

    def read(self, routine_id: RoutineId) -> RoutineState:
        if routine_id == self.refused_id:
            raise PermissionError(f"{routine_id}: state.json is not readable")
        return super().read(routine_id)


class StaleReadStateStore(FileStateStore):
    """Answers one read with a state read just before the run finished, as a reaper racing the run sees it."""

    stale: RoutineState | None = Field(default=None, description="The state the next read answers, once")

    def read(self, routine_id: RoutineId) -> RoutineState:
        if self.stale is not None:
            stale, self.stale = self.stale, None
            return stale
        return super().read(routine_id)
