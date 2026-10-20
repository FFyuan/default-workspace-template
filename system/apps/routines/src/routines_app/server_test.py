import os
import threading
import time
from pathlib import Path

from flask.testing import FlaskClient

from app_schema.testing import assert_api_schema_describes_app
from imbue.imbue_common.model_update import to_update
from routines.data_types import CurrentRun
from routines.data_types import RoutineDefinition
from routines.locks import held_lock
from routines.primitives import RoutineId
from routines.primitives import RunId
from routines.primitives import RunTrigger
from routines.service import RoutinesService
from routines.testing import TEST_NOW
from routines_app.mock_fix_chat_test import RecordingFixChatStarter
from routines_app.server import create_app

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "app.toml"
SYNC = RoutineId("news-sync")


def _add(service: RoutinesService) -> None:
    values: dict[str, object] = {
        "title": "News sync",
        "what": "Pulls the headlines.",
        "every": "1h",
        "command": ["sh", "-c", "echo ran"],
    }
    service.add(SYNC, RoutineDefinition.model_validate(values))


def test_the_api_document_describes_every_route(client: FlaskClient) -> None:
    assert_api_schema_describes_app(client, MANIFEST_PATH)


def test_every_page_path_serves_the_one_document_and_assets_their_file(
    client: FlaskClient, service: RoutinesService
) -> None:
    service.registry_path.parent.mkdir(parents=True, exist_ok=True)
    service.registry_path.write_text(
        '[[apps]]\nname = "chat"\nurl = "http://127.0.0.1:8010"\nlabel = "chat-x7k9q2w1"\n'
    )
    for path in ("/", "/news-sync", "/news-sync/runs/run-1"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert b"<title>Routines</title>" in response.data
        # The chat app's minted origin label rides in the document, so the pages can link a run's chat.
        assert b'<meta name="routines-chat-label" content="chat-x7k9q2w1">' in response.data
        assert response.headers["Cache-Control"] == "no-store"
    assert client.get("/assets/app.js").data == b"console.log('built');"
    assert client.get("/assets/missing.js").status_code == 404


def test_the_document_carries_no_chat_label_before_the_chat_app_registers(client: FlaskClient) -> None:
    assert b'<meta name="routines-chat-label" content="">' in client.get("/").data


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
    unknown_run = "run-00000000000000000000000000000000"
    assert client.get(f"/api/routines/news-sync/runs/{unknown_run}").status_code == 404
    assert client.get(f"/api/routines/news-sync/runs/{unknown_run}/log").status_code == 404
    assert client.get(f"/api/routines/nothing/runs/{event.run_id}/log").status_code == 404

    detail = client.get("/api/routines/news-sync").get_json()
    assert [run["run_id"] for run in detail["runs"]] == [event.run_id]
    assert detail["row"]["last_run_text"].startswith("Worked")


def test_run_now_answers_a_receipt_and_refuses_a_second_run_while_one_holds_the_lock(
    client: FlaskClient, service: RoutinesService
) -> None:
    _add(service)
    with held_lock(service.paths.run_lock_path(SYNC), "A run"):
        refused = client.post("/api/routines/news-sync/run", json={})
        assert refused.status_code == 409
        assert "already going" in refused.get_json()["detail"]

    started = client.post("/api/routines/news-sync/run", json={})

    assert started.status_code == 200, started.get_json()
    receipt = started.get_json()
    assert receipt["routine_id"] == "news-sync"
    assert receipt["run_id"].startswith("run-")
    # The run goes on in a process of its own; its books close without the app.
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and service.states.read(SYNC).last_run is None:
        threading.Event().wait(0.1)
    last_run = service.states.read(SYNC).last_run
    assert last_run is not None, "the spawned run never finished"
    assert str(last_run.run_id) == receipt["run_id"]
    assert last_run.trigger == "MANUAL"
    assert client.post("/api/routines/nothing/run", json={}).status_code == 404


def test_the_switch_and_the_schedule_of_an_unknown_routine_are_not_found(client: FlaskClient) -> None:
    assert client.put("/api/routines/nothing/enabled", json={"is_enabled": False}).status_code == 404
    schedule = {"every": "1d", "at": "07:30", "days": [], "day_of_month": None, "once": None}
    assert client.put("/api/routines/nothing/schedule", json=schedule).status_code == 404


def test_a_broken_definition_cannot_be_run_and_the_reason_is_a_bad_request(
    client: FlaskClient, service: RoutinesService
) -> None:
    _add(service)
    (service.paths.definitions_dir / "news-sync.toml").write_text('title = "News sync"\n')
    refused = client.post("/api/routines/news-sync/run", json={})
    assert refused.status_code == 400
    assert "cannot run" in refused.get_json()["detail"]


def test_removing_a_routine_deletes_it_once_no_run_is_going(client: FlaskClient, service: RoutinesService) -> None:
    _add(service)
    in_flight = CurrentRun(
        run_id=RunId.generate(), pid=os.getpid(), pid_start="", trigger=RunTrigger.MANUAL, started_at=TEST_NOW
    )
    service.states.update(
        SYNC, lambda state: state.model_copy_update(to_update(state.field_ref().current_run, in_flight))
    )
    refused = client.delete("/api/routines/news-sync")
    assert refused.status_code == 409
    assert "is going" in refused.get_json()["detail"]
    assert client.get("/api/routines/news-sync").status_code == 200

    service.states.update(SYNC, lambda state: state.model_copy_update(to_update(state.field_ref().current_run, None)))
    assert client.delete("/api/routines/news-sync").status_code == 204
    assert client.get("/api/routines/news-sync").status_code == 404
    assert client.delete("/api/routines/news-sync").status_code == 404


def test_the_fix_route_opens_a_chat_briefed_on_the_routine_and_answers_its_id(
    client: FlaskClient, service: RoutinesService, fix_chat_starter: RecordingFixChatStarter
) -> None:
    _add(service)
    response = client.post("/api/routines/news-sync/fix", json={})
    assert response.status_code == 200
    assert response.get_json() == {"chat_id": "agent-fix"}
    ((brief, name),) = fix_chat_starter.started
    assert name == "Fix News sync"
    assert '"News sync"' in brief
    assert "/news-sync" in brief
    assert client.post("/api/routines/nothing/fix", json={}).status_code == 404


def test_a_fix_chat_that_could_not_start_is_a_bad_gateway_with_the_reason(
    client: FlaskClient, service: RoutinesService, fix_chat_starter: RecordingFixChatStarter
) -> None:
    _add(service)
    fix_chat_starter.refusal = "sign in to a provider first"
    response = client.post("/api/routines/news-sync/fix", json={})
    assert response.status_code == 502
    assert "sign in" in response.get_json()["detail"]


def test_a_preview_refuses_every_change(
    preview_client: FlaskClient, service: RoutinesService, fix_chat_starter: RecordingFixChatStarter
) -> None:
    _add(service)
    assert preview_client.get("/api/routines").status_code == 200
    assert preview_client.post("/api/routines/news-sync/run", json={}).status_code == 403
    assert preview_client.put("/api/routines/news-sync/enabled", json={"is_enabled": False}).status_code == 403
    schedule = {"every": "1d", "at": "07:30", "days": [], "day_of_month": None, "once": None}
    assert preview_client.put("/api/routines/news-sync/schedule", json=schedule).status_code == 403
    assert preview_client.post("/api/routines/news-sync/fix", json={}).status_code == 403
    assert preview_client.delete("/api/routines/news-sync").status_code == 403
    assert service.detail(SYNC).row.is_enabled
    assert service.detail(SYNC).row.schedule_text == "Every hour"
    assert fix_chat_starter.started == []


def test_the_health_probe_says_whether_the_pages_are_built(client: FlaskClient) -> None:
    assert client.get("/api/health").get_json() == {"status": "ok", "is_frontend_built": True}


def test_an_unbuilt_frontend_serves_the_not_built_page_and_says_so_in_the_health_probe(
    service: RoutinesService, tmp_path: Path, fix_chat_starter: RecordingFixChatStarter
) -> None:
    unbuilt = create_app(service, tmp_path / "nothing-built", is_preview=False, fix_chat_starter=fix_chat_starter)
    client = unbuilt.test_client()
    page = client.get("/")
    assert page.status_code == 200
    assert b"has not been built yet" in page.data
    assert client.get("/api/health").get_json() == {"status": "ok", "is_frontend_built": False}


def test_a_schedule_body_the_model_refuses_is_a_bad_request(client: FlaskClient, service: RoutinesService) -> None:
    _add(service)
    for body in ({"every": "15x", "at": None, "days": [], "day_of_month": None, "once": None}, ["not", "a", "body"]):
        refused = client.put("/api/routines/news-sync/schedule", json=body)
        assert refused.status_code == 400, body
        assert refused.get_json()["detail"]
    assert service.detail(SYNC).row.schedule_text == "Every hour"
