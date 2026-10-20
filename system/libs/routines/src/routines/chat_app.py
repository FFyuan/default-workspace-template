"""The chat app over HTTP, and ``mngr create`` for a chat that does not exist yet."""

import json
import os
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any
from typing import Final
from uuid import uuid4

import httpx
from loguru import logger
from pydantic import Field

from routines.errors import ChatAppError
from routines.errors import ChatCreateError
from routines.interfaces import ChatAppInterface
from routines.interfaces import ClockInterface
from routines.primitives import ChatStatusWord
from routines.primitives import RoutineId
from routines.registry import chat_app_url

# The create template every routine's chat is made from: the one the automation runner used.
AUTOMATION_TEMPLATE: Final[str] = "automation"
CONNECT_TIMEOUT_SECONDS: Final[float] = 3.0
READ_TIMEOUT_SECONDS: Final[float] = 30.0
# A send answers only once the harness has accepted the text, which can take a while on a cold agent.
SEND_READ_TIMEOUT_SECONDS: Final[float] = 300.0
# A 503 is the chat app up but not ready; it is retried for this long before it counts as a refusal.
NOT_READY_RETRY_WINDOW_SECONDS: Final[float] = 30.0
NOT_READY_RETRY_PAUSE_SECONDS: Final[float] = 1.0
CREATE_TIMEOUT_SECONDS: Final[float] = 300.0
_EVENTS_PAGE_LIMIT: Final[int] = 200
_ASSISTANT_MESSAGE_TYPE: Final[str] = "assistant_message"


def workspace_label(environ: dict[str, str]) -> str:
    """The workspace the services agent belongs to, so the routine's chat groups with the user's other chats."""
    host_dir = environ.get("MNGR_HOST_DIR", "")
    agent_id = environ.get("MNGR_AGENT_ID", "")
    if host_dir and agent_id:
        try:
            labels = json.loads((Path(host_dir) / "agents" / agent_id / "data.json").read_text()).get("labels", {})
        except (OSError, ValueError):
            labels = {}
        if isinstance(labels, dict) and isinstance(labels.get("workspace"), str) and labels["workspace"]:
            return labels["workspace"]
    if host_dir:
        try:
            host_name = json.loads((Path(host_dir) / "data.json").read_text()).get("host_name", "")
        except (OSError, ValueError):
            host_name = ""
        if isinstance(host_name, str):
            return host_name
    return ""


def _created_agent_id(stdout: str) -> str:
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("event") == "created" and isinstance(event.get("agent_id"), str):
            return event["agent_id"]
    return ""


