"""The runner: one run of a routine, the once-a-minute tick that starts the due ones, and the housekeeping."""

import json
import os
import signal
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Final

from loguru import logger
from pydantic import Field
from pydantic import ValidationError

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.logging import format_nanosecond_iso_timestamp
from imbue.imbue_common.logging import generate_log_event_id
from imbue.imbue_common.model_update import to_update
from imbue.imbue_common.mutable_model import MutableModel
from imbue.imbue_common.primitives import NonNegativeInt
from imbue.imbue_common.pure import pure
from routines.data_types import CurrentRun
from routines.data_types import LastRun
from routines.data_types import RUN_BLOCKED_EVENT
from routines.data_types import RUN_EVENTS_SOURCE
from routines.data_types import RUN_FINISHED_EVENT
from routines.data_types import RUN_STARTED_EVENT
from routines.data_types import RoutineDefinition
from routines.data_types import RoutineState
from routines.data_types import RunBlockedEvent
from routines.data_types import RunFinishedEvent
from routines.data_types import RunResult
from routines.data_types import RunStartedEvent
from routines.errors import DefinitionValidationError
from routines.errors import RunInFlightError
from routines.interfaces import ChatAppInterface
from routines.interfaces import ClockInterface
from routines.interfaces import DefinitionStoreInterface
from routines.interfaces import LedgerInterface
from routines.interfaces import NotifierInterface
from routines.interfaces import StateStoreInterface
from routines.locks import held_lock
from routines.locks import is_lock_held
from routines.paths import RoutinesPaths
from routines.presentation import is_switched_on
from routines.primitives import RoutineId
from routines.primitives import RunId
from routines.primitives import RunKind
from routines.primitives import RunOutcome
from routines.primitives import RunTrigger
from routines.primitives import RunWarning
from routines.schedule import next_due
from routines.wake import WakeOutcome
from routines.wake import slash_command_of
from routines.wake import wake_skill

OUTPUT_TAIL_BYTES: Final[int] = 4096
# After the timeout the process group is asked to stop, then killed if it has not.
TERMINATE_GRACE_SECONDS: Final[float] = 5.0
RUN_DIR_RETENTION: Final[timedelta] = timedelta(days=90)
INTERRUPTED_SUMMARY: Final[str] = "The run was cut off before it finished, most likely by a restart."
TIMED_OUT_SUMMARY: Final[str] = "The run was stopped because it took longer than its time limit."
RUN_DIR_ENV: Final[str] = "ROUTINES_RUN_DIR"
RUN_ID_ENV: Final[str] = "ROUTINES_RUN_ID"
ROUTINE_ID_ENV: Final[str] = "ROUTINES_ROUTINE_ID"
_TIMED_OUT_EXIT_CODE: Final[int] = 124


class TickReport(FrozenModel):
    """What one tick did."""

    started: tuple[RoutineId, ...] = Field(description="The routines whose runs it spawned")
    reaped: tuple[RoutineId, ...] = Field(description="The routines whose dead runs it closed off")
    is_skipped: bool = Field(description="Whether another tick held the lock")


class _Execution(FrozenModel):
    """What running the routine's work produced, before the books are closed."""

    outcome: RunOutcome
    exit_code: int | None
    summary: str
    chat_id: str | None
    warnings: tuple[RunWarning, ...]


def _envelope(event_type: str, now: datetime) -> dict[str, str]:
    return {
        "timestamp": format_nanosecond_iso_timestamp(now),
        "type": event_type,
        "event_id": generate_log_event_id(),
        "source": RUN_EVENTS_SOURCE,
    }


