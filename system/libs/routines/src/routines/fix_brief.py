"""The brief a Fix chat opens on: the routine, what is wrong, where to look, and its recent runs."""

from typing import Final

from imbue.imbue_common.pure import pure
from routines.data_types import RoutineDetail
from routines.data_types import RunRecord

RUNS_IN_BRIEF: Final[int] = 8
MAX_CHAT_NAME_CHARS: Final[int] = 40


@pure
def _run_lines(runs: tuple[RunRecord, ...]) -> list[str]:
    if not runs:
        return ["## Recent runs", "", "None recorded yet."]
    lines = ["## Recent runs", "", "Newest first."]
    for run in runs[:RUNS_IN_BRIEF]:
        verdict = run.outcome_text if run.outcome is not None else "still going"
        lines.append(f"- {run.started_at:%b %-d %H:%M} · {run.trigger.lower()} · {verdict}")
        if run.summary:
            lines.append(f"  {run.summary}")
    return lines


@pure
def build_fix_brief(detail: RoutineDetail, routine_page_path: str) -> str:
    """The first message of the Fix chat, addressed to the workspace's /assist flow."""
    row = detail.row
    definition = detail.definition
    lines = [
        f'/assist The routine "{row.title}" is not working and I would like it fixed.',
        "",
        "This brief was written by the Routines app from the routine's live state.",
        "",
        "## What it is",
        "",
        f"- Shows in Routines as: {row.title}",
        f"- Routine id: `{row.routine_id}`",
        f"- What it is supposed to do: {row.what}",
        f"- Schedule: {row.schedule_text}",
    ]
    if definition is not None and definition.command is not None:
        lines.append(f"- Command it runs: `{' '.join(definition.command)}`")
    if definition is not None and definition.skill is not None:
        lines.append(f"- Skill it runs in its chat: `/{definition.skill}`")
    if row.app:
        lines.append(f"- Belongs to the app: {row.app}")
    lines += ["", "## What is wrong", "", f"- Current state: {row.health_text}"]
    if row.health_detail:
        lines.append(f"- {row.health_detail}")
    lines += [
        "",
        "## Where to look",
        "",
        f"- Its definition: `{detail.definition_path}`",
        f"- Its runs and logs: `data/.state/routines/{row.routine_id}/runs/<run id>/log`",
        f"- Its page in the Routines app: `{routine_page_path}`",
        "- `routines show <id>` and `routines log <id>` print the same; the `manage-routines` skill explains the rest.",
        "",
        *_run_lines(detail.runs),
        "",
        "## What I would like",
        "",
        "Reproduce the failure yourself (`routines run <id> --wait` runs it now), find the real cause, and fix it.",
        "If the cause is an expired or missing connection rather than a bug, say so plainly: that needs me to",
        "reconnect it, not a code change. When you are done, tell me in plain terms what was wrong and whether it is fixed.",
    ]
    return "\n".join(lines)


@pure
def fix_chat_name(title: str) -> str:
    return f"Fix {title}"[:MAX_CHAT_NAME_CHARS]
