"""What the command and the app both do: the one place a routine is listed, changed, run, or removed."""

import os
from pathlib import Path
from typing import Final

from loguru import logger
from pydantic import Field

from imbue.imbue_common.model_update import to_update
from imbue.imbue_common.mutable_model import MutableModel
from routines.chat_app import HttpChatApp
from routines.clock import SystemClock
from routines.data_types import RoutineDefinition
from routines.data_types import RoutineDetail
from routines.data_types import RoutineListing
from routines.data_types import RoutineRow
from routines.data_types import RunDetail
from routines.data_types import RunRecord
from routines.data_types import RunResult
from routines.data_types import RunStartReceipt
from routines.data_types import ScheduleChange
from routines.definitions import FileDefinitionStore
from routines.errors import ChatAppError
from routines.errors import DefinitionValidationError
from routines.errors import RunInFlightError
from routines.errors import RunNotFoundError
from routines.interfaces import ChatAppInterface
from routines.interfaces import ClockInterface
from routines.interfaces import DefinitionStoreInterface
from routines.interfaces import LedgerInterface
from routines.interfaces import NotifierInterface
from routines.interfaces import StateStoreInterface
from routines.ledger import FileLedger
from routines.locks import is_lock_held
from routines.notifications import GatewayNotifier
from routines.paths import RoutinesPaths
from routines.presentation import build_listing
from routines.presentation import build_row
from routines.presentation import fold_run_events
from routines.primitives import RoutineId
from routines.primitives import RunId
from routines.primitives import RunTrigger
from routines.registry import app_display_names
from routines.registry import registry_path_of
from routines.repository import GitRepository
from routines.runner import Runner
from routines.runner import read_result
from routines.runner import spawn_run_process
from routines.state import FileStateStore

DEFAULT_RUN_LIMIT: Final[int] = 25
LOG_TAIL_BYTES: Final[int] = 200_000


