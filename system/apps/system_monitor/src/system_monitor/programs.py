"""The running programs and who they belong to: each process's memory, the chats, the apps the
user built, and the programs supervisord runs."""

import json
import re
import tomllib
from collections.abc import Callable
from pathlib import Path

from oom_priority.meminfo import KIB, PROC, parse_kib_fields
from oom_priority.registry import is_process_alive, live_pids_by_agent_id

MNGR_AGENTS_DIR = Path("/home/user/.mngr/agents")
APPS_REGISTRY = Path("data/.state/apps.toml")
# Command-line fragments of the language servers chats start to check code.
CODE_CHECKER_MARKERS = (
    "langserver",
    "language-server",
    "language_server",
    "gopls",
    "rust-analyzer",
    "clangd",
    "pylsp",
)
_AGENT_DIR = re.compile(r"/\.mngr/agents/(agent-[^/\s]+)")


class Process:
    def __init__(
        self,
        pid: int,
        ppid: int,
        rss: int,
        argv: list[str],
        private: int | None = None,
        pss: int | None = None,
    ) -> None:
        self.pid = pid
        self.ppid = ppid
        self.rss = rss  # bytes, shared pages counted in full
        self.argv = argv
        # From smaps_rollup, in bytes, None where the kernel has none or the process is not
        # ours to read: the memory only this process maps, and its proportional share (each
        # shared page divided evenly among the processes that map it).
        self.private = private
        self.pss = pss


def read_rollup(entry: Path) -> tuple[int, int] | None:
    """(private, pss) in bytes from a process's smaps_rollup, or None when it cannot be read."""
    try:
        values = parse_kib_fields((entry / "smaps_rollup").read_text())
    except OSError:
        return None  # no such file on this kernel, the process is gone, or not ours to read
    if "Pss" not in values:
        return None
    private = values.get("Private_Clean", 0) + values.get("Private_Dirty", 0)
    return private, values["Pss"]


def read_processes(proc: Path = PROC) -> dict[int, Process]:
    out: dict[int, Process] = {}
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            status = (entry / "status").read_text()
            argv = [a for a in (entry / "cmdline").read_bytes().split(b"\0") if a]
        except OSError:
            continue  # gone, or not ours to read
        ppid = rss = 0
        for line in status.splitlines():
            if line.startswith("PPid:"):
                ppid = int(line.split()[1])
            elif line.startswith("VmRSS:"):
                rss = int(line.split()[1]) * KIB
        rollup = read_rollup(entry) if rss else None
        out[int(entry.name)] = Process(
            int(entry.name),
            ppid,
            rss,
            [a.decode(errors="replace") for a in argv],
            private=rollup[0] if rollup else None,
            pss=rollup[1] if rollup else None,
        )
    return out


def has_breakdown(procs: dict[int, Process]) -> bool:
    """Whether the kernel reported private and proportional memory (smaps_rollup) for any process."""
    return any(p.pss is not None for p in procs.values())


def is_code_checker(command: str) -> bool:
    return any(marker in command for marker in CODE_CHECKER_MARKERS)


def chat_agent_id(command: str) -> str | None:
    """The agent id a command line names through its ``~/.mngr/agents/agent-...`` path, if any."""
    found = _AGENT_DIR.search(command)
    return found.group(1) if found else None


def chat_names(agents_dir: Path = MNGR_AGENTS_DIR) -> dict[str, str]:
    """Agent id -> the name the user knows the chat by."""
    names: dict[str, str] = {}
    if not agents_dir.is_dir():
        return names
    for data_file in agents_dir.glob("agent-*/data.json"):
        try:
            data = json.loads(data_file.read_text())
        except (OSError, ValueError):
            continue
        # A record of an unexpected shape is skipped, so one bad record cannot fail the page.
        if not isinstance(data, dict):
            continue
        labels = data.get("labels") if isinstance(data.get("labels"), dict) else {}
        name = labels.get("display_name") or data.get("name") or data_file.parent.name
        names[data_file.parent.name] = (
            str(name).removesuffix(" Agent").removesuffix("-Agent")
        )
    return names


def agents_by_pid(
    is_alive: Callable[[int], bool] = is_process_alive,
) -> dict[int, str]:
    """pid -> agent id, for every live agent's main process, whatever its harness.

    Each agent records its own main-process pid at launch in oom_priority's agent-pid registry
    (codex records both its TUI and its app-server). This is how a chat on claude, codex, or pi
    is recognised alike. A registered pid that a later, unrelated process has reused counts as
    that agent's until the next agent launch prunes the registry.
    """
    return {
        pid: agent_id
        for agent_id, pids in live_pids_by_agent_id(is_alive).items()
        for pid in pids
    }


def user_apps(registry: Path = APPS_REGISTRY) -> dict[str, str]:
    """supervisord program -> display name, for the apps the user built."""
    try:
        rows = tomllib.loads(registry.read_text()).get("apps", [])
    except (OSError, ValueError):
        return {}
    # A row of an unexpected shape is skipped, so one bad row cannot fail the page.
    return {
        str(r["program"]): str(r.get("display_name") or r.get("name") or r["program"])
        for r in (rows if isinstance(rows, list) else [])
        if isinstance(r, dict) and r.get("priority") == "user" and r.get("program")
    }
