"""Recording the model calls of a ``claude -p`` one-shot.

Claude Code writes every call it makes, sub-agents' included, to its session
log. A one-shot runs with a session id chosen up front (``--session-id``,
with session persistence on), and once it exits the caller reports that
session; the usage collector reads the calls out of the log with the same
reader the Claude agents' usage writer uses, then deletes the log, so a
one-shot leaves nothing behind in the account's ``projects/`` directory.
"""

import os
from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4

from workspace_usage.context import (
    ORIGIN_KIND,
    ORIGIN_KIND_UNKNOWN,
    read_usage_context,
    read_workspace_id,
)
from workspace_usage.emit import emit_claude_session
from workspace_usage.events import BILLING_MODE_UNKNOWN


def new_claude_session_id() -> str:
    return str(uuid4())


def claude_session_args(session_id: str) -> list[str]:
    """The ``claude -p`` arguments that make it log under ``session_id`` (in place of ``--no-session-persistence``)."""
    return ["--session-id", session_id]


def build_claude_session_report(
    *,
    config_dir: Path,
    session_id: str,
    context: Mapping[str, str],
    workspace_id: str,
    purpose: str | None = None,
    billing_mode: str = BILLING_MODE_UNKNOWN,
    credential_ref: str | None = None,
    delete_log: bool = True,
) -> dict[str, object]:
    attribution: dict[str, object] = {
        "workspace_id": workspace_id,
        ORIGIN_KIND: context.get(ORIGIN_KIND, ORIGIN_KIND_UNKNOWN),
        **{
            key: value for key, value in context.items() if key != ORIGIN_KIND and value
        },
        **({"purpose": purpose} if purpose else {}),
    }
    report: dict[str, object] = {
        "config_dir": str(config_dir),
        "session_id": session_id,
        "attribution": attribution,
        "billing_mode": billing_mode,
        "delete_log": delete_log,
    }
    if credential_ref:
        report["credential_ref"] = credential_ref
    return report


def report_claude_one_shot(
    config_dir: Path,
    session_id: str,
    purpose: str | None = None,
    context: Mapping[str, str] | None = None,
    billing_mode: str = BILLING_MODE_UNKNOWN,
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Report a finished one-shot's session. ``context`` defaults to this process's usage context."""
    env = os.environ if environ is None else environ
    report = build_claude_session_report(
        config_dir=config_dir,
        session_id=session_id,
        context=read_usage_context(env) if context is None else context,
        workspace_id=read_workspace_id(env),
        purpose=purpose,
        billing_mode=billing_mode,
    )
    return emit_claude_session(report, env)
