#!/usr/bin/env bash
#
# run_job.sh -- durable, completion-tracked runner for recurring jobs.
#
# Invoked every minute by a /etc/cron.d line (through with_agent_env.sh); runs
# the given command at most once per interval, and retries a run that failed
# or was killed mid-flight. Modeled on the host-backup service's tick loop:
# a run only counts once it COMPLETES.
#
# Usage: run_job.sh <job-id> --every <N[mhd]> [--at <hour>] [--retry-after <N[mhd]>] [--wake-grace <N[mhd]>] <command...>
#
#   --every 7d --at 3     weekly at 3 AM local, catch-up after downtime
#   --every 15m           every 15 minutes, no due-hour concept
#   --retry-after 2m      gap before retrying a failed run (default 2m)
#   --wake-grace 10m      after the workspace wakes, hold a due run this long
#
# State (timestamps and a counter, under data/.state/ so it survives
# container recreation and is captured by the restic host backup):
#   data/.state/jobs/<job-id>/last_attempt   epoch when a run last STARTED
#   data/.state/jobs/<job-id>/last_success   epoch when a run last COMPLETED (exit 0)
#   data/.state/jobs/<job-id>/failures       consecutive failed attempts
#   data/.state/jobs/<job-id>/last_tick      epoch of the last tick (--wake-grace only)
#   data/.state/jobs/<job-id>/woke_at        epoch the workspace last woke (--wake-grace only)
#
# Semantics:
#   - Due when now - last_success >= --every. Only last_success covers a
#     window, so a run that dies mid-flight (machine off, crash, nonzero
#     exit) leaves the window due and is retried -- no sooner than
#     --retry-after since last_attempt.
#   - --at <hour>: wait for that local hour on the day the job comes due;
#     if a whole extra day has passed (overdue by --every + 24h), run at any
#     hour -- the first minute the machine is back up.
#   - No state yet (first run ever): due now, but still waits for --at.
#   - The parent holds a flock for the whole run and runs the command as a
#     child with the lock fd closed, so overlapping ticks skip and the lock
#     can never leak into daemons the command starts (tmux, agents).
#   - At 3 consecutive failures a loud warning is logged; the retry cadence
#     is unchanged (the flock and --retry-after already bound the cost).
#   - --wake-grace: a tick that finds no tick in the last WAKE_GAP_SECONDS
#     (the first tick ever, after a boot, or after the machine slept) marks a
#     wake, and a due run waits until the grace has passed since it. A wake is
#     usually someone opening the workspace to use it, and a catch-up run is
#     not worth slowing their first minutes down for.
#
# Test hooks (used by system/libs/automations/run_job_test.py): MINDS_JOB_STATE_DIR overrides
# the state root; MINDS_JOB_NOW_EPOCH / MINDS_JOB_NOW_HOUR override the clock.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

usage() {
    echo "usage: run_job.sh <job-id> --every <N[mhd]> [--at <hour>] [--retry-after <N[mhd]>] [--wake-grace <N[mhd]>] <command...>" >&2
    exit 2
}

# Duration like 15m / 3h / 7d -> seconds. Anything else is a usage error.
to_seconds() {
    case "$1" in
        *m) echo $(( ${1%m} * 60 )) ;;
        *h) echo $(( ${1%h} * 3600 )) ;;
        *d) echo $(( ${1%d} * 86400 )) ;;
        *) echo "run_job: bad duration: $1 (use e.g. 15m, 3h, 7d)" >&2; exit 2 ;;
    esac
}

[ "$#" -ge 3 ] || usage
JOB_ID="$1"; shift
EVERY=""
AT_HOUR=""
RETRY_AFTER="2m"
WAKE_GRACE=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --every) EVERY="$2"; shift 2 ;;
        --at) AT_HOUR="$2"; shift 2 ;;
        --retry-after) RETRY_AFTER="$2"; shift 2 ;;
        --wake-grace) WAKE_GRACE="$2"; shift 2 ;;
        --*) echo "run_job: unknown option: $1" >&2; usage ;;
        *) break ;;
    esac
done
[ -n "$EVERY" ] && [ "$#" -ge 1 ] || usage
EVERY_SECONDS=$(to_seconds "$EVERY")
RETRY_SECONDS=$(to_seconds "$RETRY_AFTER")
WAKE_GRACE_SECONDS=0
if [ -n "$WAKE_GRACE" ]; then
    WAKE_GRACE_SECONDS=$(to_seconds "$WAKE_GRACE")
fi
# cron ticks every minute, so a longer silence means the machine was off or asleep.
WAKE_GAP_SECONDS=300

STATE_DIR="${MINDS_JOB_STATE_DIR:-$ROOT/data/.state/jobs}/$JOB_ID"

