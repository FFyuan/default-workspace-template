A new chat no longer waits for the plugin install/update or `uv sync --all-packages` before it can take its first message, and the work is no longer repeated at every chat start. Claude takes no prompt until all of its startup hooks have finished, and those two were the slow ones.

- An hourly job, `system/scripts/refresh_agent_tools.sh`, now does them: it runs `uv sync --all-packages`, installs and updates the Claude plugins in every Claude config dir in use (`~/.claude` and each Claude account's folder, listed by `claude_config_dirs.py`), and refreshes the shared code-guardian copy new Codex agents start from. A run missed while the workspace was off or asleep is caught up ten minutes after it wakes, and a failed run is retried after fifteen minutes. Each part runs at a lower CPU priority and is stopped after ten minutes.

- Signing in to a new Claude account installs its plugins at once, so the account's first chat has them. Before, a plugin installed during a session only loaded in the next one, so the first chat on an account never had them.

- The SessionStart hook is now `refresh_agent_tools.sh --session-start`. It returns at once, shows the warnings the last run logged to one session, and starts an install in the background only for a config dir that has never had one.

- A new Codex chat no longer clones code-guardian from GitHub before it starts (about 1.5 s on a cloud workspace, and once 93 s when the fetch hung). It copies the workspace's shared install from `data/.state/codex-plugins/` in tens of milliseconds, and so does a Codex worker in its own worktree. Only the first Codex agent on a workspace still installs from GitHub, and its install becomes the shared copy.

- Workers install their Claude plugins through `refresh_agent_tools.sh --claude-plugins`, which still never fails a worker's launch.
