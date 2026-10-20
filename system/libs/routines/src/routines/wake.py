"""A skill run: wake the routine's chat with its slash command and wait for the agent's turn to end."""

from collections.abc import Callable
from datetime import datetime
from datetime import timedelta
from typing import Final
from typing import assert_never

from loguru import logger
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.pure import pure
from routines.data_types import WakeOutcome
from routines.errors import ChatAppError
from routines.errors import ChatCreateError
from routines.interfaces import ChatAppInterface
from routines.interfaces import ClockInterface
from routines.primitives import ChatStatusWord
from routines.primitives import RestartVerdict
from routines.primitives import RoutineId
from routines.primitives import RunOutcome
from routines.primitives import RunWarning

POLL_PAUSE_SECONDS: Final[float] = 1.0
# A chat that neither works nor answers this long after the send never started; one that worked and has been
# idle this long with no answer has nothing to say; a chat the app does not list yet this long after its
# create, or after a restart, is gone rather than still being registered.
START_DEADLINE: Final[timedelta] = timedelta(seconds=60)
SUMMARY_MAX_CHARS: Final[int] = 200
CLEAR_COMMAND: Final[str] = "/clear"
NEVER_STARTED_SUMMARY: Final[str] = "The agent never started on the message."
NO_ANSWER_SUMMARY: Final[str] = "The agent finished without answering."
STOPPED_SUMMARY: Final[str] = "The agent stopped before it finished."
NEVER_LISTED_SUMMARY: Final[str] = "The chat app never listed the agent's chat."
_BUSY_STATUSES: Final[frozenset[ChatStatusWord]] = frozenset(
    (ChatStatusWord.WORKING, ChatStatusWord.BACKGROUND, ChatStatusWord.ATTENTION)
)
_GONE_STATUSES: Final[frozenset[ChatStatusWord | None]] = frozenset(
    (None, ChatStatusWord.STOPPED, ChatStatusWord.ERROR)
)


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


class _ChatToWake(FrozenModel):
    """The chat a wake found or made, as the wait needs to know it."""

    chat_id: str = Field(description="The chat's id")
    status: ChatStatusWord | None = Field(description="How the chat app listed it; None for one just made")
    is_fresh: bool = Field(description="Whether it was just made with the command as its first message")


def _find_or_create_chat(
    routine_id: RoutineId,
    title: str,
    command: str,
    known_chat_id: str | None,
    chat_app: ChatAppInterface,
    on_chat_known: Callable[[str], None],
) -> _ChatToWake | WakeOutcome:
    """Find the chat: the one the state names, else one that outlived its state (its agent still carries the
    routine's label, and mngr would refuse to create another under the same name), else make it with the
    command as its first message; the outcome that ends the wake when none of that can be done."""
    chat_id = known_chat_id
    try:
        status = chat_app.chat_status(chat_id) if chat_id is not None else None
        if status is None:
            found_chat_id = chat_app.find_chat(routine_id)
            status = chat_app.chat_status(found_chat_id) if found_chat_id is not None else None
            if status is not None:
                assert found_chat_id is not None
                logger.info("Taking up the chat {} of {}, which its agent still carries", found_chat_id, routine_id)
                chat_id = found_chat_id
                on_chat_known(chat_id)
    except ChatAppError as e:
        # The chat the state names is still the routine's; only the chat app could not say how it is.
        return WakeOutcome(outcome=RunOutcome.FAILED, summary=str(e), chat_id=known_chat_id, warnings=())
    if status is None:
        try:
            chat_id = chat_app.create_chat(title, routine_id, command)
        except ChatCreateError as e:
            return WakeOutcome(outcome=RunOutcome.FAILED, summary=str(e), chat_id=None, warnings=())
        on_chat_known(chat_id)
        return _ChatToWake(chat_id=chat_id, status=None, is_fresh=True)
    assert chat_id is not None
    return _ChatToWake(chat_id=chat_id, status=status, is_fresh=False)


