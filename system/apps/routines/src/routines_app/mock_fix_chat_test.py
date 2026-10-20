from pydantic import Field

from imbue.imbue_common.mutable_model import MutableModel
from routines_app.errors import FixChatError


class RecordingFixChatStarter(MutableModel):
    """A fix-chat starter that keeps every brief instead of creating a chat."""

    started: list[tuple[str, str]] = Field(default_factory=list, description="Every (brief, name), in order")
    chat_id: str = Field(default="agent-fix", description="The id it answers")
    refusal: str | None = Field(default=None, description="When set, every start raises with this text")

    def __call__(self, brief: str, name: str) -> str:
        if self.refusal is not None:
            raise FixChatError(self.refusal)
        self.started.append((brief, name))
        return self.chat_id
