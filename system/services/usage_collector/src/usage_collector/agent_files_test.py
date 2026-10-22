import json
from datetime import timedelta
from pathlib import Path

from usage_collector.agent_files import follow_agent_event_files
from usage_collector.ingest import Ingestor
from usage_collector.store import UsageStore
from usage_collector.testing import NOW, model_call_payload


def _event_file(host_dir: Path, root: str = "agents", agent: str = "agent-1") -> Path:
    path = host_dir / root / agent / "events" / "claude" / "usage" / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _calls(store: UsageStore) -> int:
    rows = store.totals([], NOW - timedelta(days=1))
    return rows[0].calls if rows else 0


def test_model_call_lines_are_ingested_and_other_lines_skipped(
    tmp_path: Path, store: UsageStore, ingestor: Ingestor
) -> None:
    path = _event_file(tmp_path)
    path.write_text(
        json.dumps(
            {"timestamp": "2026-10-22T00:00:00Z", "session_id": "legacy-snapshot"}
        )
        + "\n"
        + json.dumps(model_call_payload())
        + "\n"
        + '{"schema_version": 1, "half a line'
    )

    assert follow_agent_event_files(tmp_path, store, ingestor.ingest, "ws-host") == 1
    assert _calls(store) == 1


def test_reading_resumes_where_it_left_off_including_a_finished_partial_line(
    tmp_path: Path, store: UsageStore, ingestor: Ingestor
) -> None:
    path = _event_file(tmp_path)
    second = json.dumps(model_call_payload())
    path.write_text(json.dumps(model_call_payload()) + "\n" + second[:20])
    follow_agent_event_files(tmp_path, store, ingestor.ingest, "ws-host")

    with path.open("a") as handle:
        handle.write(second[20:] + "\n")

    assert follow_agent_event_files(tmp_path, store, ingestor.ingest, "ws-host") == 1
    assert follow_agent_event_files(tmp_path, store, ingestor.ingest, "ws-host") == 0
    assert _calls(store) == 2


def test_a_truncated_file_is_read_again_from_the_start_without_double_counting(
    tmp_path: Path, store: UsageStore, ingestor: Ingestor
) -> None:
    path = _event_file(tmp_path)
    first = json.dumps(model_call_payload())
    path.write_text(first + "\n" + json.dumps(model_call_payload()) + "\n")
    follow_agent_event_files(tmp_path, store, ingestor.ingest, "ws-host")

    path.write_text(first + "\n")

    follow_agent_event_files(tmp_path, store, ingestor.ingest, "ws-host")
    assert _calls(store) == 2


def test_preserved_agents_files_are_read_too(
    tmp_path: Path, store: UsageStore, ingestor: Ingestor
) -> None:
    _event_file(tmp_path, root="preserved", agent="old--agent-0").write_text(
        json.dumps(model_call_payload()) + "\n"
    )

    assert follow_agent_event_files(tmp_path, store, ingestor.ingest, "ws-host") == 1


def test_agent_events_are_attributed_to_this_workspace(
    tmp_path: Path, store: UsageStore, ingestor: Ingestor
) -> None:
    _event_file(tmp_path).write_text(
        json.dumps(
            model_call_payload(attribution={"workspace_id": "MacBook-of-the-agent"})
        )
        + "\n"
    )

    follow_agent_event_files(tmp_path, store, ingestor.ingest, "ws-host")

    [row] = store.totals(["origin_kind"], NOW - timedelta(days=1))
    assert row.calls == 1
    [raw] = store.totals(["harness", "origin_id"], NOW - timedelta(days=1))
    assert raw.calls == 1
    assert _workspace_ids(store) == ["ws-host"]


def _workspace_ids(store: UsageStore) -> list[str]:
    return [
        row.group["workspace_id"] or ""
        for row in store.totals(["workspace_id"], NOW - timedelta(days=1))
    ]