class HttpChatApp(ChatAppInterface):
    """The chat app reached on loopback, found through the app registry."""

    repo_root: Path = Field(frozen=True, description="The workspace checkout, which a create runs from")
    registry_path: Path = Field(frozen=True, description="The app registry, where the chat app's address is")
    environ: dict[str, str] = Field(frozen=True, description="The process environment")
    clock: ClockInterface = Field(frozen=True, description="For the pauses between not-ready retries")

    def _base_url(self) -> str:
        return chat_app_url(self.registry_path)

    def _request(self, method: str, path: str, body: dict[str, Any] | None, read_timeout: float) -> httpx.Response:
        url = f"{self._base_url()}{path}"
        timeout = httpx.Timeout(connect=CONNECT_TIMEOUT_SECONDS, read=read_timeout, write=10.0, pool=10.0)
        try:
            return httpx.request(method, url, json=body, timeout=timeout)
        except httpx.HTTPError as e:
            raise ChatAppError(f"The chat app could not be reached ({e}).") from e

    def _request_until_ready(
        self, method: str, path: str, body: dict[str, Any] | None, read_timeout: float
    ) -> httpx.Response:
        """Request, retrying a 503 (the chat app up but not ready) for a bounded window."""
        deadline = self.clock.now().timestamp() + NOT_READY_RETRY_WINDOW_SECONDS
        response = self._request(method, path, body, read_timeout)
        while response.status_code == 503 and self.clock.now().timestamp() < deadline:
            self.clock.pause(NOT_READY_RETRY_PAUSE_SECONDS)
            response = self._request(method, path, body, read_timeout)
        return response

    def _detail(self, response: httpx.Response) -> str:
        try:
            parsed = response.json()
        except ValueError:
            return response.text.strip()[:200]
        if isinstance(parsed, dict):
            for key in ("detail", "error", "message"):
                if isinstance(parsed.get(key), str):
                    return parsed[key]
        return response.text.strip()[:200]

    def chat_status(self, chat_id: str) -> ChatStatusWord | None:
        response = self._request_until_ready("GET", "/api/chats", None, READ_TIMEOUT_SECONDS)
        if response.status_code != 200:
            raise ChatAppError(f"The chat app answered {response.status_code} for the chat list.")
        try:
            chats = response.json().get("chats", [])
        except (ValueError, AttributeError) as e:
            raise ChatAppError("The chat app's chat list is not JSON.") from e
        for chat in chats:
            if isinstance(chat, dict) and chat.get("chat_id") == chat_id:
                status = str(chat.get("status", "")).upper()
                return ChatStatusWord(status) if status in ChatStatusWord.__members__ else ChatStatusWord.UNKNOWN
        return None

    def _post_verb(self, chat_id: str, verb: str) -> None:
        response = self._request_until_ready(
            "POST", f"/api/chats/{urllib.parse.quote(chat_id)}/{verb}", {}, READ_TIMEOUT_SECONDS
        )
        if response.status_code >= 300:
            raise ChatAppError(f"The chat app refused to {verb} the chat: {self._detail(response)}")

    def stop_chat(self, chat_id: str) -> None:
        self._post_verb(chat_id, "stop")

    def start_chat(self, chat_id: str) -> None:
        self._post_verb(chat_id, "start")

    def interrupt_chat(self, chat_id: str) -> None:
        self._post_verb(chat_id, "interrupt")

    def send_message(self, chat_id: str, text: str) -> None:
        body = {"message": text, "message_id": uuid4().hex}
        response = self._request_until_ready(
            "POST",
            f"/api/chats/{urllib.parse.quote(chat_id)}/message",
            body,
            SEND_READ_TIMEOUT_SECONDS,
        )
        if response.status_code >= 300:
            raise ChatAppError(f"The chat app refused the message: {self._detail(response)}")

    def _events(self, chat_id: str, query: str) -> list[dict[str, Any]]:
        response = self._request_until_ready(
            "GET",
            f"/api/chats/{urllib.parse.quote(chat_id)}/events?{query}",
            None,
            READ_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            raise ChatAppError(f"The chat app answered {response.status_code} for the chat's transcript.")
        try:
            events = response.json().get("events", [])
        except (ValueError, AttributeError) as e:
            raise ChatAppError("The chat app's transcript is not JSON.") from e
        return [event for event in events if isinstance(event, dict)]

    def latest_event_id(self, chat_id: str) -> str | None:
        events = self._events(chat_id, "limit=1")
        if not events:
            return None
        event_id = events[-1].get("event_id")
        return event_id if isinstance(event_id, str) else None

    def assistant_text_after(self, chat_id: str, cursor_event_id: str | None) -> str | None:
        if cursor_event_id is not None:
            try:
                events = self._events(
                    chat_id,
                    f"after={urllib.parse.quote(cursor_event_id)}&limit={_EVENTS_PAGE_LIMIT}",
                )
            except ChatAppError:
                # A cleared chat starts a fresh transcript, so the cursor is gone; the tail is the answer then.
                events = self._events(chat_id, f"limit={_EVENTS_PAGE_LIMIT}")
        else:
            events = self._events(chat_id, f"limit={_EVENTS_PAGE_LIMIT}")
        for event in reversed(events):
            if event.get("type") == _ASSISTANT_MESSAGE_TYPE and isinstance(event.get("text"), str):
                return event["text"]
        return None

    def create_chat(self, name: str, routine_id: RoutineId, first_message: str) -> str:
        argv = [
            "uv",
            "run",
            "--no-sync",
            "mngr",
            "create",
            str(routine_id),
            "--template",
            AUTOMATION_TEMPLATE,
            "--no-connect",
            "--format",
            "jsonl",
            "--label",
            f"routine={routine_id}",
            "--label",
            f"display_name={name}",
        ]
        workspace = workspace_label(self.environ)
        if workspace:
            argv += ["--label", f"workspace={workspace}"]
        argv += ["--message", first_message]
        try:
            completed = subprocess.run(
                argv,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=CREATE_TIMEOUT_SECONDS,
                check=False,
                env={**os.environ, **self.environ},
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            raise ChatCreateError(f"The chat could not be created ({e}).") from e
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip().splitlines()
            reason = detail[-1] if detail else f"mngr create exited {completed.returncode}"
            raise ChatCreateError(f"The chat could not be created: {reason}")
        chat_id = _created_agent_id(completed.stdout)
        if not chat_id:
            raise ChatCreateError("The chat was created but mngr named no agent in its output.")
        logger.debug("Created the chat {} for the routine {}", chat_id, routine_id)
        return chat_id
