#!/usr/bin/env python3
"""The background tasks chats are waiting on, and whether a chat is busy; and Claude's hooks that
record its own background tasks.

    python3 system/scripts/background_tasks.py list [--chat <chat-id>] [--format json|tsv]
    python3 system/scripts/background_tasks.py is-busy <chat-id>    # exit 0 busy, 1 not

``list`` prints every chat with pending tasks; ``tsv`` is one line per chat,
``chat_id<TAB>active_agent_id<TAB>active_agent_name<TAB>is_busy<TAB>task_count``. Both ask the
chat app first and read the marker files only when it cannot answer; ``is_busy`` from the chat
app also counts a turn in flight, which the files cannot see.

``record-claude-stop`` and ``clear-claude`` are the Stop and SessionStart hooks
``.claude/settings.json`` wires. Each exits 0 on every condition it handles, so it never blocks
Claude's stop. On a resume, ``clear-claude`` prints which of Claude's background tasks the restart
ended, and SessionStart adds what it prints to Claude's context.

The markers and their readers are ``system/libs/chat_background_tasks``, which this script puts
on ``sys.path``: skills run it with a bare ``python3`` and the hooks run it before any venv exists.
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

import message_chat
from chat_background_tasks import claude
from chat_background_tasks.listing import (
    AGENTS_PATH,
    ChatAppUnavailableError,
    ChatTasks,
    chats_from_agents_payload,
    chats_from_files,
    get_json,
)
from chat_background_tasks.markers import marker_root

EXIT_BUSY = 0
EXIT_NOT_BUSY = 1


def known_chats(environ: Mapping[str, str], cwd: Path) -> tuple[list[ChatTasks], str]:
    """The chats the chat app reports, or those the files hold live tasks for, and which answered
    (``chat_app`` or ``files``)."""
    base_url = message_chat.chat_app_url(environ, cwd)
    try:
        return chats_from_agents_payload(get_json(base_url, AGENTS_PATH)), "chat_app"
    except ChatAppUnavailableError as exc:
        print(f"background_tasks.py: reading the marker files ({exc})", file=sys.stderr)
        return chats_from_files(marker_root(environ)), "files"


def cmd_list(
    chat_filter: str | None, output_format: str, environ: Mapping[str, str], cwd: Path
) -> int:
    chats, source = known_chats(environ, cwd)
    chats = [
        chat for chat in chats if chat.tasks and chat_filter in (None, chat.chat_id)
    ]
    if output_format == "tsv":
        for chat in chats:
            print(chat.to_tsv())
    else:
        print(
            json.dumps(
                {"source": source, "chats": [chat.to_json() for chat in chats]},
                indent=2,
            )
        )
    return 0


def cmd_is_busy(chat_id: str, environ: Mapping[str, str], cwd: Path) -> int:
    chats, _ = known_chats(environ, cwd)
    return (
        EXIT_BUSY
        if any(chat.chat_id == chat_id and chat.is_busy for chat in chats)
        else EXIT_NOT_BUSY
    )


def cmd_record_claude_stop(stdin: IO[str], environ: Mapping[str, str]) -> int:
    chat_id = claude.hook_chat_id(environ)
    if not chat_id:
        return 0
    try:
        payload = json.loads(stdin.read() or "null")
    except ValueError as exc:
        print(
            f"background_tasks.py: the Stop input is not JSON ({exc})", file=sys.stderr
        )
        return 0
    try:
        claude.record_stop(
            marker_root(environ), chat_id, payload, claude.hook_claude_pid(environ)
        )
    except OSError as exc:
        print(
            f"background_tasks.py: could not record the Claude tasks: {exc}",
            file=sys.stderr,
        )
    return 0


def cmd_clear_claude(stdin: IO[str], environ: Mapping[str, str]) -> int:
    """On a resume, prints what the restart ended, which SessionStart adds to Claude's context."""
    chat_id = claude.hook_chat_id(environ)
    if not chat_id:
        return 0
    try:
        payload = json.loads(stdin.read() or "null")
    except ValueError as exc:
        print(
            f"background_tasks.py: the SessionStart input is not JSON ({exc})",
            file=sys.stderr,
        )
        payload = None
    try:
        removed = claude.clear(
            marker_root(environ), chat_id, claude.hook_claude_pid(environ)
        )
    except OSError as exc:
        print(
            f"background_tasks.py: could not clear the Claude tasks: {exc}",
            file=sys.stderr,
        )
        return 0
    if isinstance(payload, dict) and payload.get("source") == "resume" and removed:
        print(claude.lost_tasks_notice(removed))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="The background tasks chats are waiting on, and whether a chat is busy."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    list_parser = commands.add_parser(
        "list", help="Print every chat with pending background tasks."
    )
    list_parser.add_argument("--chat", default=None, help="Only this chat id.")
    list_parser.add_argument("--format", choices=("json", "tsv"), default="json")
    is_busy_parser = commands.add_parser(
        "is-busy", help="Exit 0 when the chat is busy, 1 when it is not."
    )
    is_busy_parser.add_argument("chat_id")
    commands.add_parser(
        "record-claude-stop",
        help="Claude's Stop hook: copy the input's background tasks into markers.",
    )
    commands.add_parser(
        "clear-claude",
        help="Claude's SessionStart hook: clear this Claude's markers and dead ones; on a "
        "resume, name the tasks the restart ended.",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    stdin: IO[str] | None = None,
) -> int:
    args = _build_parser().parse_args(argv)
    resolved_environ = os.environ if environ is None else environ
    if args.command == "list":
        return cmd_list(args.chat, args.format, resolved_environ, Path.cwd())
    if args.command == "is-busy":
        return cmd_is_busy(args.chat_id, resolved_environ, Path.cwd())
    if args.command == "record-claude-stop":
        return cmd_record_claude_stop(
            sys.stdin if stdin is None else stdin, resolved_environ
        )
    return cmd_clear_claude(sys.stdin if stdin is None else stdin, resolved_environ)


if __name__ == "__main__":
    raise SystemExit(main())
