"""``usage-collector``: the supervised process that owns the workspace's usage store.

About once a second it reads what the workspace's agents appended to their
usage event files and drains the emitters' spool (reports written while it
was down or restarting); hourly it prunes raw events past retention. It
serves the HTTP API on 127.0.0.1.
"""

import itertools
import os
import threading
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from loguru import logger
from werkzeug.serving import make_server
from workspace_usage.context import read_workspace_id
from workspace_usage.emit import (
    CLAUDE_SESSIONS_SPOOL_NAME,
    COLLECTOR_PORT,
    EVENTS_SPOOL_NAME,
    spool_dir,
    usage_data_dir,
)

from usage_collector.agent_files import follow_agent_event_files
from usage_collector.feed import UsageFeed
from usage_collector.ingest import (
    IngestCounts,
    Ingestor,
    IngestOutcome,
    describe_counts,
)
from usage_collector.server import create_app
from usage_collector.store import UsageStore

DATABASE_FILENAME: Final[str] = "usage.db"
HOST_DIR_ENV_VAR: Final[str] = "MNGR_HOST_DIR"
_PASS_SECONDS: Final[float] = 1.0
_PRUNE_EVERY_PASSES: Final[int] = 3600


def host_dir(environ: Mapping[str, str]) -> Path | None:
    configured = environ.get(HOST_DIR_ENV_VAR, "").strip()
    return Path(configured) if configured else None


def run_pass(ingestor: Ingestor, store: UsageStore, environ: Mapping[str, str]) -> None:
    """One round of reading agent event files and draining both spools."""
    agents_host_dir = host_dir(environ)
    if agents_host_dir is not None:
        follow_agent_event_files(
            agents_host_dir, store, ingestor.ingest, read_workspace_id(environ)
        )
    _log_drained(
        "events", ingestor.drain_events_spool(spool_dir(environ, EVENTS_SPOOL_NAME))
    )
    _log_drained(
        "claude sessions",
        ingestor.drain_claude_sessions_spool(
            spool_dir(environ, CLAUDE_SESSIONS_SPOOL_NAME)
        ),
    )


def run_maintenance(
    ingestor: Ingestor,
    store: UsageStore,
    environ: Mapping[str, str],
    stop: threading.Event,
) -> None:
    """Run a pass about once a second, and prune hourly, until ``stop`` is set."""
    for passes in itertools.count():
        run_pass(ingestor, store, environ)
        if passes % _PRUNE_EVERY_PASSES == 0:
            pruned = store.prune(datetime.now(timezone.utc))
            if pruned:
                logger.info("Pruned {} raw events past retention", pruned)
        if stop.wait(_PASS_SECONDS):
            return


def _log_drained(kind: str, counts: IngestCounts) -> None:
    if counts[IngestOutcome.STORED] or counts[IngestOutcome.REJECTED]:
        logger.info("Drained spooled {}: {}", kind, describe_counts(counts))


def main() -> None:
    environ = dict(os.environ)
    store = UsageStore(usage_data_dir(environ) / DATABASE_FILENAME)
    feed = UsageFeed()
    ingestor = Ingestor(store, feed)
    app = create_app(store, feed, ingestor)
    stop = threading.Event()
    maintenance = threading.Thread(
        target=run_maintenance,
        args=(ingestor, store, environ, stop),
        name="usage-maintenance",
        daemon=True,
    )
    maintenance.start()
    server = make_server("127.0.0.1", COLLECTOR_PORT, app, threaded=True)
    logger.info("usage-collector listening on 127.0.0.1:{}", COLLECTOR_PORT)
    try:
        server.serve_forever()
    finally:
        stop.set()
        feed.close()
        maintenance.join(timeout=10)
        store.close()