log() { printf '%s run_job[%s]: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$JOB_ID" "$*"; }

# CLEANUP: for a while the runner kept its state under system/data/.state/jobs/,
# which git neither tracks nor ignores. This moves a job's state from there into
# place (or drops it once the new dir exists). Remove once every workspace has
# ticked each of its jobs on a build that has this.
LEGACY_STATE_DIR="$ROOT/system/data/.state/jobs/$JOB_ID"
if [ -z "${MINDS_JOB_STATE_DIR:-}" ] && [ -d "$LEGACY_STATE_DIR" ]; then
    if [ -e "$STATE_DIR" ]; then
        rm -rf "$LEGACY_STATE_DIR" || log "could not remove the old state at $LEGACY_STATE_DIR"
    else
        { mkdir -p "$(dirname "$STATE_DIR")" && mv "$LEGACY_STATE_DIR" "$STATE_DIR"; } \
            || log "could not move the old state at $LEGACY_STATE_DIR"
    fi
    rmdir "$ROOT/system/data/.state/jobs" "$ROOT/system/data/.state" "$ROOT/system/data" 2>/dev/null || true
fi
mkdir -p "$STATE_DIR"

NOW="${MINDS_JOB_NOW_EPOCH:-$(date +%s)}"
HOUR="${MINDS_JOB_NOW_HOUR:-$((10#$(date +%H)))}"

# Recorded before the lock, so a tick that finds a run in progress still counts
# as the machine being awake.
if [ "$WAKE_GRACE_SECONDS" -gt 0 ]; then
    LAST_TICK="$(cat "$STATE_DIR/last_tick" 2>/dev/null || echo "")"
    if [ -z "$LAST_TICK" ] || [ $(( NOW - LAST_TICK )) -gt "$WAKE_GAP_SECONDS" ]; then
        printf '%s\n' "$NOW" > "$STATE_DIR/woke_at"
    fi
    printf '%s\n' "$NOW" > "$STATE_DIR/last_tick"
fi

# One run at a time per job. Held by THIS parent for the whole run; the
# command below runs with fd 9 closed so nothing it daemonizes can inherit
# the lock and wedge the job forever. flock(1) exists in the Linux container
# (the only place cron drives this); macOS dev machines lack it, so degrade
# to no overlap protection there rather than failing.
exec 9>"$STATE_DIR/lock"
if command -v flock >/dev/null 2>&1; then
    flock -n 9 || exit 0
fi

LAST_SUCCESS="$(cat "$STATE_DIR/last_success" 2>/dev/null || echo "")"
LAST_ATTEMPT="$(cat "$STATE_DIR/last_attempt" 2>/dev/null || echo "")"

# Covered: the interval has not elapsed since the last COMPLETED run.
if [ -n "$LAST_SUCCESS" ] && [ $(( NOW - LAST_SUCCESS )) -lt "$EVERY_SECONDS" ]; then
    exit 0
fi

# Due-hour gate: wait for --at, unless a whole extra day has been missed --
# then run at any hour, the first minute the machine is back.
if [ -n "$AT_HOUR" ] && [ "$HOUR" -lt "$AT_HOUR" ]; then
    if [ -z "$LAST_SUCCESS" ] || [ $(( NOW - LAST_SUCCESS )) -lt $(( EVERY_SECONDS + 86400 )) ]; then
        exit 0
    fi
fi

# Retry gate: a started-but-never-completed run (failure or kill) is retried,
# but no sooner than --retry-after since it last started.
if [ -n "$LAST_ATTEMPT" ] && [ $(( NOW - LAST_ATTEMPT )) -lt "$RETRY_SECONDS" ]; then
    exit 0
fi

# Wake gate: let the workspace settle before a catch-up run.
if [ "$WAKE_GRACE_SECONDS" -gt 0 ]; then
    WOKE_AT="$(cat "$STATE_DIR/woke_at" 2>/dev/null || echo "")"
    if [ -n "$WOKE_AT" ] && [ $(( NOW - WOKE_AT )) -lt "$WAKE_GRACE_SECONDS" ]; then
        exit 0
    fi
fi

printf '%s\n' "$NOW" > "$STATE_DIR/last_attempt"
set +e
"$@" 9>&-
rc=$?
set -e

if [ "$rc" -eq 0 ]; then
    printf '%s\n' "${MINDS_JOB_NOW_EPOCH:-$(date +%s)}" > "$STATE_DIR/last_success"
    rm -f "$STATE_DIR/failures"
    exit 0
fi

FAILURES=$(( $(cat "$STATE_DIR/failures" 2>/dev/null || echo 0) + 1 ))
printf '%s\n' "$FAILURES" > "$STATE_DIR/failures"
log "run failed (rc=$rc); attempt $FAILURES, retrying in $RETRY_AFTER"
if [ "$FAILURES" -ge 3 ]; then
    log "warning: job has failed $FAILURES consecutive attempts and is not completing; investigate this log"
fi
exit "$rc"
