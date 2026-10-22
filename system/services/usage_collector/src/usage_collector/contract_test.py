"""workspace_usage speaks the model_call schema without importing mngr; these hold it to mngr_usage's."""

from datetime import datetime, timezone
from decimal import Decimal

from imbue.imbue_common.primitives import NonEmptyStr
from imbue.mngr_usage.model_call import ModelCallEvent, OriginKind, UsageContext
from imbue.mngr_usage.model_call import (
    format_usage_context as mngr_format_usage_context,
)
from imbue.mngr_usage.model_call import parse_usage_context as mngr_parse_usage_context
from imbue.mngr_usage.resources import model_call_lib
from workspace_usage.context import (
    USAGE_CONTEXT_FILENAME,
    format_usage_context,
    parse_usage_context,
)
from workspace_usage.events import MODEL_CALL_SCHEMA_VERSION, build_model_call


def test_workspace_usage_events_validate_against_the_schema() -> None:
    at = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
    event = build_model_call(
        event_id="e-1",
        started_at=at,
        ended_at=at,
        provider="anthropic",
        model="claude-haiku-4-5",
        context={"origin_kind": "ROUTINE", "origin_id": "nightly", "run_id": "r-1"},
        workspace_id="ws-1",
        tokens={
            "input": 1,
            "output": 2,
            "cache_read": 3,
            "cache_write": 4,
            "cache_write_1h": 4,
        },
        cost_usd=Decimal("0.5"),
        billing_mode="SUBSCRIPTION",
        status="RATE_LIMITED",
        harness="litellm",
        purpose="APP_CALL",
        modifiers=["FAST_MODE"],
    )

    parsed = ModelCallEvent.model_validate(event)

    assert parsed.schema_version == MODEL_CALL_SCHEMA_VERSION
    assert parsed.attribution.run_id == "r-1"


def test_usage_context_wire_formats_match() -> None:
    context = UsageContext(
        origin_kind=OriginKind.APP,
        origin_id=NonEmptyStr("a,b=c"),
        run_id=NonEmptyStr("r 1"),
    )
    mngr_serialized = mngr_format_usage_context(context)

    assert (
        format_usage_context(
            {"origin_kind": "APP", "origin_id": "a,b=c", "run_id": "r 1"}
        )
        == mngr_serialized
    )
    assert (
        mngr_parse_usage_context(
            format_usage_context(parse_usage_context(mngr_serialized))
        )
        == context
    )


def test_the_usage_context_file_name_matches_what_agent_writers_read() -> None:
    assert USAGE_CONTEXT_FILENAME == model_call_lib.USAGE_CONTEXT_FILENAME