class RoutinesService(MutableModel):
    """The library's front door, over the stores and the runner."""

    paths: RoutinesPaths = Field(frozen=True, description="Where everything lives")
    registry_path: Path = Field(frozen=True, description="The app registry, for the apps' display names")
    definitions: DefinitionStoreInterface = Field(frozen=True, description="The definition files")
    states: StateStoreInterface = Field(frozen=True, description="The state files")
    ledger: LedgerInterface = Field(frozen=True, description="The run events")
    chat_app: ChatAppInterface = Field(frozen=True, description="The chat app")
    clock: ClockInterface = Field(frozen=True, description="The time")
    runner: Runner = Field(frozen=True, description="What runs routines")

    def listing(self) -> RoutineListing:
        now = self.clock.now()
        zone = self.clock.local_zone()
        rows = [
            build_row(loaded, self.states.read(loaded.routine_id), now, zone)
            for loaded in self.definitions.list_routines()
        ]
        return build_listing(rows, app_display_names(self.registry_path), now, zone)

    def row(self, routine_id: RoutineId) -> RoutineRow:
        loaded = self.definitions.load(routine_id)
        return build_row(
            loaded,
            self.states.read(routine_id),
            self.clock.now(),
            self.clock.local_zone(),
        )

    def detail(self, routine_id: RoutineId, run_limit: int = DEFAULT_RUN_LIMIT) -> RoutineDetail:
        loaded = self.definitions.load(routine_id)
        now = self.clock.now()
        row = build_row(loaded, self.states.read(routine_id), now, self.clock.local_zone())
        runs = fold_run_events(self.ledger.recent_events(routine_id, run_limit), now)
        return RoutineDetail(
            row=row,
            definition=loaded.definition,
            definition_path=str(self.paths.definition_path(routine_id)),
            runs=tuple(runs),
        )

    def runs(self, routine_id: RoutineId, run_limit: int = DEFAULT_RUN_LIMIT) -> list[RunRecord]:
        self.definitions.load(routine_id)
        return fold_run_events(self.ledger.recent_events(routine_id, run_limit), self.clock.now())

    def run_detail(self, routine_id: RoutineId, run_id: RunId) -> RunDetail:
        self.definitions.load(routine_id)
        records = fold_run_events(self.ledger.events_of_run(routine_id, run_id), self.clock.now())
        if not records:
            raise RunNotFoundError(run_id)
        log, is_truncated = self.log_tail(routine_id, run_id)
        result: RunResult = read_result(self.paths.result_path(routine_id, run_id))
        return RunDetail(run=records[0], log=log, is_log_truncated=is_truncated, links=result.links)

    def log_tail(self, routine_id: RoutineId, run_id: RunId) -> tuple[str, bool]:
        """The run's log, or its last part when it is long; whether it was cut."""
        path = self.paths.run_log_path(routine_id, run_id)
        if not path.is_file():
            return "", False
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            is_truncated = size > LOG_TAIL_BYTES
            handle.seek(max(0, size - LOG_TAIL_BYTES))
            return handle.read().decode("utf-8", errors="replace"), is_truncated

    def last_run_id(self, routine_id: RoutineId) -> RunId | None:
        state = self.states.read(routine_id)
        if state.current_run is not None:
            return state.current_run.run_id
        return state.last_run.run_id if state.last_run is not None else None

    def set_enabled(self, routine_id: RoutineId, is_enabled: bool) -> None:
        self.definitions.load(routine_id)
        self.states.update(
            routine_id,
            lambda state: state.model_copy_update(to_update(state.field_ref().is_enabled, is_enabled)),
        )

    def add(self, routine_id: RoutineId, definition: RoutineDefinition) -> Path:
        return self.definitions.add(routine_id, definition)

    def replace(
        self,
        routine_id: RoutineId,
        definition: RoutineDefinition,
        change_description: str,
    ) -> Path:
        return self.definitions.replace(routine_id, definition, change_description)

    def change_schedule(self, routine_id: RoutineId, change: ScheduleChange) -> RoutineDefinition:
        loaded = self.definitions.load(routine_id)
        if loaded.definition is None:
            raise DefinitionValidationError(f"{routine_id} is broken ({loaded.error}); fix its file first.")
        updated = loaded.definition.model_copy_update(
            to_update(loaded.definition.field_ref().every, change.every),
            to_update(loaded.definition.field_ref().at, change.at),
            to_update(loaded.definition.field_ref().days, change.days),
            to_update(loaded.definition.field_ref().day_of_month, change.day_of_month),
            to_update(loaded.definition.field_ref().once, change.once),
        )
        validated = RoutineDefinition.model_validate(updated.model_dump())
        self.definitions.replace(routine_id, validated, "change the schedule")
        # A rescheduled routine is judged from now, not from an attempt made under the old schedule.
        return validated

    def remove(self, routine_id: RoutineId) -> None:
        state = self.states.read(routine_id)
        self.definitions.remove(routine_id)
        if state.chat_id is not None:
            try:
                self.chat_app.stop_chat(state.chat_id)
            except ChatAppError as e:
                logger.warning(
                    "Removed {} but could not stop its chat {}: {}",
                    routine_id,
                    state.chat_id,
                    e,
                )
        self.states.remove(routine_id)

    def is_running(self, routine_id: RoutineId) -> bool:
        return self.states.read(routine_id).current_run is not None or is_lock_held(
            self.paths.run_lock_path(routine_id)
        )

    def start_run_detached(self, routine_id: RoutineId) -> RunStartReceipt:
        """A manual run in a process of its own; raises RunInFlightError when one is already going."""
        loaded = self.definitions.load(routine_id)
        if loaded.definition is None:
            raise DefinitionValidationError(f"{routine_id} cannot run: {loaded.error}")
        if self.is_running(routine_id):
            raise RunInFlightError(f"A run of {routine_id} is already going.")
        run_id = RunId.generate()
        spawn_run_process(self.paths, routine_id, RunTrigger.MANUAL, run_id)
        return RunStartReceipt(routine_id=routine_id, run_id=run_id)


def build_service(paths: RoutinesPaths, environ: dict[str, str]) -> RoutinesService:
    """The service over the real stores, the chat app on loopback, the gateway, and the machine's clock."""
    clock = SystemClock()
    registry_path = registry_path_of(paths.repo_root, environ)
    repository = GitRepository(repo_root=paths.repo_root, clock=clock)
    definitions = FileDefinitionStore(paths=paths, repository=repository)
    states = FileStateStore(paths=paths)
    ledger = FileLedger(paths=paths)
    chat_app = HttpChatApp(repo_root=paths.repo_root, registry_path=registry_path, environ=environ, clock=clock)
    notifier: NotifierInterface = GatewayNotifier(environ=environ)
    runner = Runner(
        paths=paths,
        definitions=definitions,
        states=states,
        ledger=ledger,
        chat_app=chat_app,
        notifier=notifier,
        clock=clock,
    )
    return RoutinesService(
        paths=paths,
        registry_path=registry_path,
        definitions=definitions,
        states=states,
        ledger=ledger,
        chat_app=chat_app,
        clock=clock,
        runner=runner,
    )
