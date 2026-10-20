"""Opening the Fix chat: the brief goes to the chat app's create route through the workspace's chat script."""

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Final

from loguru import logger

from routines_app.errors import FixChatError

MESSAGE_CHAT_SCRIPT: Final[Path] = Path("system/scripts/message_chat.py")
# The create makes an agent and waits on the chat app; a couple of minutes is the ceiling.
CREATE_TIMEOUT_SECONDS: Final[float] = 120.0

# What the app's fix route calls: the brief and the chat's name in, the chat's id out, FixChatError when none.
FixChatStarter = Callable[[str, str], str]


def subprocess_fix_chat_starter(repo_root: Path) -> FixChatStarter:
    """The starter the served app uses: the workspace's chat script, run from the repo root."""
    return lambda brief, name: start_fix_chat(brief, name, repo_root)


def start_fix_chat(brief: str, name: str, repo_root: Path) -> str:
    """Create the chat with the brief as its first message and the window surfaced; answers its id or raises."""
    argv = [
        "python3",
        str(repo_root / MESSAGE_CHAT_SCRIPT),
        "--create",
        "--name",
        name,
        "--label",
        "auto_open=true",
        "-m",
        brief,
    ]
    try:
        completed = subprocess.run(
            argv, cwd=repo_root, capture_output=True, text=True, timeout=CREATE_TIMEOUT_SECONDS, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise FixChatError(f"The chat could not be started ({e}).") from e
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        logger.warning("Starting a fix chat failed (rc={}): {}", completed.returncode, detail)
        raise FixChatError(detail or "The chat could not be started.")
    chat_id = chat_id_from_output(completed.stdout)
    if chat_id is None:
        logger.warning("The fix chat create printed no chat id: {}", completed.stdout.strip()[:200])
        raise FixChatError("The chat was started but its id could not be read.")
    return chat_id


def chat_id_from_output(stdout: str) -> str | None:
    """The chat id from the create's JSON line (the script always prints one on success); None when it is missing."""
    for line in reversed(stdout.strip().splitlines()):
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("chat_id"), str) and parsed["chat_id"]:
            return parsed["chat_id"]
    return None