def _restart_busy_chat(
    chat_app: ChatAppInterface,
    clock: ClockInterface,
    routine_id: RoutineId,
    chat_id: str,
    deadline: datetime,
    warnings: tuple[RunWarning, ...],
) -> WakeOutcome | None:
    """Make sure the chat is free: a busy chat is the previous run still going, so it is stopped and started
    again; the outcome that ends the wake when it does not come back idle, else None."""
    logger.warning("Restarting the chat {} of {}: the previous run was still going", chat_id, routine_id)
    chat_app.stop_chat(chat_id)
    chat_app.start_chat(chat_id)
    match _wait_until_idle(chat_app, clock, chat_id, deadline):
        case RestartVerdict.IDLE:
            return None
        case RestartVerdict.GONE:
            return WakeOutcome(
                outcome=RunOutcome.FAILED,
                summary="The agent stopped after the restart.",
                chat_id=chat_id,
                warnings=warnings,
            )
        case RestartVerdict.TIMED_OUT:
            return WakeOutcome(
                outcome=RunOutcome.TIMED_OUT,
                summary="The chat did not come back after a restart.",
                chat_id=chat_id,
                warnings=warnings,
            )
        case _ as unreachable:
            assert_never(unreachable)


def _wait_for_turn(
    chat_app: ChatAppInterface,
    clock: ClockInterface,
    chat_id: str,
    is_fresh_chat: bool,
    sent_at: datetime,
    cursor: str | None,
    deadline: datetime,
    warnings: tuple[RunWarning, ...],
    on_blocked: Callable[[], None],
) -> WakeOutcome:
    """Wait for the turn: poll the chat until the agent has answered, never started, stopped, finished without
    answering, or the deadline passes, telling on_blocked once when the agent waits on the user."""
    is_blocked_told = False
    has_worked = False
    idle_without_answer_since: datetime | None = None
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
                summary=NEVER_LISTED_SUMMARY if status is None else STOPPED_SUMMARY,
                chat_id=chat_id,
                warnings=warnings,
            )
        if status is ChatStatusWord.ATTENTION and not is_blocked_told:
            is_blocked_told = True
            on_blocked()
        if status in _BUSY_STATUSES:
            has_worked = True
            idle_without_answer_since = None
        if status is ChatStatusWord.IDLE:
            text = chat_app.assistant_text_after(chat_id, cursor)
            if text is not None:
                return WakeOutcome(
                    outcome=RunOutcome.SUCCEEDED,
                    summary=summary_of_message(text),
                    chat_id=chat_id,
                    warnings=warnings,
                )
            if not has_worked and now - sent_at > START_DEADLINE:
                return WakeOutcome(
                    outcome=RunOutcome.FAILED, summary=NEVER_STARTED_SUMMARY, chat_id=chat_id, warnings=warnings
                )
            if has_worked:
                if idle_without_answer_since is None:
                    idle_without_answer_since = now
                if now - idle_without_answer_since > START_DEADLINE:
                    return WakeOutcome(
                        outcome=RunOutcome.FAILED, summary=NO_ANSWER_SUMMARY, chat_id=chat_id, warnings=warnings
                    )
        clock.pause(POLL_PAUSE_SECONDS)
        now = clock.now()
    chat_app.interrupt_chat(chat_id)
    return WakeOutcome(
        outcome=RunOutcome.TIMED_OUT,
        summary="The agent was still going when the time ran out.",
        chat_id=chat_id,
        warnings=warnings,
    )


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
    deadline = clock.now() + timeout
    command = slash_command_of(skill)
    chat = _find_or_create_chat(routine_id, title, command, known_chat_id, chat_app, on_chat_known)
    if isinstance(chat, WakeOutcome):
        return chat
    warnings: tuple[RunWarning, ...] = ()
    try:
        cursor: str | None = None
        if not chat.is_fresh:
            if chat.status in _BUSY_STATUSES:
                warnings = (RunWarning.RESTARTED_PREVIOUS_RUN,)
                not_back = _restart_busy_chat(chat_app, clock, routine_id, chat.chat_id, deadline, warnings)
                if not_back is not None:
                    return not_back
            # Start fresh: the send answers once the harness has accepted the text.
            chat_app.send_message(chat.chat_id, CLEAR_COMMAND)
            cursor = chat_app.latest_event_id(chat.chat_id)
            chat_app.send_message(chat.chat_id, command)
        return _wait_for_turn(
            chat_app, clock, chat.chat_id, chat.is_fresh, clock.now(), cursor, deadline, warnings, on_blocked
        )
    except ChatAppError as e:
        return WakeOutcome(outcome=RunOutcome.FAILED, summary=str(e), chat_id=chat.chat_id, warnings=warnings)
