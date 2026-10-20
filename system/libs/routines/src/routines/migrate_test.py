from datetime import datetime
from datetime import timezone
from pathlib import Path

from inline_snapshot import snapshot

from routines.definitions import FileDefinitionStore
from routines.errors import DefinitionCommitError
from routines.migrate import ConvertedEntry
from routines.migrate import SkippedEntry
from routines.migrate import convert_cron_entry
from routines.migrate import migrate_cron_entries
from routines.mock_repository_test import RecordingRepository
from routines.paths import RoutinesPaths
from routines.primitives import RoutineId
from routines.primitives import Weekday
from routines.state import FileStateStore

WRAPPER = "/home/user/workspace/system/libs/automations/with_agent_env.sh"
RUN_JOB = "/home/user/workspace/system/libs/automations/run_job.sh"
RUN_AUTOMATION = "/home/user/workspace/system/libs/automations/run_automation.sh"


def test_a_runner_entry_becomes_a_command_routine_with_its_cadence_and_hour() -> None:
    line = f"* * * * *   root   {WRAPPER} {RUN_JOB} news-sync --every 1d --at 7 --retry-after 5m python3 sync.py --all >> /var/log/supervisor/news.log 2>&1\n"
    (converted,) = convert_cron_entry(line, "news-sync")
    assert isinstance(converted, ConvertedEntry)
    assert converted.routine_id == RoutineId("news-sync")
    assert converted.definition.model_dump(mode="json") == snapshot(
        {
            "title": "News sync",
            "what": "python3 sync.py --all",
            "every": "1d",
            "at": "07:00",
            "days": [],
            "day_of_month": None,
            "once": None,
            "command": ["python3", "sync.py", "--all"],
            "skill": None,
            "enabled": True,
            "timeout": "1h",
            "retry_after": "5m",
            "notify_after_failures": 3,
            "app": None,
        }
    )


def test_an_automation_entry_becomes_a_skill_routine() -> None:
    line = f"* * * * *   root   {WRAPPER} {RUN_JOB} news --every 1d --at 9 bash {RUN_AUTOMATION} news >> /var/log/supervisor/news-job.log 2>&1\n"
    (converted,) = convert_cron_entry(line, "news")
    assert isinstance(converted, ConvertedEntry)
    assert converted.definition.skill == "news"
    assert converted.definition.command is None


def test_an_automation_entry_with_the_scripts_options_still_names_the_skill() -> None:
    line = f"* * * * * root {WRAPPER} {RUN_JOB} news --every 1d bash {RUN_AUTOMATION} --template caretaker --type claude news\n"
    (converted,) = convert_cron_entry(line, "news")
    assert isinstance(converted, ConvertedEntry)
    assert converted.definition.skill == "news"


def test_the_caretaker_entry_is_recognized_as_the_switch_on_the_shipped_routine() -> None:
    line = f"* * * * *   root   {WRAPPER} {RUN_JOB} caretaker --every 7d --at 3 bash /home/user/workspace/system/services/caretaker/caretaker_check.sh >> /var/log/supervisor/caretaker-job.log 2>&1\n"
    (converted,) = convert_cron_entry(line, "minds-caretaker")
    assert isinstance(converted, ConvertedEntry)
    assert converted.is_caretaker_switch


def test_plain_cron_lines_in_the_shapes_a_definition_can_say_are_converted() -> None:
    cases = {
        "*/15 * * * * root cmd": ("15m", None, ()),
        "0 */2 * * * root cmd": ("2h", None, ()),
        "30 9 * * * root cmd": ("1d", "09:30", ()),
        "30 9 * * 1 root cmd": ("1d", "09:30", (Weekday.MON,)),
        "0 0 1 * * root cmd": ("1mo", "00:00", ()),
    }
    for line, (every, at, days) in cases.items():
        (converted,) = convert_cron_entry(line + "\n", "weekly_report")
        assert isinstance(converted, ConvertedEntry), line
        assert str(converted.definition.every) == every
        assert converted.definition.at == at
        assert converted.definition.days == days
        assert converted.routine_id == RoutineId("weekly-report")


