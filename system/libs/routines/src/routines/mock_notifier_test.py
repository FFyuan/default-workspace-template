from pydantic import Field

from routines.interfaces import NotifierInterface
from routines.primitives import RoutineId


class RecordingNotifier(NotifierInterface):
    """Keeps every notification instead of sending it."""

    sent: list[tuple[RoutineId, str]] = Field(default_factory=list, description="Every notification, in order")
    is_accepting: bool = Field(default=True, description="What the app answers")

    def notify(self, message: str, routine_id: RoutineId) -> bool:
        self.sent.append((routine_id, message))
        return self.is_accepting
