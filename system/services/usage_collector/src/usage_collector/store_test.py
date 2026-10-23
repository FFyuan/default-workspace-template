from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from imbue.mngr_usage.model_call import ModelCallEvent, price_model_call

from usage_collector.limits import LimitReading
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


def test_summed_costs_carry_no_float_noise(store: UsageStore) -> None:
    for _ in range(3):
        store.insert(_event(cost_usd="0.1", cost_provenance="REPORTED"))

    [row] = store.totals([], NOW - timedelta(hours=1))

    assert row.cost_usd == Decimal("0.3")


def _timed(seconds: float, **overrides: object) -> ModelCallEvent:
    return _event(
        started_at=(NOW - timedelta(seconds=seconds)).isoformat(),
        ended_at=NOW.isoformat(),
        **overrides,
    )


def test_latency_percentiles_leave_out_untimed_calls_and_count_them(
    store: UsageStore,
) -> None:
    for seconds in (1, 2, 3, 4, 10):
        store.insert(_timed(seconds))
    store.insert(_timed(0))

    [row] = store.latency([], NOW - timedelta(hours=1))

    assert (row.timed_calls, row.untimed_calls) == (5, 1)
    assert (row.p50_ms, row.p95_ms) == (3000, 10000)


def test_latency_counts_log_timed_calls_as_approximate_per_group(
    store: UsageStore,
) -> None:
    store.insert(_timed(2, attribution={"harness": "claude"}))
    store.insert(_timed(1, model="anthropic/claude-haiku-4-5"))

    rows = {
        row.group["model"]: row
        for row in store.latency(["model"], NOW - timedelta(hours=1))
    }

    assert rows["anthropic/claude-opus-5-5"].approximate_calls == 1
    assert rows["anthropic/claude-haiku-4-5"].approximate_calls == 0
    assert rows["anthropic/claude-haiku-4-5"].p50_ms == 1000


def test_a_group_of_only_untimed_calls_has_no_percentiles(store: UsageStore) -> None:
    store.insert(_timed(0))

    [row] = store.latency([], NOW - timedelta(hours=1))

    assert (row.timed_calls, row.untimed_calls, row.p50_ms) == (0, 1, None)


def test_calls_are_newest_first_and_page_back_with_before(store: UsageStore) -> None:
    events = [
        _event(
            ended_at=(NOW - timedelta(minutes=minutes)).isoformat(),
            started_at=(NOW - timedelta(minutes=minutes, seconds=1)).isoformat(),
        )
        for minutes in (3, 1, 2)
    ]
    for event in events:
        store.insert(event)

    first_page = store.calls({}, limit=2)
    second_page = store.calls({}, limit=2, before=str(first_page[-1].event["event_id"]))

    assert [call.event["event_id"] for call in first_page + second_page] == [
        events[1].event_id,
        events[2].event_id,
        events[0].event_id,
    ]


def test_calls_page_by_offset_and_count_what_the_filters_keep(
    store: UsageStore,
) -> None:
    events = [
        _event(
            ended_at=(NOW - timedelta(minutes=minutes)).isoformat(),
            started_at=(NOW - timedelta(minutes=minutes, seconds=1)).isoformat(),
        )
        for minutes in (1, 2, 3)
    ]
    for event in events:
        store.insert(event)

    second_page = store.calls({}, limit=2, offset=2)

    assert [call.event["event_id"] for call in second_page] == [events[2].event_id]
    assert store.count_calls({}) == 3
    assert store.count_calls({"model": ["nobody/model"]}) == 0


def test_calls_after_a_sequence_are_the_ones_stored_since(store: UsageStore) -> None:
    store.insert(_event())
    [seen] = store.calls({})
    later = _event(
        ended_at=(NOW - timedelta(hours=1)).isoformat(),
        started_at=(NOW - timedelta(hours=1, seconds=1)).isoformat(),
    )
    store.insert(later)

    assert [
        call.event["event_id"] for call in store.calls({}, after=seen.sequence)
    ] == [later.event_id]


def test_calls_filter_by_rollup_dimensions(store: UsageStore) -> None:
    store.insert(_event(attribution={"origin_id": "files"}))
    store.insert(_event(attribution={"origin_id": "routines"}))

    [call] = store.calls({"origin_id": ["routines"]})

    assert ModelCallEvent.model_validate(call.event).attribution.origin_id == "routines"
    with pytest.raises(UsageStoreError):
        store.calls({"harness": ["litellm"]})


def test_totals_group_by_cost_provenance(store: UsageStore) -> None:
    store.insert(_event())
    store.insert(_event(cost_usd="0.5", cost_provenance="REPORTED"))

    rows = {
        row.group["cost_provenance"]: row.calls
        for row in store.totals(["cost_provenance"], NOW - timedelta(hours=1))
    }

    assert rows == {"ESTIMATED": 1, "REPORTED": 1}


def _reading(used: float, minutes_ago: int, window: str = "five_hour") -> LimitReading:
    return LimitReading(
        source="claude",
        window=window,
        used_percentage=used,
        window_seconds=18000 if window == "five_hour" else 604800,
        observed_at=NOW - timedelta(minutes=minutes_ago),
    )


def test_the_freshest_limit_reading_wins_whatever_order_it_arrives_in(
    store: UsageStore,
) -> None:
    store.record_limits([_reading(40, minutes_ago=5)])
    store.record_limits([_reading(10, minutes_ago=60)])

    [reading] = store.limits(NOW - timedelta(days=7))

    assert reading.used_percentage == 40


def test_limits_come_shortest_window_first_and_old_ones_drop_out(
    store: UsageStore,
) -> None:
    store.record_limits(
        [_reading(8, minutes_ago=1, window="seven_day"), _reading(28, minutes_ago=1)]
    )

    assert [r.window for r in store.limits(NOW - timedelta(days=7))] == [
        "five_hour",
        "seven_day",
    ]
    assert store.limits(NOW) == []


def test_latency_filters_keep_calls_with_any_of_the_given_values(
    store: UsageStore,
) -> None:
    store.insert(_timed(1, billing_mode="API_KEY"))
    store.insert(_timed(3, billing_mode="UNKNOWN"))
    store.insert(_timed(9, billing_mode="SUBSCRIPTION"))

    [row] = store.latency(
        [], NOW - timedelta(hours=1), filters={"billing_mode": ["API_KEY", "UNKNOWN"]}
    )

    assert (row.timed_calls, row.p95_ms) == (2, 3000)
    with pytest.raises(UsageStoreError):
        store.latency([], NOW - timedelta(hours=1), filters={"nonsense": ["x"]})


def test_calls_filter_by_provider_and_any_of_several_values(store: UsageStore) -> None:
    store.insert(_event(billing_mode="API_KEY"))
    store.insert(_event(billing_mode="UNKNOWN"))
    store.insert(_event(billing_mode="SUBSCRIPTION"))
    store.insert(
        _event(provider="openai", model="openai/gpt-5.2", billing_mode="API_KEY")
    )

    calls = store.calls(
        {"provider": ["anthropic"], "billing_mode": ["API_KEY", "UNKNOWN"]}
    )

    assert sorted(str(call.event["billing_mode"]) for call in calls) == [
        "API_KEY",
        "UNKNOWN",
    ]
