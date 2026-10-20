from datetime import datetime

import pytest
from inline_snapshot import snapshot
from pydantic import ValidationError

from imbue.imbue_common.model_update import to_update
from routines.data_types import RoutineDefinition
from routines.definitions import FileDefinitionStore
from routines.errors import RoutineExistsError
from routines.errors import RoutineNotFoundError
from routines.mock_repository_test import RecordingRepository
from routines.primitives import RoutineId
from routines.primitives import TimeOfDay
from routines.primitives import Weekday

DIGEST = RoutineId("inbox-digest")


def _digest() -> RoutineDefinition:
    return RoutineDefinition.model_validate(
        {
            "title": "Morning inbox digest",
            "what": "Reads new mail.",
            "every": "1d",
            "at": "07:30",
            "skill": "inbox-digest",
        }
    )


def test_adding_a_routine_writes_its_file_without_the_defaults_and_commits_it(
    definitions: FileDefinitionStore, repository: RecordingRepository
) -> None:
    path = definitions.add(DIGEST, _digest())

    assert path.read_text() == snapshot("""\
title = "Morning inbox digest"
what = "Reads new mail."
every = "1d"
at = "07:30"
skill = "inbox-digest"
""")
    assert repository.commits == [(path, "routines: add inbox-digest")]
    assert definitions.load(DIGEST).definition == _digest()


def test_adding_a_routine_that_exists_is_refused(definitions: FileDefinitionStore) -> None:
    definitions.add(DIGEST, _digest())
    with pytest.raises(RoutineExistsError):
        definitions.add(DIGEST, _digest())


def test_replacing_a_routine_keeps_the_comments_an_agent_left(
    definitions: FileDefinitionStore, repository: RecordingRepository
) -> None:
    path = definitions.add(DIGEST, _digest())
    path.write_text("# The user asked for this on a Tuesday.\n" + path.read_text())

    definition = _digest()
    changed = definition.model_copy_update(
        to_update(definition.field_ref().at, TimeOfDay("08:00")),
        to_update(definition.field_ref().days, (Weekday.MON,)),
    )
    definitions.replace(DIGEST, changed, "change the schedule")

    assert path.read_text() == snapshot("""\
# The user asked for this on a Tuesday.
title = "Morning inbox digest"
what = "Reads new mail."
every = "1d"
at = "08:00"
skill = "inbox-digest"
days = ["mon"]
""")
    assert repository.commits[-1] == (path, "routines: change the schedule of inbox-digest")


def test_a_broken_file_is_listed_with_its_reason_and_never_raises(definitions: FileDefinitionStore) -> None:
    (definitions.paths.definitions_dir / "broken.toml").write_text(
        'title = "No what"\nevery = "1d"\ncommand = ["true"]\n'
    )
    (definitions.paths.definitions_dir / "garbled.toml").write_text("title = \n")

    listed = {loaded.routine_id: loaded for loaded in definitions.list_routines()}

    assert listed[RoutineId("broken")].definition is None
    assert listed[RoutineId("broken")].error == snapshot("what: Field required")
    garbled_error = listed[RoutineId("garbled")].error
    assert garbled_error is not None
    assert garbled_error.startswith("not valid TOML")


def test_loading_a_routine_that_does_not_exist_raises(definitions: FileDefinitionStore) -> None:
    with pytest.raises(RoutineNotFoundError):
        definitions.load(RoutineId("nothing"))


def test_removing_a_routine_deletes_the_file_and_commits_the_deletion(
    definitions: FileDefinitionStore, repository: RecordingRepository
) -> None:
    path = definitions.add(DIGEST, _digest())
    definitions.remove(DIGEST)
    assert not path.exists()
    assert repository.commits[-1] == (path, "routines: remove inbox-digest")


@pytest.mark.parametrize(
    ("fields", "problem"),
    [
        (
            {"every": "1d", "once": datetime(2026, 11, 3, 15, 0), "command": ["true"]},
            "exactly one of 'every' and 'once'",
        ),
        ({"every": "1d", "command": ["true"], "skill": "x"}, "exactly one of 'command' and 'skill'"),
        ({"every": "1d", "command": []}, "at least one word"),
        ({"every": "15m", "at": "07:00", "command": ["true"]}, "a day or longer"),
        ({"every": "90s", "command": ["true"]}, "minutes, hours, days, weeks or months"),
        ({"every": "1d", "day_of_month": 3, "command": ["true"]}, "a cadence in months"),
        ({"once": datetime(2026, 11, 3, 15, 0), "at": "07:00", "command": ["true"]}, "go with 'every'"),
        ({"every": "1d", "timeout": "1mo", "command": ["true"]}, "fixed lengths"),
    ],
)
def test_a_definition_that_says_two_things_at_once_is_refused_with_a_reason(
    fields: dict[str, object], problem: str
) -> None:
    with pytest.raises(ValidationError, match=problem):
        RoutineDefinition.model_validate({"title": "T", "what": "W", **fields})


def test_weekdays_are_read_in_any_case() -> None:
    definition = RoutineDefinition.model_validate(
        {"title": "T", "what": "W", "every": "1d", "days": ["Mon", "FRI"], "command": ["true"]}
    )
    assert definition.days == (Weekday.MON, Weekday.FRI)
