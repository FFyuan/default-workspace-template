import json
import os
import subprocess
import sys
from datetime import timedelta

import pytest

from imbue.imbue_common.model_update import to_update
from routines.data_types import CurrentRun
from routines.data_types import RoutineDefinition
from routines.data_types import RunFinishedEvent
from routines.data_types import RunStartedEvent
from routines.definitions import FileDefinitionStore
from routines.errors import DefinitionValidationError
from routines.errors import RunInFlightError
from routines.ledger import FileLedger
from routines.locks import held_lock
from routines.mock_chat_app_test import ScriptedChatApp
from routines.mock_clock_test import FakeClock
from routines.mock_notifier_test import RecordingNotifier
from routines.primitives import ChatStatusWord
from routines.primitives import RoutineId
from routines.primitives import RunId
from routines.primitives import RunOutcome
from routines.primitives import RunTrigger
from routines.primitives import RunWarning
from routines.runner import INTERRUPTED_SUMMARY
from routines.runner import Runner
from routines.state import FileStateStore

SYNC = RoutineId("nightly-sync")


def _command_routine(definitions: FileDefinitionStore, *command: str, **fields: object) -> None:
    values: dict[str, object] = {"title": "Nightly sync", "what": "Syncs.", "every": "1d", "command": list(command)}
    values.update(fields)
    definitions.add(SYNC, RoutineDefinition.model_validate(values))


def _skill_routine(definitions: FileDefinitionStore, **fields: object) -> None:
    values: dict[str, object] = {"title": "Morning digest", "what": "Digests.", "every": "1d", "skill": "digest"}
    values.update(fields)
    definitions.add(SYNC, RoutineDefinition.model_validate(values))


def test_a_command_run_streams_its_output_records_both_events_and_updates_the_state(
    runner: Runner, definitions: FileDefinitionStore, states: FileStateStore, ledger: FileLedger
) -> None:
    _command_routine(definitions, "sh", "-c", 'echo "hello from the run"; echo "stderr too" >&2')

    event = runner.run(SYNC, RunTrigger.MANUAL, None)

    assert event.outcome is RunOutcome.SUCCEEDED
    assert event.exit_code == 0
    assert "hello from the run" in event.output_tail
    assert "stderr too" in event.output_tail
    log = runner.paths.run_log_path(SYNC, event.run_id).read_text()
    assert "hello from the run" in log
    state = states.read(SYNC)
    assert state.current_run is None
    assert state.last_succeeded_at == runner.clock.now()
    assert state.consecutive_failures == 0
    assert state.last_run is not None
    assert state.last_run.run_id == event.run_id
    assert state.last_run.trigger is RunTrigger.MANUAL
    events = ledger.events_of_run(SYNC, event.run_id)
    assert isinstance(events[0], RunStartedEvent)
    assert isinstance(events[1], RunFinishedEvent)
    assert events[0].command == 'sh -c echo "hello from the run"; echo "stderr too" >&2'


def test_a_command_sees_its_run_directory_and_its_result_file_becomes_the_summary(
    runner: Runner, definitions: FileDefinitionStore
) -> None:
    script = 'printf \'{"summary": "3 things synced", "links": [{"label": "Note", "url": "/x"}]}\' > "$ROUTINES_RUN_DIR/result.json"'
    _command_routine(definitions, "sh", "-c", script)

    event = runner.run(SYNC, RunTrigger.SCHEDULED, None)

    assert event.summary == "3 things synced"
    assert runner.paths.result_path(SYNC, event.run_id).is_file()


