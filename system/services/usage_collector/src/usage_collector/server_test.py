import json
from collections.abc import Iterator
from datetime import timedelta

import pytest
from flask.testing import FlaskClient

from usage_collector.feed import UsageFeed
from usage_collector.ingest import Ingestor
from usage_collector.server import create_app, is_owner_request
from usage_collector.store import UsageStore
from usage_collector.testing import NOW, model_call_payload

_VISITOR = json.dumps({"owner": False, "user_id": "u-2", "email": "v@example.com"})


@pytest.fixture
def client(
    store: UsageStore, feed: UsageFeed, ingestor: Ingestor
) -> Iterator[FlaskClient]:
    yield create_app(store, feed).test_client()


def test_owner_check_treats_only_an_explicit_visitor_as_one() -> None:
    assert is_owner_request(None)
    assert is_owner_request("")
    assert is_owner_request("not json")
    assert is_owner_request(json.dumps({"owner": True}))
    assert not is_owner_request(_VISITOR)


def test_visitors_are_refused_everywhere(client: FlaskClient) -> None:
    assert (
        client.get("/v1/totals", headers={"X-Imbue-Identity": _VISITOR}).status_code
        == 403
    )
    assert (
        client.post(
            "/v1/events",
            json=model_call_payload(),
            headers={"X-Imbue-Identity": _VISITOR},
        ).status_code
        == 403
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
