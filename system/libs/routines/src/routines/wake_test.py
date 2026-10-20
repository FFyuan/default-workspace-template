from datetime import timedelta

from routines.mock_chat_app_test import ScriptedChatApp
from routines.mock_clock_test import FakeClock
from routines.primitives import ChatStatusWord
from routines.primitives import RoutineId
from routines.primitives import RunOutcome
from routines.wake import NEVER_STARTED_SUMMARY
from routines.wake import WakeOutcome
from routines.wake import summary_of_message
from routines.wake import wake_skill

DIGEST = RoutineId("digest")


def _wake(
    chat_app: ScriptedChatApp, clock: FakeClock, known_chat_id: str | None, timeout: timedelta = timedelta(hours=1)
) -> tuple[WakeOutcome, list[bool], list[str]]:
    blocked: list[bool] = []
    known: list[str] = []
    outcome = wake_skill(
        routine_id=DIGEST,
        title="Digest",
        skill="digest",
        known_chat_id=known_chat_id,
        timeout=timeout,
        chat_app=chat_app,
        clock=clock,
        on_blocked=lambda: blocked.append(True),
        on_chat_known=known.append,
    )
    return outcome, blocked, known


def test_the_first_run_creates_the_chat_with_the_skill_as_its_first_message(
    chat_app: ScriptedChatApp, clock: FakeClock
) -> None:
    chat_app.script("agent-created", (ChatStatusWord.WORKING, ChatStatusWord.IDLE), "All set.")

    outcome, _, known = _wake(chat_app, clock, None)

    assert outcome.outcome is RunOutcome.SUCCEEDED
    assert outcome.summary == "All set."
    assert chat_app.created == [("Digest", DIGEST, "/digest")]
    assert chat_app.sent == [], "a fresh chat needs no clear and no second send"
    assert known == ["agent-created"]


def test_a_fresh_chat_the_app_has_not_listed_yet_is_waited_for(chat_app: ScriptedChatApp, clock: FakeClock) -> None:
    """The chat app lists a just-created agent a moment after mngr made it; that moment is not a stopped agent."""
    chat_app.script("agent-created", (ChatStatusWord.WORKING, ChatStatusWord.IDLE), "Done.")
    chat_app.unlisted_polls_by_chat["agent-created"] = 2

    outcome, _, _ = _wake(chat_app, clock, None)

    assert outcome.outcome is RunOutcome.SUCCEEDED
    assert outcome.summary == "Done."


def test_a_fresh_chat_still_unlisted_after_the_start_grace_is_a_failed_run(
    chat_app: ScriptedChatApp, clock: FakeClock
) -> None:
    outcome, _, _ = _wake(chat_app, clock, None)
    assert outcome.outcome is RunOutcome.FAILED
    assert outcome.summary == "The agent stopped before it finished."
    assert sum(clock.pauses) > 60


def test_a_chat_the_app_no_longer_knows_is_made_again(chat_app: ScriptedChatApp, clock: FakeClock) -> None:
    chat_app.script("agent-created", (ChatStatusWord.IDLE,), "ok")
    outcome, _, known = _wake(chat_app, clock, "agent-gone")
    assert outcome.outcome is RunOutcome.SUCCEEDED
    assert known == ["agent-created"]


def test_a_later_run_clears_the_chat_and_sends_the_skill(chat_app: ScriptedChatApp, clock: FakeClock) -> None:
    chat_app.script(
        "agent-1", (ChatStatusWord.IDLE, ChatStatusWord.WORKING, ChatStatusWord.IDLE), "Summarized 3 messages."
    )
    chat_app.event_ids["agent-1"] = "evt-9"

    outcome, _, _ = _wake(chat_app, clock, "agent-1")

    assert outcome.outcome is RunOutcome.SUCCEEDED
    assert chat_app.sent == [("agent-1", "/clear"), ("agent-1", "/digest")]
    assert chat_app.verbs == []


def test_a_create_refusal_is_a_failed_run_with_the_refusal_as_its_summary(
    chat_app: ScriptedChatApp, clock: FakeClock
) -> None:
    chat_app.is_create_refused = True
    outcome, _, _ = _wake(chat_app, clock, None)
    assert outcome.outcome is RunOutcome.FAILED
    assert "sign in" in outcome.summary
    assert outcome.chat_id is None


def test_a_stopped_agent_is_a_failed_run(chat_app: ScriptedChatApp, clock: FakeClock) -> None:
    chat_app.script("agent-1", (ChatStatusWord.IDLE, ChatStatusWord.WORKING, ChatStatusWord.STOPPED), None)
    outcome, _, _ = _wake(chat_app, clock, "agent-1")
    assert outcome.outcome is RunOutcome.FAILED
    assert outcome.summary == "The agent stopped before it finished."


def test_an_agent_waiting_on_the_user_is_reported_once_and_the_run_can_still_succeed(
    chat_app: ScriptedChatApp, clock: FakeClock
) -> None:
    chat_app.script(
        "agent-1",
        (
            ChatStatusWord.IDLE,
            ChatStatusWord.ATTENTION,
            ChatStatusWord.ATTENTION,
            ChatStatusWord.WORKING,
            ChatStatusWord.IDLE,
        ),
        "Thanks, done.",
    )
    outcome, blocked, _ = _wake(chat_app, clock, "agent-1")
    assert outcome.outcome is RunOutcome.SUCCEEDED
    assert blocked == [True]


def test_a_restarted_chat_that_comes_back_stopped_is_a_failed_run_not_a_timeout(
    chat_app: ScriptedChatApp, clock: FakeClock
) -> None:
    chat_app.script("agent-1", (ChatStatusWord.WORKING, ChatStatusWord.STOPPED), None)
    outcome, _, _ = _wake(chat_app, clock, "agent-1", timeout=timedelta(hours=2))
    assert outcome.outcome is RunOutcome.FAILED
    assert outcome.summary == "The agent stopped after the restart."
    assert chat_app.verbs == [("agent-1", "stop"), ("agent-1", "start")]
    assert 60 <= sum(clock.pauses) < 600, "the start grace, not the whole timeout"


def test_a_chat_that_never_starts_is_a_failed_run_after_a_minute(chat_app: ScriptedChatApp, clock: FakeClock) -> None:
    chat_app.script("agent-1", (ChatStatusWord.IDLE,), None)
    outcome, _, _ = _wake(chat_app, clock, "agent-1")
    assert outcome.outcome is RunOutcome.FAILED
    assert outcome.summary == NEVER_STARTED_SUMMARY
    assert sum(clock.pauses) > 60


def test_a_turn_past_the_timeout_is_interrupted(chat_app: ScriptedChatApp, clock: FakeClock) -> None:
    chat_app.script("agent-1", (ChatStatusWord.IDLE, ChatStatusWord.WORKING), None)
    outcome, _, _ = _wake(chat_app, clock, "agent-1", timeout=timedelta(minutes=2))
    assert outcome.outcome is RunOutcome.TIMED_OUT
    assert chat_app.verbs == [("agent-1", "interrupt")]


def test_the_summary_is_the_first_real_line_of_the_message_without_its_heading_marks() -> None:
    assert summary_of_message("\n## Done\nThe rest.") == "Done"
    assert summary_of_message("x" * 300) == "x" * 200
    assert summary_of_message(None) == ""
