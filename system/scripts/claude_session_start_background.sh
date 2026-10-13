#!/usr/bin/env bash
# SessionStart hook: start the session's upkeep in the background, so none of it
# holds up the session's first message.
#
# Claude Code takes no prompt until every SessionStart hook has exited, so anything
# slow here is time a user waits on a new chat. The two jobs this starts are only
# needed eventually:
#
#   - `uv sync --all-packages` keeps the root venv in step with the lockfile.
#   - claude_update_plugin.sh installs the plugins .claude/settings.json enables
#     and checks the marketplaces on GitHub for newer versions. A plugin it
#     installs or updates is loaded only by the NEXT session, so waiting for it
#     gains the current one nothing. It runs at every session start, except while
#     the previous run for the same config dir and project path is still going,
#     so opening several chats at once starts one check, not several.
#
# Both run detached at a lower CPU priority, so they also yield to the chat's turn,
# and each is killed if it outlives BACKGROUND_JOB_TIMEOUT_SECONDS (where GNU
# `timeout` exists): a hung marketplace fetch would otherwise block every later
# plugin check for that config dir and project path.
# Their output goes to logs rather than this session's context; this hook prints
# the "warning:" lines each run wrote to stdout to one later session instead, so
# the session after a failed plugin install still learns why a skill is missing.
# Their stderr has a log of its own and is never printed: tools such as uv write
# routine "warning:" lines there.
set -euo pipefail

BACKGROUND_NICENESS=10
BACKGROUND_JOB_TIMEOUT_SECONDS="${CLAUDE_SESSION_START_JOB_TIMEOUT_SECONDS:-600}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
config_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
state_root="$repo_root/data/.state/claude-session-start"
# One state folder per config dir and project path: plugins install per config
# dir, at project scope.
state_key="$(printf '%s|%s' "$config_dir" "$PWD" | cksum | cut -d' ' -f1)"
state_dir="$state_root/$state_key"
mkdir -p "$state_dir" || exit 0

plugin_log="$state_dir/plugin_update.log"
plugin_stderr_log="$state_dir/plugin_update.stderr.log"
plugin_pid_file="$state_dir/plugin_update.pid"
uv_log="$state_dir/uv_sync.log"
uv_stderr_log="$state_dir/uv_sync.stderr.log"

# The prefix that caps a job's run time, word-split where the jobs use it; empty
# where there is no `timeout` (a bare macOS), which leaves the jobs uncapped.
time_limit=""
if command -v timeout >/dev/null 2>&1; then
    time_limit="timeout $BACKGROUND_JOB_TIMEOUT_SECONDS"
fi

run_detached() {
    local log="$1"
    local stderr_log="$2"
    shift 2
    # Every descriptor is redirected so claude, which reads this hook's output to
    # its end, is never left waiting on a background job's copy of it.
    if command -v setsid >/dev/null 2>&1; then
        setsid nohup nice -n "$BACKGROUND_NICENESS" "$@" >"$log" 2>"$stderr_log" </dev/null &
    else
        nohup nice -n "$BACKGROUND_NICENESS" "$@" >"$log" 2>"$stderr_log" </dev/null &
    fi
}

# Report what the previous background runs warned about, before the new runs
# replace their logs. A log is reported only while it is newer than its marker,
# so a plugin log kept while a check is still running is not reported twice.
for log in "$plugin_log" "$uv_log"; do
    if [[ -f "$log" && "$log" -nt "$log.reported" ]]; then
        grep '^warning:' "$log" || true
        touch "$log.reported" || true
    fi
done

if command -v uv >/dev/null 2>&1; then
    run_detached "$uv_log" "$uv_stderr_log" bash -c \
        '$1 uv sync --all-packages || echo "warning: uv sync --all-packages failed (exit $?); see $0"' \
        "$uv_stderr_log" "$time_limit"
fi

plugin_script="$script_dir/claude_update_plugin.sh"
running_plugin_pid=""
if [[ -f "$plugin_pid_file" ]]; then
    read -r running_plugin_pid < "$plugin_pid_file" || true
fi
if [[ -z "$running_plugin_pid" ]] || ! kill -0 "$running_plugin_pid" 2>/dev/null; then
    # A failed install logs its own warning; a run the time limit killed
    # (timeout's exit 124) never got that far, so it logs one here.
    run_detached "$plugin_log" "$plugin_stderr_log" bash -c '$1 bash "$0" || {
            status=$?
            if [[ $status -eq 124 ]]; then
                echo "warning: the plugin install/update was stopped after ${2}s; the next session tries again"
            fi
        }' "$plugin_script" "$time_limit" "$BACKGROUND_JOB_TIMEOUT_SECONDS"
    echo "$!" > "$plugin_pid_file"
fi

exit 0

plugin_log="$state_dir/plugin_update.log"
plugin_stderr_log="$state_dir/plugin_update.stderr.log"
plugin_pid_file="$state_dir/plugin_update.pid"
uv_log="$state_dir/uv_sync.log"
uv_stderr_log="$state_dir/uv_sync.stderr.log"

# The prefix that caps a job's run time, word-split where the jobs use it; empty
# where there is no `timeout` (a bare macOS), which leaves the jobs uncapped.
time_limit=""
if command -v timeout >/dev/null 2>&1; then
    time_limit="timeout $BACKGROUND_JOB_TIMEOUT_SECONDS"
fi

run_detached() {
    local log="$1"
    local stderr_log="$2"
    shift 2
    # Every descriptor is redirected so claude, which reads this hook's output to
    # its end, is never left waiting on a background job's copy of it.
    if command -v setsid >/dev/null 2>&1; then
        setsid nohup nice -n "$BACKGROUND_NICENESS" "$@" >"$log" 2>"$stderr_log" </dev/null &
    else
        nohup nice -n "$BACKGROUND_NICENESS" "$@" >"$log" 2>"$stderr_log" </dev/null &
    fi
}

# Report what the previous background runs warned about, before the new runs
# replace their logs. A log is reported only while it is newer than its marker,
# so a plugin log kept while a check is still running is not reported twice.
for log in "$plugin_log" "$uv_log"; do
    if [[ -f "$log" && "$log" -nt "$log.reported" ]]; then
        grep '^warning:' "$log" || true
        touch "$log.reported" || true
    fi
done

if command -v uv >/dev/null 2>&1; then
    run_detached "$uv_log" "$uv_stderr_log" bash -c \
        '$1 uv sync --all-packages || echo "warning: uv sync --all-packages failed (exit $?); see $0"' \
        "$uv_stderr_log" "$time_limit"
fi

plugin_script="$script_dir/claude_update_plugin.sh"
recent_plugin_stamp="$(find "$plugin_stamp" -mmin "-$PLUGIN_UPDATE_INTERVAL_MINUTES" 2>/dev/null || true)"
if [[ -z "$recent_plugin_stamp" || "$plugin_script" -nt "$plugin_stamp" ]]; then
    touch "$plugin_stamp"
    # A failed install already logs its own warning; a run the time limit killed
    # (timeout's exit 124) never got that far, so it logs one here.
    run_detached "$plugin_log" "$plugin_stderr_log" bash -c '$2 bash "$0" --strict || {
            status=$?
            rm -f "$1"
            if [[ $status -eq 124 ]]; then
                echo "warning: the plugin install/update was stopped after ${3}s; the next session tries again"
            fi
        }' "$plugin_script" "$plugin_stamp" "$time_limit" "$BACKGROUND_JOB_TIMEOUT_SECONDS"
fi

exit 0
