"""Delivering usage reports to the workspace's usage collector without ever failing the model call.

A report is POSTed to the collector on loopback. When the collector cannot
take it (not running, restarting, erroring), it is written to the spool
instead, one file per report, which the collector drains when it next runs.
Neither path raises: a usage record is never worth a failed call.

Two kinds of report share this path: a model_call event (``/v1/events``,
spooled under ``events/``) and a finished ``claude -p`` session for the
collector to read from its session log (``/v1/claude-sessions``, spooled
under ``claude-sessions/``).
"""

import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Final
from uuid import uuid4

from loguru import logger

COLLECTOR_URL_ENV_VAR: Final[str] = "IMBUE_USAGE_COLLECTOR_URL"
DATA_DIR_ENV_VAR: Final[str] = "IMBUE_USAGE_DATA_DIR"
COLLECTOR_PORT: Final[int] = 8795
DEFAULT_COLLECTOR_URL: Final[str] = f"http://127.0.0.1:{COLLECTOR_PORT}"
# Absolute rather than relative to the repo root: apps and their claude -p children
# do not all run from it.
DEFAULT_DATA_DIR: Final[Path] = Path.home() / "workspace" / "data" / ".apps" / "usage"
SPOOL_DIR_NAME: Final[str] = "spool"
EVENTS_SPOOL_NAME: Final[str] = "events"
CLAUDE_SESSIONS_SPOOL_NAME: Final[str] = "claude-sessions"
SPOOL_SUFFIX: Final[str] = ".json"
EVENTS_PATH: Final[str] = "/v1/events"
CLAUDE_SESSIONS_PATH: Final[str] = "/v1/claude-sessions"
# Loopback answers in milliseconds; this only bounds a collector that accepted the
# connection and then hung.
_POST_TIMEOUT_SECONDS: Final[float] = 0.5


def collector_url(environ: Mapping[str, str]) -> str:
    return (
        environ.get(COLLECTOR_URL_ENV_VAR, "").strip().rstrip("/")
        or DEFAULT_COLLECTOR_URL
    )


def usage_data_dir(environ: Mapping[str, str]) -> Path:
    """The collector's directory: its store and the spool it drains."""
    configured = environ.get(DATA_DIR_ENV_VAR, "").strip()
    return Path(configured) if configured else DEFAULT_DATA_DIR


def spool_dir(environ: Mapping[str, str], kind: str) -> Path:
    return usage_data_dir(environ) / SPOOL_DIR_NAME / kind


def emit_model_call(
    event: Mapping[str, object], environ: Mapping[str, str] | None = None
) -> bool:
    """Send one model_call event to the collector, or spool it. Returns whether the collector took it directly."""
    return _post_or_spool(EVENTS_PATH, EVENTS_SPOOL_NAME, event, environ)


def emit_claude_session(
    report: Mapping[str, object], environ: Mapping[str, str] | None = None
) -> bool:
    """Ask the collector to read a finished claude -p session's calls, or spool the request."""
    return _post_or_spool(
        CLAUDE_SESSIONS_PATH, CLAUDE_SESSIONS_SPOOL_NAME, report, environ
    )


def _post_or_spool(
    path: str,
    spool_kind: str,
    report: Mapping[str, object],
    environ: Mapping[str, str] | None,
) -> bool:
    env = os.environ if environ is None else environ
    body = json.dumps(report, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        f"{collector_url(env)}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_POST_TIMEOUT_SECONDS) as response:
            if 200 <= response.status < 300:
                return True
    except urllib.error.HTTPError as e:
        if e.code == 400:
            # A rejected report would be rejected again on drain; spooling it would only retry it forever.
            logger.warning(
                "The usage collector rejected a usage report: {}", e.read()[:300]
            )
            return False
    except (urllib.error.URLError, OSError) as e:
        logger.debug("Usage collector unreachable ({}); spooling the report", e)
    spool_report(body, spool_dir(env, spool_kind))
    return False


def spool_report(body: bytes, directory: Path) -> Path | None:
    """Write one serialized report where the collector drains it. Returns the file, or None if the write failed."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        name = uuid4().hex
        partial = directory / f".{name}.partial"
        partial.write_bytes(body)
        # The rename is what makes the report visible, so the collector never reads half a file.
        final = directory / f"{name}{SPOOL_SUFFIX}"
        partial.rename(final)
        return final
    except OSError as e:
        logger.warning("Could not spool a usage report to {}: {}", directory, e)
        return None
