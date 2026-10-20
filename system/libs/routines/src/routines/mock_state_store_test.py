from routines.errors import StateRemovalError
from routines.primitives import RoutineId
from routines.state import FileStateStore


class RefusingRemovalStateStore(FileStateStore):
    """A state store whose directories cannot be deleted whole, as a file the process may not remove leaves them."""

    def remove(self, routine_id: RoutineId) -> None:
        raise StateRemovalError(f"Could not remove all of the state of {routine_id}: a file could not be deleted")