def test_a_failing_command_counts_toward_the_streak_and_tells_the_feed_at_the_threshold(
    runner: Runner, definitions: FileDefinitionStore, states: FileStateStore, notifier: RecordingNotifier
) -> None:
    _command_routine(definitions, "sh", "-c", "echo boom; exit 3", notify_after_failures=2)

    first = runner.run(SYNC, RunTrigger.SCHEDULED, None)
    assert first.outcome is RunOutcome.FAILED
    assert first.exit_code == 3
    assert notifier.sent == []

    second = runner.run(SYNC, RunTrigger.SCHEDULED, None)
    assert second.outcome is RunOutcome.FAILED
    assert states.read(SYNC).consecutive_failures == 2
    assert notifier.sent == [(SYNC, "Nightly sync has failed 2 times in a row.")]

    runner.run(SYNC, RunTrigger.SCHEDULED, None)
    assert len(notifier.sent) == 1, "a streak notifies once"


def test_a_success_after_a_notified_streak_says_it_is_working_again(
    runner: Runner, definitions: FileDefinitionStore, notifier: RecordingNotifier, states: FileStateStore
) -> None:
    marker = runner.paths.repo_root / "fail-once"
    marker.write_text("")
    _command_routine(
        definitions, "sh", "-c", f'if [ -e "{marker}" ]; then rm "{marker}"; exit 1; fi', notify_after_failures=1
    )

    runner.run(SYNC, RunTrigger.SCHEDULED, None)
    runner.run(SYNC, RunTrigger.SCHEDULED, None)

    assert notifier.sent == [(SYNC, "Nightly sync has failed once."), (SYNC, "Nightly sync is working again.")]
    assert states.read(SYNC).is_failure_notified is False


def test_a_command_past_its_timeout_is_killed_with_its_whole_process_group(
    runner: Runner, definitions: FileDefinitionStore, states: FileStateStore
) -> None:
    pid_file = runner.paths.repo_root / "child.pid"
    _command_routine(definitions, "sh", "-c", f'sleep 73841 & echo $! > "{pid_file}"; wait', timeout="1s")

    event = runner.run(SYNC, RunTrigger.MANUAL, None)

    assert event.outcome is RunOutcome.TIMED_OUT
    child_pid = int(pid_file.read_text())
    with pytest.raises(OSError):
        os.kill(child_pid, 0)
    assert states.read(SYNC).consecutive_failures == 1


def test_a_second_run_is_refused_while_one_holds_the_lock(runner: Runner, definitions: FileDefinitionStore) -> None:
    _command_routine(definitions, "true")
    with held_lock(runner.paths.run_lock_path(SYNC), "A run"):
        with pytest.raises(RunInFlightError):
            runner.run(SYNC, RunTrigger.MANUAL, None)


def test_a_broken_definition_cannot_run(runner: Runner, definitions: FileDefinitionStore) -> None:
    (definitions.paths.definitions_dir / f"{SYNC}.toml").write_text('title = "x"\n')
    with pytest.raises(DefinitionValidationError):
        runner.run(SYNC, RunTrigger.MANUAL, None)


def test_a_skill_run_wakes_the_chat_and_records_it(
    runner: Runner, definitions: FileDefinitionStore, states: FileStateStore, chat_app: ScriptedChatApp
) -> None:
    _skill_routine(definitions)
    chat_app.script(
        "agent-created", (ChatStatusWord.WORKING, ChatStatusWord.IDLE), "Done: 3 messages summarized.\nMore."
    )

    event = runner.run(SYNC, RunTrigger.SCHEDULED, None)

    assert event.outcome is RunOutcome.SUCCEEDED
    assert event.summary == "Done: 3 messages summarized."
    assert event.chat_id == "agent-created"
    assert chat_app.created == [("Morning digest", SYNC, "/digest")]
    assert states.read(SYNC).chat_id == "agent-created"
    assert states.read(SYNC).last_run is not None


