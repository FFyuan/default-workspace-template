from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from routines.errors import ChatAppError
from routines.errors import ChatCreateError
from routines.interfaces import ChatAppInterface
from routines.primitives import ChatStatusWord
from routines.primitives import RoutineId


class ScriptedChat(FrozenModel):
    """One chat as the scripted app plays it: what its status reads on each poll, and what the agent says."""

    statuses: tuple[ChatStatusWord, ...] = Field(description="The status answered on each poll; the last repeats")
    reply: str | None = Field(description="The agent's message once the chat is idle; None for no reply")


class ScriptedChatApp(ChatAppInterface):
    """A chat app that answers from a script and records what it was asked to do."""

    chats: dict[str, ScriptedChat] = Field(default_factory=dict, description="The chats it knows")
    polls_by_chat: dict[str, int] = Field(default_factory=dict, description="How many status polls each chat had")
    sent: list[tuple[str, str]] = Field(default_factory=list, description="Every message sent, in order")
    verbs: list[tuple[str, str]] = Field(default_factory=list, description="Every stop, start or interrupt")
    created: list[tuple[str, RoutineId, str]] = Field(default_factory=list, description="Every chat created")
    next_created_id: str = Field(default="agent-created", description="The id the next create answers")
    is_create_refused: bool = Field(default=False, description="Whether creates fail")
    event_ids: dict[str, str] = Field(default_factory=dict, description="The latest event id per chat")
    unlisted_polls_by_chat: dict[str, int] = Field(
        default_factory=dict, description="How many status polls a chat is left out of the list for, as a fresh one is"
    )

    def script(self, chat_id: str, statuses: tuple[ChatStatusWord, ...], reply: str | None) -> None:
        self.chats[chat_id] = ScriptedChat(statuses=statuses, reply=reply)
        self.polls_by_chat[chat_id] = 0

    def chat_status(self, chat_id: str) -> ChatStatusWord | None:
        if self.unlisted_polls_by_chat.get(chat_id, 0) > 0:
            self.unlisted_polls_by_chat[chat_id] -= 1
            return None
        chat = self.chats.get(chat_id)
        if chat is None:
            return None
        index = self.polls_by_chat.get(chat_id, 0)
        self.polls_by_chat[chat_id] = index + 1
        return chat.statuses[min(index, len(chat.statuses) - 1)]

    def stop_chat(self, chat_id: str) -> None:
        self.verbs.append((chat_id, "stop"))

    def start_chat(self, chat_id: str) -> None:
        self.verbs.append((chat_id, "start"))

    def interrupt_chat(self, chat_id: str) -> None:
        self.verbs.append((chat_id, "interrupt"))

    def send_message(self, chat_id: str, text: str) -> None:
        if chat_id not in self.chats:
            raise ChatAppError("The chat app refused the message: no such chat.")
        self.sent.append((chat_id, text))

    def latest_event_id(self, chat_id: str) -> str | None:
        return self.event_ids.get(chat_id)

    def assistant_text_after(self, chat_id: str, cursor_event_id: str | None) -> str | None:
        chat = self.chats.get(chat_id)
        return chat.reply if chat is not None else None

    def create_chat(self, name: str, routine_id: RoutineId, first_message: str) -> str:
        if self.is_create_refused:
            raise ChatCreateError("The chat could not be created: sign in to a provider first.")
        self.created.append((name, routine_id, first_message))
        return self.next_created_id
