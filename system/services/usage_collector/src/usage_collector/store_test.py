from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from imbue.mngr_usage.model_call import ModelCallEvent, price_model_call

from usage_collector.store import TimeBucket, UsageStore, UsageStoreError
from usage_collector.testing import NOW, model_call_payload


def _event(**overrides: object) -> ModelCallEvent:
    return price_model_call(
        ModelCallEvent.model_validate(model_call_payload(**overrides))
    )


def test_insert_is_idempotent_by_event_id(store: UsageStore) -> None:
    event = _event()

    assert store.insert(event)
    assert not store.insert(event)

    [row] = store.totals([], NOW - timedelta(hours=1))
    assert row.calls == 1


def test_rollup_and_raw_totals_agree(store: UsageStore) -> None:
    for origin_id in ("files", "files", "routines"):
        store.insert(_event(attribution={"origin_id": origin_id, "harness": "litellm"}))

    from_rollups = store.totals(["origin_id"], NOW - timedelta(hours=1))
    from_raw = store.totals(["origin_id", "harness"], NOW - timedelta(hours=1))

    assert [
        (r.group["origin_id"], r.calls, r.cost_usd, r.tokens) for r in from_rollups
    ] == [(r.group["origin_id"], r.calls, r.cost_usd, r.tokens) for r in from_raw]
    assert from_rollups[0].group == {"origin_id": "files"}
    assert from_rollups[0].calls == 2
    assert from_rollups[0].tokens["input"] == 2000


def test_a_group_whose_calls_all_lack_a_cost_reports_unknown_not_zero(
    store: UsageStore,
) -> None:
    store.insert(_event(model="anthropic/claude-not-real-4471"))
    store.insert(_event())

    rows = {
        r.group["model"]: r for r in store.totals(["model"], NOW - timedelta(hours=1))
    }

    unpriced = rows["anthropic/claude-not-real-4471"]
    assert unpriced.cost_usd is None and unpriced.unknown_cost_calls == 1
    priced = rows["anthropic/claude-opus-5-5"]
    assert priced.cost_usd is not None and priced.cost_usd > Decimal(0)


def test_missing_dimensions_read_back_as_none(store: UsageStore) -> None:
    store.insert(_event())

    [row] = store.totals(["agent_id"], NOW - timedelta(hours=1))

    assert row.group == {"agent_id": None}


def test_totals_bucket_by_hour_and_respect_the_window(store: UsageStore) -> None:
    store.insert(_event())
    store.insert(
        _event(
            ended_at=(NOW - timedelta(hours=3)).isoformat(),
            started_at=(NOW - timedelta(hours=3)).isoformat(),
        )
    )

    rows = store.totals([], NOW - timedelta(hours=5), bucket=TimeBucket.HOUR)
    recent = store.totals([], NOW - timedelta(hours=1))

    assert [row.bucket_start.hour for row in rows if row.bucket_start is not None] == [
        9,
        12,
    ]
    assert recent[0].calls == 1


def test_unknown_group_by_is_refused(store: UsageStore) -> None:
    with pytest.raises(UsageStoreError):
        store.totals(["prompt"], NOW)


def test_prune_drops_old_raw_events_but_keeps_rollups(store: UsageStore) -> None:
    old = (NOW - timedelta(days=91)).isoformat()
    store.insert(
        _event(started_at=old, ended_at=old, attribution={"harness": "litellm"})
    )

    assert store.prune(NOW) == 1
    assert store.totals(["harness"], NOW - timedelta(days=100)) == []
    assert store.totals(["origin_id"], NOW - timedelta(days=100))[0].calls == 1


def test_file_positions_persist(tmp_path: Path, store: UsageStore) -> None:
    path = tmp_path / "events.jsonl"
    assert store.file_position(path) == (None, 0)

    store.set_file_position(path, 42, 1000)
    store.set_file_position(path, 42, 1500)

    assert store.file_position(path) == (42, 1500)
