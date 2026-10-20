import pytest

from routines.errors import InvalidRoutineIdError
from routines.primitives import LEDGER_DIRNAME
from routines.primitives import RoutineId


def test_the_ledgers_directory_name_is_not_a_routine_id() -> None:
    """A routine of that name would have the run ledger's directory as its state, and remove it with itself."""
    with pytest.raises(InvalidRoutineIdError, match="run ledger"):
        RoutineId(LEDGER_DIRNAME)
    assert RoutineId("events-digest") == "events-digest"
