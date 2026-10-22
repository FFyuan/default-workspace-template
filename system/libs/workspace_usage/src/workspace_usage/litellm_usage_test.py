from datetime import datetime
from types import SimpleNamespace
from typing import Any

import litellm

from workspace_usage.litellm_usage import UsageCallback


def _callback(sent: list[Any]) -> UsageCallback:
    return UsageCallback(
        {"origin_kind": "APP", "origin_id": "files"}, "ws-1", emit=sent.append
    )


def _kwargs(**payload: Any) -> dict[str, Any]:
    standard = {
        "id": "chatcmpl-1",
        "custom_llm_provider": "anthropic",
        "model": "claude-haiku-4-5",
        "prompt_tokens": 1200,
        "completion_tokens": 40,
        "response_cost": 0.0021,
        "api_base": "https://api.anthropic.com/v1/messages",
    }
    standard.update(payload)
    return {"standard_logging_object": standard}


def test_a_successful_call_becomes_a_model_call_with_cache_split_out() -> None:
    sent: list[Any] = []
    usage = SimpleNamespace(
        cache_read_input_tokens=1000,
        cache_creation_input_tokens=100,
        prompt_tokens_details=None,
    )

    _callback(sent).log_success_event(
        _kwargs(),
        SimpleNamespace(usage=usage),
        datetime(2026, 10, 22, 12, 0, 0),
        datetime(2026, 10, 22, 12, 0, 1),
    )

    [event] = sent
    assert event["event_id"] == "chatcmpl-1"
    assert event["model"] == "anthropic/claude-haiku-4-5"
    assert event["tokens"] == {
        "input": 100,
        "output": 40,
        "cache_read": 1000,
        "cache_write": 100,
    }
    assert event["cost_usd"] == "0.0021"
    assert event["billing_mode"] == "API_KEY"
    assert event["status"] == "OK"
    assert event["attribution"]["origin_id"] == "files"
    assert event["attribution"]["purpose"] == "APP_CALL"
    assert event["ended_at"].endswith("+00:00")


def test_a_zero_cost_for_a_call_that_used_tokens_is_reported_unknown() -> None:
    sent: list[Any] = []

    _callback(sent).log_success_event(
        _kwargs(response_cost=0.0), SimpleNamespace(usage=None), 0.0, 1.0
    )

    assert "cost_usd" not in sent[0]


def test_a_rate_limited_failure_is_reported_as_such() -> None:
    sent: list[Any] = []
    error = litellm.RateLimitError(
        message="slow down", llm_provider="anthropic", model="claude-haiku-4-5"
    )
    kwargs = _kwargs(prompt_tokens=None, completion_tokens=None, response_cost=None)
    kwargs["exception"] = error

    _callback(sent).log_failure_event(kwargs, None, 0.0, 1.0)

    assert sent[0]["status"] == "RATE_LIMITED"
    assert sent[0]["tokens"] == {}


def test_a_call_through_a_proxy_has_an_unknown_billing_mode() -> None:
    sent: list[Any] = []

    _callback(sent).log_success_event(
        _kwargs(api_base="https://litellm.example.internal"),
        SimpleNamespace(usage=None),
        0.0,
        1.0,
    )

    assert sent[0]["billing_mode"] == "UNKNOWN"