@pure
def read_output_tail(log_path: Path) -> str:
    try:
        with log_path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - OUTPUT_TAIL_BYTES))
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def is_run_process_alive(pid: int, routine_id: RoutineId) -> bool:
    """Whether the pid is still this routine's runner; a reused pid never passes."""
    cmdline_path = Path(f"/proc/{pid}/cmdline")
    if cmdline_path.exists():
        try:
            cmdline = cmdline_path.read_bytes()
        except OSError:
            return False
        return b"routines" in cmdline and b"run" in cmdline and routine_id.encode() in cmdline
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class Runner(MutableModel):
    """Runs routines and ticks the schedule, over the stores and services it is given."""

    paths: RoutinesPaths = Field(frozen=True, description="Where everything lives")
    definitions: DefinitionStoreInterface = Field(frozen=True, description="The definition files")
    states: StateStoreInterface = Field(frozen=True, description="The state files")
    ledger: LedgerInterface = Field(frozen=True, description="The run events")
    chat_app: ChatAppInterface = Field(frozen=True, description="The chat app, for skill runs")
    notifier: NotifierInterface = Field(frozen=True, description="The feed")
    clock: ClockInterface = Field(frozen=True, description="The time")

    def run(self, routine_id: RoutineId, trigger: RunTrigger, run_id: RunId | None) -> RunFinishedEvent:
        """One run, start to finish; raises RunInFlightError when one is already going."""
        loaded = self.definitions.load(routine_id)
        if loaded.definition is None:
            raise DefinitionValidationError(f"{routine_id} cannot run: {loaded.error}")
        definition = loaded.definition
        with held_lock(self.paths.run_lock_path(routine_id), f"A run of {routine_id}"):
            if run_id is None:
                run_id = RunId.generate()
            run_dir = self.paths.run_dir(routine_id, run_id)
            run_dir.mkdir(parents=True, exist_ok=True)
            started_at = self.clock.now()
            self._record_start(routine_id, run_id, definition, trigger, started_at)
            execution = self._execute(routine_id, run_id, definition, run_dir)
            finished_at = self.clock.now()
            return self._record_finish(
                routine_id,
                run_id,
                definition,
                trigger,
                started_at,
                finished_at,
                execution,
            )

    def _record_start(
        self,
        routine_id: RoutineId,
        run_id: RunId,
        definition: RoutineDefinition,
        trigger: RunTrigger,
        now: datetime,
    ) -> None:
        command = " ".join(definition.command) if definition.command else slash_command_of(str(definition.skill))
        self.ledger.append(
            RunStartedEvent(
                **_envelope(RUN_STARTED_EVENT, now),
                routine_id=routine_id,
                run_id=run_id,
                trigger=trigger,
                kind=definition.kind,
                command=command,
            )
        )
        current = CurrentRun(run_id=run_id, pid=os.getpid(), trigger=trigger, started_at=now)
        self.states.update(
            routine_id,
            lambda state: state.model_copy_update(
                to_update(state.field_ref().current_run, current),
                to_update(state.field_ref().last_started_at, now),
            ),
        )

    def _execute(
        self,
        routine_id: RoutineId,
        run_id: RunId,
        definition: RoutineDefinition,
        run_dir: Path,
    ) -> _Execution:
        if definition.skill is not None:
            return self._execute_skill(routine_id, run_id, definition)
        assert definition.command is not None
        return self._execute_command(
            routine_id,
            run_id,
            definition.command,
            definition.timeout.timedelta,
            run_dir,
        )

    def _execute_command(
        self,
        routine_id: RoutineId,
        run_id: RunId,
        command: tuple[str, ...],
        timeout: timedelta,
        run_dir: Path,
    ) -> _Execution:
        log_path = self.paths.run_log_path(routine_id, run_id)
        environment = {
            **os.environ,
            RUN_DIR_ENV: str(run_dir),
            RUN_ID_ENV: str(run_id),
            ROUTINE_ID_ENV: str(routine_id),
        }
        with log_path.open("ab") as log_handle:
            try:
                process = subprocess.Popen(
                    list(command),
                    cwd=self.paths.repo_root,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                    env=environment,
                )
            except OSError as e:
                log_handle.write(f"could not start the command: {e}\n".encode())
                return _Execution(
                    outcome=RunOutcome.FAILED,
                    exit_code=127,
                    summary=str(e),
                    chat_id=None,
                    warnings=(),
                )
            try:
                exit_code = process.wait(timeout=timeout.total_seconds())
            except subprocess.TimeoutExpired:
                _stop_process_group(process)
                log_handle.write(f"\n{TIMED_OUT_SUMMARY}\n".encode())
                return _Execution(
                    outcome=RunOutcome.TIMED_OUT,
                    exit_code=_TIMED_OUT_EXIT_CODE,
                    summary=TIMED_OUT_SUMMARY,
                    chat_id=None,
                    warnings=(),
                )
        result = _read_result(self.paths.result_path(routine_id, run_id))
        outcome = RunOutcome.SUCCEEDED if exit_code == 0 else RunOutcome.FAILED
        summary = result.summary or ""
        return _Execution(
            outcome=outcome,
            exit_code=exit_code,
            summary=summary,
            chat_id=result.chat_id,
            warnings=(),
        )

    def _execute_skill(self, routine_id: RoutineId, run_id: RunId, definition: RoutineDefinition) -> _Execution:
        assert definition.skill is not None
        state = self.states.read(routine_id)

        def on_blocked() -> None:
            self.ledger.append(
                RunBlockedEvent(
                    **_envelope(RUN_BLOCKED_EVENT, self.clock.now()),
                    routine_id=routine_id,
                    run_id=run_id,
                )
            )
            self.states.update(routine_id, _mark_current_run_blocked)
            self.notifier.notify(f"{definition.title} needs you.", routine_id)

        def on_chat_known(chat_id: str) -> None:
            self.states.update(
                routine_id,
                lambda current: current.model_copy_update(to_update(current.field_ref().chat_id, chat_id)),
            )

        wake: WakeOutcome = wake_skill(
            routine_id=routine_id,
            title=str(definition.title),
            skill=str(definition.skill),
            known_chat_id=state.chat_id,
            timeout=definition.timeout.timedelta,
            chat_app=self.chat_app,
            clock=self.clock,
            on_blocked=on_blocked,
            on_chat_known=on_chat_known,
        )
        log_path = self.paths.run_log_path(routine_id, run_id)
        with log_path.open("a", encoding="utf-8") as log_handle:
            log_handle.write(f"{wake.outcome.lower()}: {wake.summary}\n")
        return _Execution(
            outcome=wake.outcome,
            exit_code=None,
            summary=wake.summary,
            chat_id=wake.chat_id,
            warnings=wake.warnings,
        )

    def _record_finish(
        self,
        routine_id: RoutineId,
        run_id: RunId,
        definition: RoutineDefinition,
        trigger: RunTrigger,
        started_at: datetime,
        finished_at: datetime,
        execution: _Execution,
    ) -> RunFinishedEvent:
        duration = (finished_at - started_at).total_seconds()
        event = RunFinishedEvent(
            **_envelope(RUN_FINISHED_EVENT, finished_at),
            routine_id=routine_id,
            run_id=run_id,
            outcome=execution.outcome,
            exit_code=execution.exit_code,
            duration_seconds=duration,
            summary=execution.summary,
            chat_id=execution.chat_id,
            warnings=execution.warnings,
            output_tail=read_output_tail(self.paths.run_log_path(routine_id, run_id)),
        )
        self.ledger.append(event)
        last_run = LastRun(
            run_id=run_id,
            trigger=trigger,
            kind=definition.kind,
            outcome=execution.outcome,
            summary=execution.summary,
            started_at=started_at,
            finished_at=finished_at,
        )
        is_success = execution.outcome is RunOutcome.SUCCEEDED

        def close_books(state: RoutineState) -> RoutineState:
            failures = NonNegativeInt(0) if is_success else NonNegativeInt(int(state.consecutive_failures) + 1)
            updates = [
                to_update(state.field_ref().current_run, None),
                to_update(state.field_ref().last_run, last_run),
                to_update(state.field_ref().consecutive_failures, failures),
            ]
            if is_success:
                updates.append(to_update(state.field_ref().last_succeeded_at, finished_at))
            if execution.chat_id is not None:
                updates.append(to_update(state.field_ref().chat_id, execution.chat_id))
            return state.model_copy_update(*updates)

        state = self.states.update(routine_id, close_books)
        self._notify_after_run(routine_id, definition, state)
        return event

    def _notify_after_run(self, routine_id: RoutineId, definition: RoutineDefinition, state: RoutineState) -> None:
        failures = int(state.consecutive_failures)
        threshold = int(definition.notify_after_failures)
        if failures == 0 and state.is_failure_notified:
            self.notifier.notify(f"{definition.title} is working again.", routine_id)
            self.states.update(
                routine_id,
                lambda current: current.model_copy_update(to_update(current.field_ref().is_failure_notified, False)),
            )
        elif failures > 0 and threshold > 0 and failures >= threshold and not state.is_failure_notified:
            times = "once" if failures == 1 else f"{failures} times in a row"
            self.notifier.notify(f"{definition.title} has failed {times}.", routine_id)
            self.states.update(
                routine_id,
                lambda current: current.model_copy_update(to_update(current.field_ref().is_failure_notified, True)),
            )

    def tick(self) -> TickReport:
        """Section 6.1 of the spec: reap, start what is due, keep house once a day."""
        try:
            with held_lock(self.paths.tick_lock_path, "A tick"):
                reaped = self._reap_dead_runs()
                started = self._start_due_runs()
                self._housekeep()
                return TickReport(started=tuple(started), reaped=tuple(reaped), is_skipped=False)
        except RunInFlightError:
            return TickReport(started=(), reaped=(), is_skipped=True)

    def _reap_dead_runs(self) -> list[RoutineId]:
        reaped: list[RoutineId] = []
        for loaded in self.definitions.list_routines():
            routine_id = loaded.routine_id
            state = self.states.read(routine_id)
            current = state.current_run
            if current is None or is_run_process_alive(current.pid, routine_id):
                continue
            if is_lock_held(self.paths.run_lock_path(routine_id)):
                continue
            logger.warning(
                "Closing off the run {} of {}: its process is gone",
                current.run_id,
                routine_id,
            )
            now = self.clock.now()
            self.ledger.append(
                RunFinishedEvent(
                    **_envelope(RUN_FINISHED_EVENT, now),
                    routine_id=routine_id,
                    run_id=current.run_id,
                    outcome=RunOutcome.INTERRUPTED,
                    exit_code=None,
                    duration_seconds=None,
                    summary=INTERRUPTED_SUMMARY,
                    chat_id=state.chat_id,
                    warnings=(),
                    output_tail=read_output_tail(self.paths.run_log_path(routine_id, current.run_id)),
                )
            )
            kind = loaded.definition.kind if loaded.definition is not None else RunKind.COMMAND
            last_run = LastRun(
                run_id=current.run_id,
                trigger=current.trigger,
                kind=kind,
                outcome=RunOutcome.INTERRUPTED,
                summary=INTERRUPTED_SUMMARY,
                started_at=current.started_at,
                finished_at=now,
            )
            self.states.update(routine_id, _closing_off(last_run))
            reaped.append(routine_id)
        return reaped

    def _start_due_runs(self) -> list[RoutineId]:
        now = self.clock.now()
        zone = self.clock.local_zone()
        started: list[RoutineId] = []
        for loaded in self.definitions.list_routines():
            if loaded.definition is None:
                continue
            state = self.states.read(loaded.routine_id)
            if not is_switched_on(loaded, state) or state.current_run is not None:
                continue
            if is_lock_held(self.paths.run_lock_path(loaded.routine_id)):
                continue
            due = next_due(loaded.definition, state, now, zone)
            if due is None or due > now:
                continue
            self._spawn_run(loaded.routine_id)
            started.append(loaded.routine_id)
        return started

    def _spawn_run(self, routine_id: RoutineId) -> None:
        """A detached runner process: a tick never waits on a run."""
        argv = [
            sys.executable,
            "-m",
            "routines.cli",
            "run",
            str(routine_id),
            "--trigger",
            "scheduled",
        ]
        logger.info("Starting a scheduled run of {}", routine_id)
        subprocess.Popen(
            argv,
            cwd=self.paths.repo_root,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

    def _housekeep(self) -> None:
        now = self.clock.now()
        today = now.strftime("%Y-%m-%d")
        stamp_path = self.paths.housekeeping_path
        try:
            last = json.loads(stamp_path.read_text()).get("date") if stamp_path.is_file() else None
        except (OSError, ValueError):
            last = None
        if last == today:
            return
        self.ledger.rotate_if_large(now)
        self._prune_old_run_dirs(now)
        stamp_path.parent.mkdir(parents=True, exist_ok=True)
        stamp_path.write_text(json.dumps({"date": today}) + "\n")

    def _prune_old_run_dirs(self, now: datetime) -> None:
        cutoff = now.timestamp() - RUN_DIR_RETENTION.total_seconds()
        for loaded in self.definitions.list_routines():
            runs_dir = self.paths.runs_dir(loaded.routine_id)
            if not runs_dir.is_dir():
                continue
            for run_dir in runs_dir.iterdir():
                try:
                    if run_dir.is_dir() and run_dir.stat().st_mtime < cutoff:
                        _remove_tree(run_dir)
                except OSError as e:
                    logger.warning("Could not prune the run directory {}: {}", run_dir, e)


def _closing_off(last_run: LastRun) -> Callable[[RoutineState], RoutineState]:
    def close(state: RoutineState) -> RoutineState:
        return state.model_copy_update(
            to_update(state.field_ref().current_run, None),
            to_update(state.field_ref().last_run, last_run),
        )

    return close


def _mark_current_run_blocked(state: RoutineState) -> RoutineState:
    if state.current_run is None:
        return state
    blocked = state.current_run.model_copy_update(to_update(state.current_run.field_ref().is_blocked, True))
    return state.model_copy_update(to_update(state.field_ref().current_run, blocked))


def _read_result(path: Path) -> RunResult:
    if not path.is_file():
        return RunResult()
    try:
        return RunResult.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ValidationError) as e:
        logger.warning("Ignoring the run's result file: {}", e)
        return RunResult()


def _stop_process_group(process: subprocess.Popen[bytes]) -> None:
    """Ask the process group to stop, then kill what is left."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except OSError:
        return
    try:
        process.wait(timeout=TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            return
        process.wait()


def _remove_tree(path: Path) -> None:
    for child in path.iterdir():
        if child.is_dir() and not child.is_symlink():
            _remove_tree(child)
        else:
            child.unlink()
    path.rmdir()
