import threading
from datetime import datetime
from datetime import timezone
from datetime import tzinfo

from routines.interfaces import ClockInterface


class SystemClock(ClockInterface):
    """The machine's clock and zone; a pause is an uncontested wait on an event nobody sets."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def local_zone(self) -> tzinfo:
        zone = datetime.now().astimezone().tzinfo
        assert zone is not None
        return zone

    def pause(self, seconds: float) -> None:
        threading.Event().wait(seconds)