def test_a_skill_run_whose_agent_waits_on_the_user_is_recorded_blocked_and_notified(
    runner: Runner,
    definitions: FileDefinitionStore,
    chat_app: ScriptedChatApp,
    notifier: RecordingNotifier,
    ledger: FileLedger,
) -> None:
    _skill_routine(definitions)
    chat_app.script(
        "agent-created", (ChatStatusWord.WORKING, ChatStatusWord.ATTENTION, ChatStatusWord.IDLE), "Answered."
    )

    event = runner.run(SYNC, RunTrigger.SCHEDULED, None)

    assert event.outcome is RunOutcome.SUCCEEDED
    assert notifier.sent == [(SYNC, "Morning digest needs you.")]
    assert [type(e).__name__ for e in ledger.events_of_run(SYNC, event.run_id)] == [
        "RunStartedEvent",
        "RunBlockedEvent",
        "RunFinishedEvent",
    ]


def test_a_busy_chat_is_restarted_and_the_run_carries_the_warning(
    runner: Runner, definitions: FileDefinitionStore, states: FileStateStore, chat_app: ScriptedChatApp
) -> None:
    _skill_routine(definitions)
    states.update(SYNC, lambda state: state.model_copy_update(to_update(state.field_ref().chat_id, "agent-old")))
    chat_app.script(
        "agent-old", (ChatStatusWord.WORKING, ChatStatusWord.WORKING, ChatStatusWord.IDLE, ChatStatusWord.IDLE), "ok"
    )

    event = runner.run(SYNC, RunTrigger.SCHEDULED, None)

    assert event.outcome is RunOutcome.SUCCEEDED
    assert event.warnings == (RunWarning.RESTARTED_PREVIOUS_RUN,)
    assert chat_app.verbs == [("agent-old", "stop"), ("agent-old", "start")]
    assert chat_app.sent == [("agent-old", "/clear"), ("agent-old", "/digest")]


def test_the_tick_closes_off_a_run_whose_process_is_gone(
    runner: Runner, definitions: FileDefinitionStore, states: FileStateStore, ledger: FileLedger, clock: FakeClock
) -> None:
    _command_routine(definitions, "true", enabled=False)
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    run_id = RunId.generate()
    states.update(
        SYNC,
        lambda state: state.model_copy_update(
            to_update(
                state.field_ref().current_run,
                CurrentRun(run_id=run_id, pid=dead.pid, trigger=RunTrigger.SCHEDULED, started_at=clock.now()),
            )
        ),
    )

    report = runner.tick()

    assert report.reaped == (SYNC,)
    assert report.started == ()
    state = states.read(SYNC)
    assert state.current_run is None
    assert state.last_run is not None
    assert state.last_run.outcome is RunOutcome.INTERRUPTED
    assert state.last_run.summary == INTERRUPTED_SUMMARY
    finished = ledger.events_of_run(SYNC, run_id)[-1]
    assert isinstance(finished, RunFinishedEvent)
    assert finished.outcome is RunOutcome.INTERRUPTED


def test_the_tick_skips_a_routine_that_is_off_or_not_due(
    runner: Runner, definitions: FileDefinitionStore, states: FileStateStore, clock: FakeClock
) -> None:
    _command_routine(definitions, "true", enabled=False)
    assert runner.tick().started == ()
    states.update(SYNC, lambda state: state.model_copy_update(to_update(state.field_ref().is_enabled, True)))
    states.update(
        SYNC, lambda state: state.model_copy_update(to_update(state.field_ref().last_succeeded_at, clock.now()))
    )
    assert runner.tick().started == ()


def test_the_tick_keeps_house_once_a_day(runner: Runner, definitions: FileDefinitionStore, clock: FakeClock) -> None:
    _command_routine(definitions, "true", enabled=False)
    runner.tick()
    stamp = json.loads(runner.paths.housekeeping_path.read_text())
    assert stamp == {"date": "2026-10-20"}
    old_run = runner.paths.run_dir(SYNC, RunId.generate())
    old_run.mkdir(parents=True)
    ninety_one_days_ago = (clock.now() - timedelta(days=91)).timestamp()
    os.utime(old_run, (ninety_one_days_ago, ninety_one_days_ago))

    runner.tick()
    assert old_run.exists(), "housekeeping ran today already"

    clock.advance(timedelta(days=1))
    runner.tick()
    assert not old_run.exists()