def test_a_cron_shape_with_no_routine_form_is_left_with_a_reason() -> None:
    (skipped,) = convert_cron_entry("0 0 1 6 * root cmd\n", "june")
    assert isinstance(skipped, SkippedEntry)
    assert skipped.reason == "a schedule naming a month has no routine form"


def test_migration_writes_definitions_carries_state_over_and_removes_both_copies(
    definitions: FileDefinitionStore, states: FileStateStore, tmp_path: Path
) -> None:
    root = definitions.paths.repo_root
    durable = root / "data" / ".state" / "cron.d"
    durable.mkdir(parents=True)
    live = tmp_path / "etc-cron-d"
    live.mkdir()
    entry = f"* * * * * root {WRAPPER} {RUN_JOB} news-sync --every 6h python3 sync.py >> /var/log/x.log 2>&1\n"
    (durable / "news-sync").write_text(entry)
    (live / "news-sync").write_text(entry)
    caretaker = f"* * * * * root {WRAPPER} {RUN_JOB} caretaker --every 7d --at 3 bash /x/caretaker_check.sh >> /var/log/c.log 2>&1\n"
    (durable / "minds-caretaker").write_text(caretaker)
    (durable / "june").write_text("0 0 1 6 * root cmd\n")
    job_state = root / "data" / ".state" / "jobs" / "news-sync"
    job_state.mkdir(parents=True)
    (job_state / "last_success").write_text("1760000000\n")
    (job_state / "failures").write_text("2\n")

    report = migrate_cron_entries(root, definitions, states, live_cron_dir=live)

    assert report.converted == (RoutineId("news-sync"),)
    assert report.enabled_caretaker is True
    assert [skipped.file_name for skipped in report.skipped] == ["june"]
    assert definitions.load(RoutineId("news-sync")).definition is not None
    assert not (durable / "news-sync").exists()
    assert not (live / "news-sync").exists()
    assert not (durable / "minds-caretaker").exists()
    assert (durable / "june").exists()
    state = states.read(RoutineId("news-sync"))
    assert state.last_succeeded_at == datetime.fromtimestamp(1760000000, tz=timezone.utc)
    assert state.consecutive_failures == 2
    assert states.read(RoutineId("caretaker")).is_enabled is True

    again = migrate_cron_entries(root, definitions, states, live_cron_dir=live)
    assert again.converted == ()


class RefusingRepository(RecordingRepository):
    """A repository whose index another writer holds for good."""

    def commit_path(self, path: Path, message: str) -> None:
        raise DefinitionCommitError("locked")


def test_an_entry_whose_commit_is_refused_is_still_converted_with_its_state(
    paths: RoutinesPaths, states: FileStateStore, tmp_path: Path
) -> None:
    root = paths.repo_root
    durable = root / "data" / ".state" / "cron.d"
    durable.mkdir(parents=True)
    (durable / "news-sync").write_text(
        f"* * * * * root {WRAPPER} {RUN_JOB} news-sync --every 6h python3 sync.py >> /var/log/x.log 2>&1\n"
    )
    job_state = root / "data" / ".state" / "jobs" / "news-sync"
    job_state.mkdir(parents=True)
    (job_state / "failures").write_text("2\n")
    definitions = FileDefinitionStore(paths=paths, repository=RefusingRepository(repo_root=root))

    report = migrate_cron_entries(root, definitions, states, live_cron_dir=tmp_path / "etc-cron-d")

    assert report.converted == (RoutineId("news-sync"),)
    assert definitions.load(RoutineId("news-sync")).definition is not None
    assert states.read(RoutineId("news-sync")).consecutive_failures == 2
    assert not (durable / "news-sync").exists()
