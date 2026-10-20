"""Opening the Fix chat: the brief goes to the chat app's create route through the workspace's chat script."""

import json
import subprocess
from pathlib import Path
from typing import Final

from loguru import logger

from routines_app.errors import FixChatError

MESSAGE_CHAT_SCRIPT: Final[Path] = Path("system/scripts/message_chat.py")
# The create makes an agent and waits on the chat app; a couple of minutes is the ceiling.
CREATE_TIMEOUT_SECONDS: Final[float] = 120.0


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
    return chat_id_from_output(completed.stdout)


def chat_id_from_output(stdout: str) -> str:
    """The chat id from the create's JSON line; empty when the line is missing, since the chat exists either way."""
    for line in reversed(stdout.strip().splitlines()):
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("chat_id"), str):
            return parsed["chat_id"]
    return ""
