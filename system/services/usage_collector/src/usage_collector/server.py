"""The collector's HTTP API, on 127.0.0.1 only.

- ``GET /v1/totals?group_by=origin_id,model&since=24h[&until=...][&bucket=hour]``: cost and token totals.
- ``GET /v1/stream``: server-sent events, one ``model_call`` message per newly stored event.

Usage is the owner's alone: a request the share gateway marks as a visitor's
is refused. A request with no identity header comes from inside the
workspace, which is the owner's.
"""

import json
import queue
import re
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import Final

from flask import Flask, Response, jsonify, request
from loguru import logger

from usage_collector.feed import UsageFeed
from usage_collector.store import TimeBucket, UsageStore, UsageStoreError

IDENTITY_HEADER: Final[str] = "X-Imbue-Identity"
DEFAULT_SINCE: Final[timedelta] = timedelta(hours=24)
_KEEPALIVE_SECONDS: Final[float] = 15.0
_DURATION = re.compile(r"^(\d+)([smhd])$")
_DURATION_UNITS: Final[dict[str, str]] = {
    "s": "seconds",
    "m": "minutes",
    "h": "hours",
    "d": "days",
}


class QueryParameterError(ValueError):
    """Raised for a totals query parameter that cannot be read."""


def is_owner_request(identity_header: str | None) -> bool:
    """Whether a request is the owner's: only an identity that says ``"owner": false`` is a visitor's."""
    if identity_header is None or not identity_header.strip():
        return True
    try:
        identity = json.loads(identity_header)
    except json.JSONDecodeError:
        logger.warning("Ignored an unreadable {} header", IDENTITY_HEADER)
        return True
    return not (isinstance(identity, dict) and identity.get("owner") is False)


def parse_time(
    value: str | None, now: datetime, default: datetime | None
) -> datetime | None:
    """A duration before ``now`` (``90s``, ``30m``, ``24h``, ``7d``) or an ISO timestamp."""
    if value is None or not value.strip():
        return default
    match = _DURATION.match(value.strip())
    if match:
        return now - timedelta(**{_DURATION_UNITS[match.group(2)]: int(match.group(1))})
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as e:
        raise QueryParameterError(
            f"{value!r} is neither a duration like 24h nor an ISO timestamp"
        ) from e
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def parse_bucket(value: str | None) -> TimeBucket | None:
    if value is None or not value.strip():
        return None
    for bucket in TimeBucket:
        if bucket.lower() == value.strip().lower():
            return bucket
    raise QueryParameterError(
        f"bucket must be one of {[bucket.lower() for bucket in TimeBucket]}"
    )


def create_app(store: UsageStore, feed: UsageFeed) -> Flask:
    app = Flask(__name__)

    @app.before_request
    def _owner_only() -> Response | None:
        if is_owner_request(request.headers.get(IDENTITY_HEADER)):
            return None
        logger.warning("Refused a visitor's request to {}", request.path)
        refusal = jsonify(detail="Usage is visible only to the workspace owner")
        refusal.status_code = 403
        return refusal

    @app.get("/health")
    def _health() -> Response:
        return jsonify(status="ok")

    @app.get("/v1/totals")
    def _get_totals() -> Response | tuple[Response, int]:
        now = datetime.now(timezone.utc)
        group_by = [
            field.strip()
            for field in request.args.get("group_by", "").split(",")
            if field.strip()
        ]
        try:
            since = (
                parse_time(request.args.get("since"), now, None) or now - DEFAULT_SINCE
            )
            until = parse_time(request.args.get("until"), now, None)
            bucket = parse_bucket(request.args.get("bucket"))
            rows = store.totals(group_by, since, until, bucket)
        except (QueryParameterError, UsageStoreError) as e:
            return _error(str(e), 400)
        return jsonify(
            since=since.isoformat(),
            until=until.isoformat() if until is not None else None,
            group_by=group_by,
            bucket=str(bucket).lower() if bucket is not None else None,
            rows=[json.loads(row.model_dump_json()) for row in rows],
        )

    @app.get("/v1/stream")
    def _stream() -> Response:
        subscription = feed.subscribe()

        def _messages() -> Iterator[str]:
            try:
                yield ": connected\n\n"
                while subscription.is_open:
                    try:
                        message = subscription.events.get(timeout=_KEEPALIVE_SECONDS)
                    except queue.Empty:
                        yield ": keepalive\n\n"
                        continue
                    yield f"event: model_call\ndata: {message}\n\n"
            finally:
                feed.unsubscribe(subscription)

        return Response(
            _messages(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def _error(detail: str, status: int) -> tuple[Response, int]:
    return jsonify(detail=detail), status
