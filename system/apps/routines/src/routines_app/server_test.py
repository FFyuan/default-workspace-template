from pathlib import Path

from flask.testing import FlaskClient

from app_schema.testing import assert_api_schema_describes_app
from routines.data_types import RoutineDefinition
from routines.primitives import RoutineId
from routines.primitives import RunTrigger
from routines.service import RoutinesService

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "app.toml"
SYNC = RoutineId("news-sync")


def _add(service: RoutinesService, **fields: object) -> None:
    values: dict[str, object] = {
        "title": "News sync",
        "what": "Pulls the headlines.",
        "every": "1h",
        "command": ["sh", "-c", "echo ran"],
    }
    values.update(fields)
    service.add(SYNC, RoutineDefinition.model_validate(values))


def test_the_api_document_describes_every_route(client: FlaskClient) -> None:
    assert_api_schema_describes_app(client, MANIFEST_PATH)


def test_every_page_path_serves_the_one_document_and_assets_their_file(client: FlaskClient) -> None:
    for path in ("/", "/news-sync", "/news-sync/runs/run-1"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert b"<title>Routines</title>" in response.data
        assert response.headers["Cache-Control"] == "no-store"
    assert client.get("/assets/app.js").data == b"console.log('built');"
    assert client.get("/assets/missing.js").status_code == 404


def test_the_listing_and_the_detail_answer_the_library_shapes(client: FlaskClient, service: RoutinesService) -> None:
    _add(service)
    listing = client.get("/api/routines").get_json()
    assert [row["routine_id"] for row in listing["routines"]] == ["news-sync"]
    assert listing["routines"][0]["health"] == "NOT_RUN_YET"
    assert listing["summary"]["total"] == 1

    detail = client.get("/api/routines/news-sync").get_json()
    assert detail["row"]["schedule_text"] == "Every hour"
    assert detail["definition"]["command"] == ["sh", "-c", "echo ran"]
    assert detail["runs"] == []

    assert client.get("/api/routines/nothing").status_code == 404
    assert client.get("/api/routines/Not%20An%20Id").status_code == 404


def test_the_switch_and_the_schedule_change_answer_the_updated_row(
    client: FlaskClient, service: RoutinesService
) -> None:
    _add(service)
    off = client.put("/api/routines/news-sync/enabled", json={"is_enabled": False})
    assert off.status_code == 200
    assert off.get_json()["health"] == "OFF"

    changed = client.put(
        "/api/routines/news-sync/schedule",
        json={"every": "1d", "at": "07:30", "days": ["mon", "fri"], "day_of_month": None, "once": None},
    )
    assert changed.status_code == 200, changed.get_json()
    assert changed.get_json()["schedule_text"] == "Every Monday and Friday at 7:30 am"
    assert (service.paths.definitions_dir / "news-sync.toml").read_text().count("07:30") == 1

    refused = client.put(
        "/api/routines/news-sync/schedule",
        json={"every": "15m", "at": "07:30", "days": [], "day_of_month": None, "once": None},
    )
    assert refused.status_code == 400
    assert "a day or longer" in refused.get_json()["detail"]


def test_a_run_and_its_log_are_read_back(client: FlaskClient, service: RoutinesService) -> None:
    _add(service)
    event = service.runner.run(SYNC, RunTrigger.MANUAL, None)

    run = client.get(f"/api/routines/news-sync/runs/{event.run_id}")
    assert run.status_code == 200
    assert run.get_json()["run"]["outcome"] == "SUCCEEDED"
    assert "ran" in run.get_json()["log"]
    assert client.get(f"/api/routines/news-sync/runs/{event.run_id}/log").data == b"ran\n"
    assert client.get("/api/routines/news-sync/runs/run-00000000000000000000000000000000").status_code == 404

    detail = client.get("/api/routines/news-sync").get_json()
    assert [run["run_id"] for run in detail["runs"]] == [event.run_id]
    assert detail["row"]["last_run_text"].startswith("Worked")


def test_removing_a_routine_deletes_it(client: FlaskClient, service: RoutinesService) -> None:
    _add(service)
    assert client.delete("/api/routines/news-sync").status_code == 204
    assert client.get("/api/routines/news-sync").status_code == 404
    assert client.delete("/api/routines/news-sync").status_code == 404


def test_a_preview_refuses_every_change(preview_client: FlaskClient, service: RoutinesService) -> None:
    _add(service)
    assert preview_client.get("/api/routines").status_code == 200
    assert preview_client.post("/api/routines/news-sync/run", json={}).status_code == 409
    assert preview_client.put("/api/routines/news-sync/enabled", json={"is_enabled": False}).status_code == 409
    assert preview_client.delete("/api/routines/news-sync").status_code == 409
    assert service.detail(SYNC).row.is_enabled


def test_the_health_probe_says_whether_the_pages_are_built(client: FlaskClient) -> None:
    assert client.get("/api/health").get_json() == {"status": "ok", "is_frontend_built": True}
