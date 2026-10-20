import os
from pathlib import Path
from typing import Final

from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from routines.primitives import RoutineId
from routines.primitives import RunId

DEFINITIONS_DIR: Final[Path] = Path("system/routines")
STATE_DIR: Final[Path] = Path("data/.state/routines")
DEFINITION_SUFFIX: Final[str] = ".toml"
STATE_FILENAME: Final[str] = "state.json"
RUN_LOCK_FILENAME: Final[str] = "run.lock"
STATE_LOCK_FILENAME: Final[str] = "state.lock"
RUNS_DIRNAME: Final[str] = "runs"
RUN_LOG_FILENAME: Final[str] = "log"
RESULT_FILENAME: Final[str] = "result.json"
EVENTS_PATH: Final[Path] = Path("events/runs/events.jsonl")
TICK_LOCK_FILENAME: Final[str] = "tick.lock"
HOUSEKEEPING_FILENAME: Final[str] = "housekeeping.json"

# Names another checkout; absent, the repo root is the current directory, which supervisord, cron (through the
# env wrapper) and the agents all set to the workspace checkout.
REPO_ROOT_ENV: Final[str] = "ROUTINES_REPO_ROOT"


class RoutinesPaths(FrozenModel):
    """Where everything of the library lives, under one repo root."""

    repo_root: Path = Field(description="The workspace checkout")

    @property
    def definitions_dir(self) -> Path:
        return self.repo_root / DEFINITIONS_DIR

    @property
    def state_dir(self) -> Path:
        return self.repo_root / STATE_DIR

    @property
    def events_path(self) -> Path:
        return self.state_dir / EVENTS_PATH

    @property
    def tick_lock_path(self) -> Path:
        return self.state_dir / TICK_LOCK_FILENAME

    @property
    def housekeeping_path(self) -> Path:
        return self.state_dir / HOUSEKEEPING_FILENAME

    def definition_path(self, routine_id: RoutineId) -> Path:
        return self.definitions_dir / f"{routine_id}{DEFINITION_SUFFIX}"

    def routine_state_dir(self, routine_id: RoutineId) -> Path:
        return self.state_dir / routine_id

    def state_path(self, routine_id: RoutineId) -> Path:
        return self.routine_state_dir(routine_id) / STATE_FILENAME

    def run_lock_path(self, routine_id: RoutineId) -> Path:
        return self.routine_state_dir(routine_id) / RUN_LOCK_FILENAME

    def state_lock_path(self, routine_id: RoutineId) -> Path:
        return self.routine_state_dir(routine_id) / STATE_LOCK_FILENAME

    def runs_dir(self, routine_id: RoutineId) -> Path:
        return self.routine_state_dir(routine_id) / RUNS_DIRNAME

    def run_dir(self, routine_id: RoutineId, run_id: RunId) -> Path:
        return self.runs_dir(routine_id) / run_id

    def run_log_path(self, routine_id: RoutineId, run_id: RunId) -> Path:
        return self.run_dir(routine_id, run_id) / RUN_LOG_FILENAME

    def result_path(self, routine_id: RoutineId, run_id: RunId) -> Path:
        return self.run_dir(routine_id, run_id) / RESULT_FILENAME


def paths_from_environment() -> RoutinesPaths:
    """The paths under the repo root the environment names, else the current directory."""
    return RoutinesPaths(
        repo_root=Path(os.environ.get(REPO_ROOT_ENV, "")) if os.environ.get(REPO_ROOT_ENV) else Path.cwd()
    )
