import json
import subprocess

from click.testing import CliRunner
from click.testing import Result

from routines.cli import DEFAULT_WAKE_TIMEOUT
from routines.cli import routines
from routines.cli import wake_defaults
from routines.data_types import RoutineDefinition
from routines.paths import REPO_ROOT_ENV
from routines.paths import RoutinesPaths
from routines.primitives import RoutineId


def _invoke(paths: RoutinesPaths, *args: str) -> Result:
    runner = CliRunner()
    return runner.invoke(routines, list(args), env={REPO_ROOT_ENV: str(paths.repo_root)}, catch_exceptions=False)


def test_add_list_show_edit_and_remove_round_trip(git_paths: RoutinesPaths) -> None:
    added = _invoke(
        git_paths,
        "add",
        "news-sync",
        "--title",
        "News sync",
        "--what",
        "Pulls news.",
        "--every",
        "6h",
        "--",
        "python3",
        "sync.py",
    )
    assert added.exit_code == 0, added.output
    assert (git_paths.definitions_dir / "news-sync.toml").is_file()
    assert (
        subprocess.run(
            ["git", "log", "--format=%s", "-1"], cwd=git_paths.repo_root, capture_output=True, text=True
        ).stdout.strip()
        == "routines: add news-sync"
    )

    listed = _invoke(git_paths, "list", "--format", "json")
    listing = json.loads(listed.output)
    assert [row["routine_id"] for row in listing["routines"]] == ["news-sync"]
    assert listing["routines"][0]["health"] == "NOT_RUN_YET"
    assert listing["routines"][0]["schedule_text"] == "Every 6 hours"

    shown = _invoke(git_paths, "show", "news-sync")
    assert "News sync (news-sync)" in shown.output
    assert "Every 6 hours" in shown.output

    edited = _invoke(git_paths, "edit", "news-sync", "--every", "1d", "--at", "07:30", "--days", "mon,fri")
    assert edited.exit_code == 0, edited.output
    assert "Every Monday and Friday at 7:30 am" in _invoke(git_paths, "show", "news-sync").output

    removed = _invoke(git_paths, "remove", "news-sync")
    assert removed.exit_code == 0
    assert not (git_paths.definitions_dir / "news-sync.toml").exists()
    assert "No routines yet" in _invoke(git_paths, "list").output


def test_add_refuses_a_definition_that_does_not_validate_with_the_reason(git_paths: RoutinesPaths) -> None:
    result = _invoke(
        git_paths, "add", "x", "--title", "X", "--what", "Y", "--every", "15m", "--at", "07:00", "--", "true"
    )
    assert result.exit_code == 1
    assert "a day or longer" in result.output


def test_add_needs_a_command_or_a_skill(git_paths: RoutinesPaths) -> None:
    result = _invoke(git_paths, "add", "x", "--title", "X", "--what", "Y", "--every", "1h")
    assert result.exit_code == 1
    assert "exactly one of 'command' and 'skill'" in result.output


def test_disable_and_enable_flip_the_switch_in_the_state(git_paths: RoutinesPaths) -> None:
    _invoke(git_paths, "add", "x", "--title", "X", "--what", "Y", "--every", "1h", "--", "true")
    assert _invoke(git_paths, "disable", "x").exit_code == 0
    listing = json.loads(_invoke(git_paths, "list", "--format", "json").output)
    assert listing["routines"][0]["health"] == "OFF"
    assert _invoke(git_paths, "enable", "x").exit_code == 0
    listing = json.loads(_invoke(git_paths, "list", "--format", "json").output)
    assert listing["routines"][0]["health"] == "NOT_RUN_YET"


def test_run_with_wait_runs_in_process_and_reports_the_outcome(git_paths: RoutinesPaths) -> None:
    _invoke(
        git_paths, "add", "x", "--title", "X", "--what", "Y", "--every", "1h", "--", "sh", "-c", "echo ran; exit 0"
    )
    result = _invoke(git_paths, "run", "x", "--wait")
    assert result.exit_code == 0, result.output
    receipt = json.loads(result.output.splitlines()[0])
    assert receipt["routine_id"] == "x"
    assert "ran" in _invoke(git_paths, "log", "x").output
    runs = json.loads(_invoke(git_paths, "runs", "x", "--format", "json").output)
    assert runs[0]["outcome"] == "SUCCEEDED"
    assert runs[0]["run_id"] == receipt["run_id"]


def test_a_failed_run_with_wait_exits_one(git_paths: RoutinesPaths) -> None:
    _invoke(git_paths, "add", "x", "--title", "X", "--what", "Y", "--every", "1h", "--", "sh", "-c", "exit 2")
    assert _invoke(git_paths, "run", "x", "--wait").exit_code == 1


def test_show_of_a_missing_routine_says_so(git_paths: RoutinesPaths) -> None:
    result = _invoke(git_paths, "show", "nothing")
    assert result.exit_code == 1
    assert "There is no routine called 'nothing'" in result.output


def test_log_of_a_missing_routine_or_a_mistyped_run_id_says_so(git_paths: RoutinesPaths) -> None:
    missing = _invoke(git_paths, "log", "nothing")
    assert missing.exit_code == 1
    assert "There is no routine called 'nothing'" in missing.output

    _invoke(git_paths, "add", "hello", "--title", "Hello", "--what", "Says hello.", "--every", "1d", "--", "true")
    mistyped = _invoke(git_paths, "log", "hello", "not-a-run")
    assert mistyped.exit_code == 1
    assert "There is no run called 'not-a-run'" in mistyped.output


def test_a_wake_takes_its_title_and_timeout_from_the_routine_unless_told_otherwise() -> None:
    definition = RoutineDefinition.model_validate(
        {"title": "Weekly check-up", "what": "Checks.", "every": "1w", "command": ["true"], "timeout": "2h"}
    )
    caretaker = RoutineId("caretaker")

    from_definition = wake_defaults(definition, caretaker, None, None)
    assert (from_definition.title, str(from_definition.timeout)) == ("Weekly check-up", "2h")

    from_flags = wake_defaults(definition, caretaker, "Check-up", "30m")
    assert (from_flags.title, str(from_flags.timeout)) == ("Check-up", "30m")

    undefined = wake_defaults(None, caretaker, None, None)
    assert (undefined.title, str(undefined.timeout)) == ("Caretaker", DEFAULT_WAKE_TIMEOUT)


def test_wake_refuses_a_timeout_that_is_not_a_duration_in_the_commands_words(git_paths: RoutinesPaths) -> None:
    result = _invoke(git_paths, "wake", "caretaker", "--timeout", "soon")
    assert result.exit_code == 1
    assert "error: 'soon' is not a duration" in result.output
