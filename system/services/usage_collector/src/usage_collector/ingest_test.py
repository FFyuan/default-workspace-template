import json
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from usage_collector.feed import UsageFeed
from usage_collector.ingest import Ingestor, IngestOutcome
from usage_collector.store import UsageStore
from usage_collector.testing import NOW, model_call_payload, write_claude_session


def _spool(directory: Path, payload: object) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid4().hex}.json"
    path.write_text(json.dumps(payload) if not isinstance(payload, str) else payload)
    return path


def test_ingest_prices_stores_and_publishes(
    ingestor: Ingestor, store: UsageStore, feed: UsageFeed
) -> None:
    subscription = feed.subscribe()

    assert ingestor.ingest(model_call_payload()) == (IngestOutcome.STORED, None)

    published = json.loads(subscription.events.get_nowait())
    assert published["cost_provenance"] == "ESTIMATED"
    assert store.totals([], NOW - timedelta(hours=1))[0].calls == 1


def test_a_replayed_event_is_a_duplicate_and_not_republished(
    ingestor: Ingestor, feed: UsageFeed
) -> None:
    payload = model_call_payload()
    ingestor.ingest(payload)
    subscription = feed.subscribe()

    assert ingestor.ingest(payload) == (IngestOutcome.DUPLICATE, None)
    assert subscription.events.empty()


def test_an_invalid_event_is_rejected_with_a_reason(ingestor: Ingestor) -> None:
    outcome, reason = ingestor.ingest(model_call_payload(prompt="never stored"))

    assert outcome == IngestOutcome.REJECTED
    assert reason is not None and "prompt" in reason


def test_draining_the_events_spool_deletes_ingested_files_and_sets_rejects_aside(
    tmp_path: Path, ingestor: Ingestor
) -> None:
    spool = tmp_path / "events"
    good = _spool(spool, model_call_payload())
    bad = _spool(spool, "{not json")

    counts = ingestor.drain_events_spool(spool)

    assert counts[IngestOutcome.STORED] == 1 and counts[IngestOutcome.REJECTED] == 1
    assert not good.exists() and not bad.exists()
    assert (spool / "rejected" / bad.name).exists()


def test_a_reported_claude_session_is_read_from_its_log_which_is_then_deleted(
    tmp_path: Path, ingestor: Ingestor, store: UsageStore
) -> None:
    session_id = "4d2f8e61-9a07-4c3b-b5e8-1f6d0a7c2e93"
    log = write_claude_session(tmp_path / "account", session_id, ["req_a", "req_b"])
    report = {
        "config_dir": str(tmp_path / "account"),
        "session_id": session_id,
        "attribution": {
            "workspace_id": "ws-1",
            "origin_kind": "CHAT",
            "origin_id": "c-1",
            "purpose": "CHAT_TITLE",
        },
    }

    counts, reason = ingestor.ingest_claude_session(report)

    assert reason is None and counts[IngestOutcome.STORED] == 2
    assert not log.exists()
    [row] = store.totals(["origin_id", "purpose"], NOW - timedelta(days=1))
    assert row.group == {"origin_id": "c-1", "purpose": "CHAT_TITLE"}
    assert row.calls == 2 and row.cost_usd is not None


def test_a_claude_session_report_keeps_the_log_when_asked(
    tmp_path: Path, ingestor: Ingestor
) -> None:
    session_id = "9c1e4a72-5b38-4f06-a2d9-6e8b07c3f145"
    log = write_claude_session(tmp_path, session_id, ["req_c"])

    ingestor.ingest_claude_session(
        {
            "config_dir": str(tmp_path),
            "session_id": session_id,
            "attribution": {"workspace_id": "ws-1", "origin_kind": "APP"},
            "delete_log": False,
        }
    )

    assert log.exists()


def test_a_claude_session_report_that_is_not_a_uuid_or_has_no_log_is_rejected(
    tmp_path: Path, ingestor: Ingestor
) -> None:
    attribution = {"workspace_id": "ws-1", "origin_kind": "APP"}

    _, traversal = ingestor.ingest_claude_session(
        {
            "config_dir": str(tmp_path),
            "session_id": "../../etc/passwd",
            "attribution": attribution,
        }
    )
    _, missing = ingestor.ingest_claude_session(
        {
            "config_dir": str(tmp_path),
            "session_id": "1f2e3d4c-5b6a-4978-8f6e-5d4c3b2a1908",
            "attribution": attribution,
        }
    )

    assert traversal is not None and "UUID" in traversal
    assert missing is not None and "No session log" in missing


def test_draining_the_claude_sessions_spool_reads_each_session(
    tmp_path: Path, ingestor: Ingestor, store: UsageStore
) -> None:
    session_id = "b7d1e3f5-2a4c-4e6b-8d0f-1a3c5e7b9d2f"
    write_claude_session(tmp_path / "account", session_id, ["req_spooled"])
    spool = tmp_path / "claude-sessions"
    _spool(
        spool,
        {
            "config_dir": str(tmp_path / "account"),
            "session_id": session_id,
            "attribution": {"workspace_id": "ws-1", "origin_kind": "APP"},
        },
    )

    counts = ingestor.drain_claude_sessions_spool(spool)

    assert counts[IngestOutcome.STORED] == 1
    assert list(spool.glob("*.json")) == []
    assert store.totals([], NOW - timedelta(days=1))[0].calls == 1


def test_a_one_shot_of_unknown_billing_is_billed_as_its_account_records(
    tmp_path: Path, ingestor: Ingestor, feed: UsageFeed
) -> None:
    session_id = "0c9e7a51-3b24-4d68-9f1a-8e5d2c7b4a60"
    account = tmp_path / "account"
    write_claude_session(account, session_id, ["req_sub"])
    (account / ".claude.json").write_text(
        json.dumps({"oauthAccount": {"billingType": "stripe_subscription"}})
    )
    subscription = feed.subscribe()

    ingestor.ingest_claude_session(
        {
            "config_dir": str(account),
            "session_id": session_id,
            "attribution": {"workspace_id": "ws-1", "origin_kind": "APP"},
        }
    )

    assert (
        json.loads(subscription.events.get_nowait())["billing_mode"] == "SUBSCRIPTION"
    )
