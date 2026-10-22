import json
from datetime import timedelta

from flask.testing import FlaskClient

from usage_collector.ingest import Ingestor
from usage_collector.testing import NOW
from usage_collector.testing import model_call_payload

_VISITOR = json.dumps({"owner": False, "user_id": "u-2"})


def test_totals_pass_through_with_their_query(client: FlaskClient, ingestor: Ingestor) -> None:
    ingestor.ingest(model_call_payload(attribution={"origin_id": "files"}))
    ingestor.ingest(model_call_payload(attribution={"origin_id": "routines"}))

    response = client.get(
        "/api/usage/totals",
        query_string={"group_by": "origin_id", "since": (NOW - timedelta(hours=1)).isoformat()},
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert [(row["group"]["origin_id"], row["calls"]) for row in response.get_json()["rows"]] == [
        ("files", 1),
        ("routines", 1),
    ]


def test_latency_and_calls_pass_through(client: FlaskClient, ingestor: Ingestor) -> None:
    payload = model_call_payload()
    ingestor.ingest(payload)

    latency = client.get(
        "/api/usage/latency", query_string={"since": (NOW - timedelta(hours=1)).isoformat()}
    ).get_json()
    calls = client.get("/api/usage/calls", query_string={"model": "anthropic/claude-opus-5-5"}).get_json()

    assert latency["rows"][0]["p50_ms"] == 2000
    assert [call["event"]["event_id"] for call in calls["calls"]] == [payload["event_id"]]


def test_a_collector_error_keeps_its_status_and_detail(client: FlaskClient) -> None:
    response = client.get("/api/usage/totals", query_string={"group_by": "nonsense"})

    assert response.status_code == 400
    assert "Cannot group by" in response.get_json()["detail"]


def test_a_visitor_is_refused_by_the_collector(client: FlaskClient) -> None:
    response = client.get("/api/usage/totals", headers={"X-Imbue-Identity": _VISITOR})

    assert response.status_code == 403


def test_an_unknown_read_is_not_found(client: FlaskClient) -> None:
    assert client.get("/api/usage/events").status_code == 404


def test_an_unreachable_collector_is_503(unreachable_client: FlaskClient) -> None:
    for path in ("/api/usage/totals", "/api/usage/health", "/api/usage/stream"):
        response = unreachable_client.get(path)
        assert response.status_code == 503, path
        assert response.get_json()["detail"] == "The usage collector isn't responding."


def test_collector_health_reports_catching_up(client: FlaskClient) -> None:
    assert client.get("/api/usage/health").get_json() == {"status": "ok", "catching_up": True}


def test_app_names_come_from_the_registry(client: FlaskClient) -> None:
    assert client.get("/api/apps").get_json() == {"display_names": {"files": "Files"}}


def test_the_page_and_its_assets_are_served(client: FlaskClient) -> None:
    page = client.get("/")
    asset = client.get("/assets/app-Ab12cd34.js")

    assert page.status_code == 200 and b"<title>Usage</title>" in page.data
    assert asset.status_code == 200 and "max-age" in asset.headers["Cache-Control"]
    assert client.get("/api/health").get_json() == {"status": "ok", "is_frontend_built": True}
