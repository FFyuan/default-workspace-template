# data/.state/

Machine state the workspace services read and write:

- `apps.toml` - The registry of running apps and their ports.
- `oom_priority/` - The memory-pressure shed ledger and agent-pid registry.
- `browser-screenshots/` - Shared browser service state. (The browser's instance records are `data/.apps/browser/instances.json`; a `browser-fleet.json` here is an older copy of them, read only until the daemon first writes that file.)
- `workspace_main_branch_initialized` - First-boot marker for moving the workspace onto a clean `main` branch. (A workspace first booted by an older build has `initial_chat_created` instead, which counts the same.)
- `last-restic-prune` - Backup maintenance timestamp.
- `user_timezone` - The last timezone the bootstrap applied, re-applied at boot when the fetch from the user's computer fails.
- `isolated-instances/` - State for temporarily booted app instances.
- `codex-plugins/` - The installed code-guardian copy new Codex agents start from, and the config the last one was created with, which the hourly refresh installs with (`system/scripts/codex_update_plugin.sh`).
- `agent-tools/` - Logs of the hourly refresh of agents' plugins and the venv, per Claude config dir, and which config dirs have had a successful plugin install (`system/scripts/refresh_agent_tools.sh`).
