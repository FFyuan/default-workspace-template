"""A skill run: wake the routine's chat with its slash command and wait for the agent's turn to end."""

from collections.abc import Callable
from datetime import datetime
from datetime import timedelta
from enum import auto
from typing import Final

from loguru import logger
from pydantic import Field

from imbue.imbue_common.enums import UpperCaseStrEnum
from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.pure import pure
from routines.errors import ChatAppError
from routines.errors import ChatCreateError
from routines.interfaces import ChatAppInterface
from routines.interfaces import ClockInterface
from routines.primitives import ChatStatusWord
from routines.primitives import RoutineId
from routines.primitives import RunOutcome
from routines.primitives import RunWarning

POLL_PAUSE_SECONDS: Final[float] = 1.0
# A chat that neither works nor answers this long after the send never started; a chat the app does not list
# yet this long after its create, or after a restart, is gone rather than still being registered.
START_DEADLINE: Final[timedelta] = timedelta(seconds=60)
SUMMARY_MAX_CHARS: Final[int] = 200
CLEAR_COMMAND: Final[str] = "/clear"
NEVER_STARTED_SUMMARY: Final[str] = "The agent never started on the message."
_BUSY_STATUSES: Final[frozenset[ChatStatusWord]] = frozenset(
    (ChatStatusWord.WORKING, ChatStatusWord.BACKGROUND, ChatStatusWord.ATTENTION)
)
_GONE_STATUSES: Final[frozenset[ChatStatusWord | None]] = frozenset(
    (None, ChatStatusWord.STOPPED, ChatStatusWord.ERROR)
)


class RestartVerdict(UpperCaseStrEnum):
    """How a restarted chat came back: ready, gone for good, or not within the run's time."""

    IDLE = auto()
    GONE = auto()
    TIMED_OUT = auto()


class WakeOutcome(FrozenModel):
    """How a skill run ended."""

    outcome: RunOutcome = Field(description="How it ended")
    summary: str = Field(description="One line about it")
    chat_id: str | None = Field(description="The chat it ran in; None when none could be made")
    warnings: tuple[RunWarning, ...] = Field(description="What was worth saying beside the outcome")


@pure
def summary_of_message(text: str | None) -> str:
    """The first non-empty line of the agent's message, cut to fit a row."""
    if text is None:
        return ""
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:SUMMARY_MAX_CHARS]
    return ""


@pure
def slash_command_of(skill: str) -> str:
    return f"/{skill}"


def _wait_until_idle(
    chat_app: ChatAppInterface, clock: ClockInterface, chat_id: str, deadline: datetime
) -> RestartVerdict:
    """Poll a restarted chat until it is idle; one still unlisted, stopped or in error past the start grace is gone."""
    grace_until = clock.now() + START_DEADLINE
    while clock.now() < deadline:
        status = chat_app.chat_status(chat_id)
        if status is ChatStatusWord.IDLE:
            return RestartVerdict.IDLE
        if status in _GONE_STATUSES and clock.now() >= grace_until:
            return RestartVerdict.GONE
        clock.pause(POLL_PAUSE_SECONDS)
    return RestartVerdict.TIMED_OUT


