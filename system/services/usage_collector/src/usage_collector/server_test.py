import json
from collections.abc import Iterator
from datetime import timedelta

import pytest
from flask.testing import FlaskClient

from usage_collector.feed import UsageFeed
from usage_collector.ingest import Ingestor
from usage_collector.server import create_app
from usage_collector.status import IngestStatus
from usage_collector.store import UsageStore
from usage_collector.testing import NOW, model_call_payload

_VISITOR = json.dumps({"owner": False, "user_id": "u-2", "email": "v@example.com"})


@pytest.fixture
def client(
    store: UsageStore, feed: UsageFeed, ingestor: Ingestor, status: IngestStatus
) -> Iterator[FlaskClient]:
    yield create_app(store, feed, status).test_client()


def test_a_visitor_admitted_by_the_gateway_reads_usage_like_the_owner(
    client: FlaskClient,
) -> None:
    assert (
        client.get("/v1/totals", headers={"X-Imbue-Identity": _VISITOR}).status_code
        == 200
    )


def test_ingested_events_show_up_in_totals(
    client: FlaskClient, ingestor: Ingestor
) -> None:
    ingestor.ingest(model_call_payload(attribution={"origin_id": "files"}))
    ingestor.ingest(model_call_payload(attribution={"origin_id": "routines"}))

    since = (NOW - timedelta(hours=1)).isoformat()
    totals = client.get(
        "/v1/totals", query_string={"group_by": "origin_id", "since": since}
    ).get_json()
    assert [(row["group"]["origin_id"], row["calls"]) for row in totals["rows"]] == [
        ("files", 1),
        ("routines", 1),
    ]


def test_events_cannot_be_posted(client: FlaskClient) -> None:
    assert client.post("/v1/events", json=model_call_payload()).status_code == 404


def test_the_stream_sends_each_new_event(
    client: FlaskClient, feed: UsageFeed, ingestor: Ingestor
) -> None:
    response = client.get("/v1/stream", buffered=False)
    chunks = iter(response.response)
    assert next(chunks) == b": connected\n\n"

    payload = model_call_payload()
    ingestor.ingest(payload)

    chunk = next(chunks)
    message = chunk.decode() if isinstance(chunk, bytes) else chunk
    assert message.startswith("event: model_call\ndata: ")
    assert json.loads(message.split("data: ", 1)[1])["event_id"] == payload["event_id"]
    response.close()
    assert feed.subscriber_count == 0


def test_latency_and_calls_answer_over_http(
    client: FlaskClient, ingestor: Ingestor
) -> None:
    payload = model_call_payload()
    ingestor.ingest(payload)
    since = (NOW - timedelta(hours=1)).isoformat()

    latency = client.get(
        "/v1/latency", query_string={"group_by": "model", "since": since}
    ).get_json()
    calls = client.get("/v1/calls", query_string={"origin_id": "files"}).get_json()

    assert latency["rows"][0]["p50_ms"] == 2000
    assert [call["event"]["event_id"] for call in calls["calls"]] == [
        payload["event_id"]
    ]


def test_bad_calls_parameters_are_refused(client: FlaskClient) -> None:
    assert client.get("/v1/calls", query_string={"limit": "many"}).status_code == 400
    assert client.get("/v1/calls", query_string={"limit": "0"}).status_code == 400
    assert client.get("/v1/calls", query_string={"before": "nope"}).status_code == 400


def test_health_reports_catching_up_until_a_complete_pass(
    client: FlaskClient, status: IngestStatus
) -> None:
    assert client.get("/health").get_json() == {"status": "ok", "catching_up": True}

    status.record_pass(is_complete=True)

    assert client.get("/health").get_json() == {"status": "ok", "catching_up": False}
