"""Print every Claude config dir in use in this workspace, one per line.

An agent with no account runs on claude's default ``~/.claude``; an agent bound to a
Claude account runs with ``CLAUDE_CONFIG_DIR`` pointed at that account's folder. Each of
those holds its own plugin installs, so refresh_agent_tools.sh refreshes plugins in each.

Run from the repo root: ``uv run --no-sync python system/scripts/claude_config_dirs.py``.
"""

from pathlib import Path

from imbue.chat import accounts
from imbue.chat.harnesses.harness_type import HarnessType


def claude_config_dirs(home: Path | None = None) -> list[Path]:
    default_config_dir = (home or Path.home()) / ".claude"
    account_dirs = [
        accounts.account_dir(account.id, home)
        for account in accounts.read_index(home).accounts
        if accounts.harness_for(account) is HarnessType.CLAUDE
    ]
    return [default_config_dir, *(path for path in account_dirs if path.is_dir())]


def main() -> None:
    for path in claude_config_dirs():
        print(path)


if __name__ == "__main__":
    main()
