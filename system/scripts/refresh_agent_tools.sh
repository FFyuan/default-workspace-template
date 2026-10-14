#!/usr/bin/env bash
# refresh_agent_tools.sh
# refresh_agent_tools.sh --claude-plugins [<config-dir>]
# refresh_agent_tools.sh --session-start
#
# Keeps the tools agents start with up to date, without a new chat waiting on it.
# Claude Code takes no prompt until every SessionStart hook has exited, and a
# plugin it installs mid-session only loads in the next session anyway, so none
# of this belongs on a chat's startup path.
#
# With no arguments (the hourly run: bootstrap writes a cron entry that runs it
# through run_job.sh, which holds a catch-up run for a while after the workspace
# wakes), it:
#
#   - runs `uv sync --all-packages`, keeping the root venv in step with the lockfile;
#   - installs and updates the Claude Code plugins .claude/settings.json enables,
#     for this project path, in every Claude config dir in use: claude's default
#     ~/.claude and each Claude account's folder (claude_config_dirs.py). Plugins
#     install per config dir, so an account added since the last run gets its own;
#   - refreshes the shared code-guardian install new Codex agents copy
#     (codex_update_plugin.sh --refresh-shared).
#
# It exits non-zero when any of these failed, so run_job.sh retries it.
#
# --claude-plugins does only the Claude plugins, for one config dir (default
# $CLAUDE_CONFIG_DIR, else ~/.claude), and always exits 0: the warnings it prints
# say what went wrong. The chat app runs it when a Claude account is signed in,
# so plugins are ready before the account's first chat, and a worker runs it as a
# provision command, since a worker's one session starts in a fresh worktree path.
#
# --session-start is the SessionStart hook. It prints, once, the warnings the last
# runs logged, so a session learns why a skill is missing; and when the session's
# config dir has never had a successful install, it starts one in the background.
# It returns in milliseconds.
#
# State lives under data/.state/agent-tools/. Each job is capped at
# AGENT_TOOLS_JOB_TIMEOUT_SECONDS where GNU `timeout` exists, and runs at a lower
# CPU priority (which gVisor ignores, hence keeping it off the startup path).
set -euo pipefail

BACKGROUND_NICENESS=10
JOB_TIMEOUT_SECONDS="${AGENT_TOOLS_JOB_TIMEOUT_SECONDS:-600}"

script_path="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
script_dir="$(dirname "$script_path")"
repo_root="$(cd "$script_dir/../.." && pwd)"
state_root="$repo_root/data/.state/agent-tools"
uv_log="$state_root/uv_sync.log"
uv_stderr_log="$state_root/uv_sync.stderr.log"
codex_log="$state_root/codex_refresh.log"

# The prefix that caps a job's run time, word-split where it is used; empty where
# there is no `timeout` (a bare macOS), which leaves the jobs uncapped.
time_limit=""
if command -v timeout >/dev/null 2>&1; then
    time_limit="timeout $JOB_TIMEOUT_SECONDS"
fi

run_capped() {
    # shellcheck disable=SC2086
    nice -n "$BACKGROUND_NICENESS" $time_limit "$@"
}

# One state folder per config dir and project path: plugins install per config
# dir, at project scope.
claude_state_dir() {
    printf '%s/claude/%s' "$state_root" "$(printf '%s|%s' "$1" "$repo_root" | cksum | cut -d' ' -f1)"
}

# Install and update the plugins in one config dir, print what the run printed,
# and return its exit status. A run already going for the same dir is left to
# finish, and this one returns 0. flock(1) is missing on macOS, which then gets
# no overlap protection.
refresh_claude_plugins() {
    local config_dir="$1"
    local state_dir
    state_dir="$(claude_state_dir "$config_dir")"
    mkdir -p "$state_dir"
    (
        if command -v flock >/dev/null 2>&1; then
            flock -n 8 || exit 0
        fi
        status=0
        (cd "$repo_root" && run_capped env CLAUDE_CONFIG_DIR="$config_dir" bash "$script_dir/claude_update_plugin.sh" --strict) \
            >"$state_dir/plugin_update.log" 2>"$state_dir/plugin_update.stderr.log" || status=$?
        if [[ $status -eq 0 ]]; then
            touch "$state_dir/installed"
        elif [[ $status -eq 124 ]]; then
            echo "warning: the plugin install/update for $config_dir was stopped after ${JOB_TIMEOUT_SECONDS}s" \
                >>"$state_dir/plugin_update.log"
        fi
        cat "$state_dir/plugin_update.log"
        exit "$status"
    ) 8>"$state_dir/lock"
}

refresh_all() {
    local failed=0
    local status=0
    local config_dirs
    mkdir -p "$state_root"

    (cd "$repo_root" && run_capped uv sync --all-packages) >"$uv_log" 2>"$uv_stderr_log" || status=$?
    if [[ $status -ne 0 ]]; then
        echo "warning: uv sync --all-packages failed (exit $status); see $uv_stderr_log" >>"$uv_log"
        failed=1
    fi
    cat "$uv_log"

    if ! config_dirs="$(cd "$repo_root" && uv run --no-sync python system/scripts/claude_config_dirs.py)"; then
        echo "warning: could not list the Claude accounts; refreshing plugins in $HOME/.claude only"
        config_dirs="$HOME/.claude"
        failed=1
    fi
    while IFS= read -r config_dir; do
        [[ -n "$config_dir" ]] || continue
        refresh_claude_plugins "$config_dir" || failed=1
    done <<<"$config_dirs"

    status=0
    run_capped bash "$script_dir/codex_update_plugin.sh" --refresh-shared >"$codex_log" 2>&1 || status=$?
    cat "$codex_log"
    if [[ $status -ne 0 ]]; then
        failed=1
    fi

    return "$failed"
}

session_start() {
    local config_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
    local state_dir
    state_dir="$(claude_state_dir "$config_dir")"
    # A log is reported only while it is newer than its marker, so each run's
    # warnings reach one session.
    for log in "$state_dir/plugin_update.log" "$uv_log"; do
        if [[ -f "$log" && "$log" -nt "$log.reported" ]]; then
            grep '^warning:' "$log" || true
            touch "$log.reported" || true
        fi
    done
    if [[ -f "$state_dir/installed" ]]; then
        return 0
    fi
    # Every descriptor is redirected so claude, which reads this hook's output to
    # its end, is never left waiting on the background run's copy of it. The run
    # is the workspace's, not this agent's, so it drops the agent's id: mngr kills
    # the processes carrying it when it restarts the agent.
    if command -v setsid >/dev/null 2>&1; then
        env -u MNGR_AGENT_ID setsid nohup bash "$script_path" --claude-plugins "$config_dir" \
            >/dev/null 2>&1 </dev/null &
    else
        env -u MNGR_AGENT_ID nohup bash "$script_path" --claude-plugins "$config_dir" \
            >/dev/null 2>&1 </dev/null &
    fi
}

case "${1:-}" in
    "")
        [[ $# -eq 0 ]] || { echo "usage: $0 [--claude-plugins [<config-dir>] | --session-start]" >&2; exit 2; }
        refresh_all
        ;;
    --claude-plugins)
        [[ $# -le 2 ]] || { echo "usage: $0 --claude-plugins [<config-dir>]" >&2; exit 2; }
        refresh_claude_plugins "${2:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}}" || true
        ;;
    --session-start)
        session_start
        ;;
    *)
        echo "usage: $0 [--claude-plugins [<config-dir>] | --session-start]" >&2
        exit 2
        ;;
esac
