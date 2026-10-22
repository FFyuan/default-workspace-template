"""A finished ``claude -p`` session reported for the collector to read, and reading it.

The report names the Claude config dir the one-shot ran under and the
session id it was given; the calls come from its session log through
mngr_usage's reader, so a one-shot is counted exactly like an agent's turn.
"""

import re
import shutil
from pathlib import Path

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.primitives import NonEmptyStr
from imbue.mngr_usage.claude_session_log import (
    ClaudeSessionLogError,
    claude_account_billing_mode,
    find_claude_session_log,
    read_claude_session_calls,
)
from imbue.mngr_usage.model_call import BillingMode, ModelCallEvent, UsageAttribution
from loguru import logger
from pydantic import Field, field_validator

# Claude Code session ids are UUIDs; holding reports to that keeps a report from steering
# the log lookup (and the deletion after it) anywhere outside the config dir's projects/.
_SESSION_ID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


class InvalidClaudeSessionIdError(ValueError):
    """Raised for a report whose session id is not a Claude session UUID."""


class ClaudeSessionNotFoundError(Exception):
    """Raised when a reported session has no log under its config dir."""


class ClaudeSessionReport(FrozenModel):
    config_dir: Path = Field(
        description="The Claude config dir (CLAUDE_CONFIG_DIR) the session ran under"
    )
    session_id: NonEmptyStr = Field(
        description="The id the session was started with (--session-id)"
    )
    attribution: UsageAttribution = Field(
        description="What the session's calls inherit"
    )
    billing_mode: BillingMode = Field(default=BillingMode.UNKNOWN)
    credential_ref: NonEmptyStr | None = Field(default=None)
    delete_log: bool = Field(
        default=True, description="Delete the session's logs once read (one-shots)"
    )

    @field_validator("session_id")
    @classmethod
    def _check_session_id(cls, value: NonEmptyStr) -> NonEmptyStr:
        if not _SESSION_ID.match(value):
            raise InvalidClaudeSessionIdError(
                f"session_id {value!r} is not a Claude session UUID"
            )
        return value


def read_reported_session(report: ClaudeSessionReport) -> list[ModelCallEvent]:
    """The session's calls; deletes its logs afterwards when the report asks. Raises ClaudeSessionNotFoundError."""
    session_log = find_claude_session_log(report.config_dir, report.session_id)
    if session_log is None:
        raise ClaudeSessionNotFoundError(
            f"No session log for {report.session_id} under {report.config_dir}"
        )
    # A one-shot's caller rarely knows who pays; the account it ran under records it.
    billing_mode = (
        claude_account_billing_mode(report.config_dir)
        if report.billing_mode == BillingMode.UNKNOWN
        else report.billing_mode
    )
    try:
        events = read_claude_session_calls(
            session_log, report.attribution, billing_mode, report.credential_ref
        )
    except ClaudeSessionLogError as e:
        raise ClaudeSessionNotFoundError(str(e)) from e
    if report.delete_log:
        _delete_session_logs(session_log)
    return events


def _delete_session_logs(session_log: Path) -> None:
    try:
        session_log.unlink(missing_ok=True)
        shutil.rmtree(session_log.with_suffix(""), ignore_errors=True)
    except OSError as e:
        logger.warning(
            "Could not delete the one-shot session log {}: {}", session_log, e
        )
