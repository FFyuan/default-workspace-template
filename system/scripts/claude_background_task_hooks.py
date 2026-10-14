#!/usr/bin/env python3
"""Claude's Stop and SessionStart hooks that record its own background tasks as markers.

    python3 system/scripts/claude_background_task_hooks.py stop
    python3 system/scripts/claude_background_task_hooks.py session-start

``.claude/settings.json`` wires both, and each reads the hook's input from stdin. ``stop`` copies
the background tasks Claude Code hands it into markers; ``session-start`` clears this Claude's
markers and dead ones and, on a resume, prints which of Claude's background tasks the restart
ended, which SessionStart adds to Claude's context. Each exits 0 on every condition it handles, so
it never blocks Claude's stop.

The markers and the hooks' logic are ``system/libs/chat_background_tasks``, which this script puts
on ``sys.path``: the hooks run it with a bare ``python3``, before any venv exists.
"""

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import IO

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "libs" / "chat_background_tasks" / "src"),
)

from chat_background_tasks.harnesses.base import lost_tasks_notice
from chat_background_tasks.harnesses.claude import ClaudeTaskHooks
from chat_background_tasks.markers import marker_root

HOOKS = ClaudeTaskHooks()


def read_payload(stdin: IO[str], event: str) -> object:
    try:
        return json.loads(stdin.read() or "null")
    except ValueError as exc:
        print(
            f"claude_background_task_hooks.py: the {event} input is not JSON ({exc})",
            file=sys.stderr,
        )
        return None


def cmd_stop(stdin: IO[str], environ: Mapping[str, str]) -> int:
    caller = HOOKS.hook_caller(environ)
    if caller is None:
        return 0
    payload = read_payload(stdin, "Stop")
    try:
        HOOKS.record_turn_end(marker_root(environ), caller, payload)
    except OSError as exc:
        print(
            f"claude_background_task_hooks.py: could not record the Claude tasks: {exc}",
            file=sys.stderr,
        )
    return 0


def cmd_session_start(stdin: IO[str], environ: Mapping[str, str]) -> int:
    caller = HOOKS.hook_caller(environ)
    if caller is None:
        return 0
    payload = read_payload(stdin, "SessionStart")
    try:
        removed = HOOKS.clear(marker_root(environ), caller)
    except OSError as exc:
        print(
            f"claude_background_task_hooks.py: could not clear the Claude tasks: {exc}",
            file=sys.stderr,
        )
        return 0
    if HOOKS.is_resume(payload) and removed:
        print(lost_tasks_notice(removed))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Claude's hooks that record its own background tasks as markers."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "stop", help="The Stop hook: copy the input's background tasks into markers."
    )
    commands.add_parser(
        "session-start",
        help="The SessionStart hook: clear this Claude's markers and dead ones; on a resume, "
        "name the tasks the restart ended.",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    stdin: IO[str] | None = None,
) -> int:
    args = _build_parser().parse_args(argv)
    resolved_environ = os.environ if environ is None else environ
    resolved_stdin = sys.stdin if stdin is None else stdin
    if args.command == "stop":
        return cmd_stop(resolved_stdin, resolved_environ)
    return cmd_session_start(resolved_stdin, resolved_environ)


if __name__ == "__main__":
    raise SystemExit(main())