def wake_skill(
    routine_id: RoutineId,
    title: str,
    skill: str,
    known_chat_id: str | None,
    timeout: timedelta,
    chat_app: ChatAppInterface,
    clock: ClockInterface,
    # Told once the first time the agent waits on the user, so the run can be recorded as blocked.
    on_blocked: Callable[[], None],
    # Told the chat id as soon as one is known, so the state keeps it even if the run is cut short.
    on_chat_known: Callable[[str], None],
) -> WakeOutcome:
    """Section 6.4 of the spec: find the chat, make sure it is free, start fresh, wait for the turn, summarize."""
    started_at = clock.now()
    deadline = started_at + timeout
    warnings: list[RunWarning] = []
    command = slash_command_of(skill)

    # Find the chat, or make it with the command as its first message.
    chat_id = known_chat_id
    is_fresh_chat = False
    try:
        status = chat_app.chat_status(chat_id) if chat_id is not None else None
        if status is None:
            chat_id = chat_app.create_chat(title, routine_id, command)
            is_fresh_chat = True
            on_chat_known(chat_id)
    except (ChatCreateError, ChatAppError) as e:
        return WakeOutcome(outcome=RunOutcome.FAILED, summary=str(e), chat_id=None, warnings=())
    assert chat_id is not None

    try:
        cursor: str | None = None
        if not is_fresh_chat:
            # Make sure it is free: a busy chat is the previous run still going.
            if status in _BUSY_STATUSES:
                logger.warning(
                    "Restarting the chat {} of {}: the previous run was still going",
                    chat_id,
                    routine_id,
                )
                chat_app.stop_chat(chat_id)
                chat_app.start_chat(chat_id)
                warnings.append(RunWarning.RESTARTED_PREVIOUS_RUN)
                match _wait_until_idle(chat_app, clock, chat_id, deadline):
                    case RestartVerdict.IDLE:
                        pass
                    case RestartVerdict.GONE:
                        return WakeOutcome(
                            outcome=RunOutcome.FAILED,
                            summary="The agent stopped after the restart.",
                            chat_id=chat_id,
                            warnings=tuple(warnings),
                        )
                    case RestartVerdict.TIMED_OUT:
                        return WakeOutcome(
                            outcome=RunOutcome.TIMED_OUT,
                            summary="The chat did not come back after a restart.",
                            chat_id=chat_id,
                            warnings=tuple(warnings),
                        )
            # Start fresh: the send answers once the harness has accepted the text.
            chat_app.send_message(chat_id, CLEAR_COMMAND)
            cursor = chat_app.latest_event_id(chat_id)
            chat_app.send_message(chat_id, command)
        sent_at = clock.now()

        # Wait for the turn.
        is_blocked_told = False
        has_worked = False
        now = clock.now()
        while now <= deadline:
            status = chat_app.chat_status(chat_id)
            if status is None and is_fresh_chat and now - sent_at <= START_DEADLINE:
                # The chat app lists a just-created agent once its follower has seen it.
                clock.pause(POLL_PAUSE_SECONDS)
                now = clock.now()
                continue
            if status in _GONE_STATUSES:
                return WakeOutcome(
                    outcome=RunOutcome.FAILED,
                    summary="The agent stopped before it finished.",
                    chat_id=chat_id,
                    warnings=tuple(warnings),
                )
            if status is ChatStatusWord.ATTENTION and not is_blocked_told:
                is_blocked_told = True
                on_blocked()
            if status in _BUSY_STATUSES:
                has_worked = True
            if status is ChatStatusWord.IDLE:
                text = chat_app.assistant_text_after(chat_id, cursor)
                if text is not None:
                    return WakeOutcome(
                        outcome=RunOutcome.SUCCEEDED,
                        summary=summary_of_message(text),
                        chat_id=chat_id,
                        warnings=tuple(warnings),
                    )
                if not has_worked and now - sent_at > START_DEADLINE:
                    return WakeOutcome(
                        outcome=RunOutcome.FAILED,
                        summary=NEVER_STARTED_SUMMARY,
                        chat_id=chat_id,
                        warnings=tuple(warnings),
                    )
            clock.pause(POLL_PAUSE_SECONDS)
            now = clock.now()
        chat_app.interrupt_chat(chat_id)
        return WakeOutcome(
            outcome=RunOutcome.TIMED_OUT,
            summary="The agent was still going when the time ran out.",
            chat_id=chat_id,
            warnings=tuple(warnings),
        )
    except ChatAppError as e:
        return WakeOutcome(
            outcome=RunOutcome.FAILED,
            summary=str(e),
            chat_id=chat_id,
            warnings=tuple(warnings),
        )
