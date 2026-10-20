# Routines

Status: agreed design (2026-10-20), not yet implemented.
Audience: implementers of the routines library (`system/libs/routines`), the Routines app (`system/apps/routines`), the bootstrap, the Caretaker, the `build-app` and `update-app` skills, and the one change in the Imbue Studio desktop app.

A routine is something in a workspace that runs on a schedule.
This spec replaces the hand-written cron entries, the `run_job.sh` runner, the `run_automation.sh` wake script, and the three Caretaker skills with one library, one command, and one app, so that the user can see everything that runs on its own, turn it on and off, run it by hand, and find out when it breaks.

- **Part A: the library.** Typed routine definitions, one scheduler, one runner for command runs and skill runs, one state store, and one run ledger.
- **Part B: the command.** `routines`, the only way an agent creates, changes, or runs a routine.
- **Part C: the app.** Routines, a built-in app listing every routine with its health, next run, and history, with run-now, on/off, reschedule, and fix controls.
- **Part D: the Caretaker.** An ordinary routine, off by default, whose check reads the ledger.
- **Part E: notifications.** The runner tells the user through the Imbue Studio feed when a routine keeps failing, needs them, or recovers.

## 1. Background

Facts this design builds on, as of `main` at `2cf9763de` (2026-10-20).

- Recurring work runs through the stock cron daemon (`system/supervisord.conf.d/cron.conf`).
  Each job is a drop-in under `/etc/cron.d/`, reinstalled at every boot from its durable copy under `data/.state/cron.d/` by the bootstrap (`_install_runtime_cron_entries` in `system/libs/bootstrap/src/bootstrap/manager.py`).
  The bootstrap also writes the one code-owned entry, the update-apply recovery guard, straight into `/etc/cron.d/` at every boot.
- A job that must not be missed is an every-minute cron line that hands the decision to `system/libs/automations/run_job.sh`, which keeps `last_attempt`, `last_success`, and `failures` under `data/.state/jobs/<id>/`, runs the command once per `--every` interval (optionally at an `--at` hour), catches up after downtime, and retries a failed run after `--retry-after`.
  Every cron line is prefixed with `system/libs/automations/with_agent_env.sh`, which rebuilds the agent environment cron scrubs.
- An automation is a skill run on a schedule: `run_automation.sh <skill>` creates a singleton agent labelled `automation=<skill>` from the `automation` create template, and on later runs sends `/clear`, sleeps two seconds, and sends `/<skill>` through `system/scripts/message_chat.py`.
  The agent's outcome is not observed.
- The Caretaker is that pattern with a deterministic gate: `system/services/caretaker/caretaker_check.sh` looks for failing services, fresh error output, a full disk, and memory-guard sheds, and wakes the `caretaker` agent (its own create template, its own skill) only with findings or on its first run.
  It is off by default; the `enable-caretaker` and `disable-caretaker` skills write and remove its cron entry.
- The `manage-scheduled-tasks` skill is the only instruction agents have for scheduling, and it asks them to hand-write cron lines, choose between the runner and a plain cron line, and keep two copies of each entry.
- The chat app owns the chats and knows what each is doing: `GET /api/agents` answers every agent with its `chat_id` and `is_busy`, the `ChatSnapshot` status (`working`, `background`, `idle`, `attention`, `stopped`, `error`) is what the chat list draws, and `POST /api/chats/<chat-id>/stop`, `start`, `interrupt`, and `message` act on a chat.
  `system/scripts/message_chat.py` sends to a chat by id and revives a stopped agent on send; `system/scripts/message_chat.py --create` makes a chat the way the launcher does.
- A chat agent notifies the user through `POST /api/v1/agents/<agent-id>/notifications` on the Imbue Studio app, via the latchkey gateway, with `message`, an optional `title`, and `watched_by` (`.agents/skills/notify-user/scripts/notify_user.py`).
  The feed resolves the entry's destination from the agent's chat: a click lands in that chat.
  There is no way to send the user to an app page.
- A built-in app is a Flask program with an `app.toml` manifest, installed as its own uv tool, registered through `forward_port.py`, serving an OpenAPI document through `system/libs/app_schema`; the ones with a real interface (the shell, the chat, Getting Started, Files) are Mithril and Tailwind builds in the npm workspace at `system/package.json` over `system/libs/workspace_ui`.
  Memory & disk (`system/apps/system_monitor`) is the one-page reference for an app that reads machine state and stores nothing.
- A published template that users adopted, `nicholasgjokaj-star/routines`, showed the value of one window over everything scheduled, with plain-language rows, automatic-versus-manual runs, next-run times, problems sorted first, a run-in-flight indicator, and a Fix button that hands an agent the evidence.
  It recovered all of it by parsing cron command lines, kept history only for jobs an agent remembered to wrap, modelled only cron commands, could not notify, and matched none of the workspace's conventions.
  This spec keeps its ideas and none of its mechanisms.

## 2. Decisions

1. **One concept.** A routine is something that runs on a schedule and then exits.
   Services that run continuously are not routines; they stay under supervisord and Memory & disk.
   An app that needs periodic work makes it a routine instead of a loop inside its service.
2. **The definition is the source of truth.** Each routine is one TOML file, tracked in git like an app or a skill.
   Cron holds one line for the whole workspace and no routine is ever written to it.
3. **One runner, one state store, one ledger.** Scheduled runs and manual runs take the same code path; the trigger is a field.
   The runner records every run, so history needs no cooperation from the routine.
4. **Two ways to say what runs, one path.** A routine runs a command or a skill.
   A skill routine is sugar for a command that wakes the routine's chat, waits for the turn to end, and records the chat.
5. **The chat app is the oracle for a skill run.** Whether the agent is done, blocked, or still going is read from the chat app, which already knows; the runner never guesses from transcripts or sleeps.
6. **Failure has two layers.** The runner notifies the user through the feed with no judgement of its own beyond counting; the Caretaker is the agent that investigates, on a schedule, when it is on.
7. **The Caretaker is a routine.** It has no create template, no cron entry, and no enabling skill of its own.
8. **The on/off switch is state, not a file edit.** The definition carries the default; the user's choice lives under `data/.state`, like stopping a supervised program.
9. **Nothing moves into mngr.** The library imports nothing from mngr and runs `mngr` only to create a chat's agent, as the automation script does today.
10. **No cron expressions.** An interval, a time of day, a set of weekdays, a day of the month, or a single moment covers every schedule the template documents today.

## 3. Vocabulary

- **Routine**: a definition file plus its state.
  Its **id** is the file's stem.
- **Definition**: `system/routines/<id>.toml`, the tracked record of what the routine is and when it runs.
- **Schedule**: the part of the definition that says when.
- **Run**: one execution of the routine, with a **run id**, a **trigger** (`scheduled` or `manual`), an **outcome**, a log, and optionally a chat.
- **Command run**: a run that executes a process.
  **Skill run**: a run that wakes the routine's chat with a slash command and waits for the turn.
- **State**: `data/.state/routines/<id>/state.json`, what the runner knows about the routine on this machine.
- **Ledger**: the run events under `data/.state/routines/events/runs/events.jsonl`.
- **Health**: the one word the app and the CLI say about a routine, derived from its state and schedule (section 7.4).
- **Tick**: the once-a-minute pass that starts every run that is due.

## 4. The definition file

One routine per file, `system/routines/<id>.toml`.
The root `routines` symlink points at that directory beside `apps` and `skills`.
The id matches `[a-z0-9][a-z0-9-]{0,62}` so it can name a chat, a log file, and a path segment unchanged.

```toml
title = "Morning inbox digest"
what = "Reads new mail and writes a short summary note."
every = "1d"
at = "07:30"
skill = "inbox-digest"
```

Every field:

| Field | Required | Meaning |
|---|---|---|
| `title` | yes | What the user sees it called. |
| `what` | yes | One sentence saying what it does for the user. |
| `every` | one of `every`, `once` | The cadence: a whole number and a unit, `m`, `h`, `d`, `w`, or `mo`. |
| `at` | no | The local time of day a run is due, `HH:MM`; only with a cadence of a day or longer. |
| `days` | no | The weekdays a run may start, `mon` to `sun`; with any cadence. |
| `day_of_month` | no | The day of the month a run is due, 1 to 31; only with a cadence in months. |
| `once` | one of `every`, `once` | A single local moment, `YYYY-MM-DDTHH:MM`; the routine is done after one successful run. |
| `command` | one of `command`, `skill` | The argv to run from the repo root. |
| `skill` | one of `command`, `skill` | The skill to run in the routine's chat. |
| `enabled` | no | The default switch, `true` unless set. |
| `timeout` | no | How long a run may take, a duration as above; `1h` unless set. |
| `retry_after` | no | How long after a failed run the next attempt may start; `2m` unless set. |
| `notify_after_failures` | no | Consecutive failures before the feed is told; `3` unless set, `0` never. |
| `app` | no | The name of the app this routine belongs to, for grouping and for the Fix brief. |

`at`, `days`, and `day_of_month` go with `every` only; a `once` moment carries its own time.
The library validates a definition with a pydantic model on every read; a file that fails validation is listed as broken with its reason and never run.
Writes go through `tomlkit` so a comment an agent left survives an edit.
A definition is written only by the library, which the CLI (section 9) and the app (section 10) both call, and the library commits each write it makes, staging that one file, with a message naming the routine and the change ("routines: change the schedule of inbox-digest").
The app's schedule editor has no agent to commit for it, and an agent that calls the CLI gets the commit for free; git is invisible plumbing to the user either way.
A commit that fails (no git, a lock held) leaves the file written and logs a warning.

## 5. Schedules and due computation

Time inside the library is UTC-aware everywhere.
A definition's `at`, `once`, and `days` are in the container's local time zone, which the bootstrap sets to the user's; the library converts at the boundary.
All arithmetic is in `schedule.py` as pure functions of the definition, the state, and `now`.

### 5.1 The next due moment

`next_due(definition, state, now)` answers the earliest moment at or after which a scheduled run may start, or `None` for a routine that is done.
Rules 1 and 2 answer outright; rules 3 to 6 compose, in order.

1. A routine with `once` is due at that moment while it has never succeeded, and done once it has.
2. A routine that has never succeeded is due now.
3. Otherwise the base is the last success plus the cadence.
   A cadence in months steps the calendar month and clamps the day to the month's last day when it must; `day_of_month` then pins the day.
4. With `at`, the due moment is the base's date at that time, the window being a calendar day: a run that succeeded at 07:04 is due again tomorrow at 07:30, not at 07:04 plus a day.
   Without `at`, the due moment is the base itself.
5. With `days`, a due moment on a weekday not listed moves to the next listed weekday, keeping the time of day.
6. A failed or interrupted attempt (last attempt after last success) floors the due moment at the last attempt plus `retry_after`.

Catch-up follows from step 3: a workspace off for three days finds the routine due the moment it is back and runs it once, after which the next due moment is counted from that success.
Missed windows are never replayed.

### 5.2 Health thresholds

A routine is **overdue** when now is past its due moment by more than the margin and no run is in flight.
The margin is the smaller of half the cadence and one day, and never under five minutes; a `once` routine's margin is five minutes.
The tick runs a due routine within a minute, so overdue means the tick is not running or the runner keeps failing to start it, which is worth a different word from failing.

### 5.3 Describing a schedule

`describe_schedule(definition)` renders the schedule in the words the rows show: "Every 15 minutes", "Every day at 7:30 am", "Every Monday and Friday at 9:00 am", "Monthly on the 1st at midnight", "Once, Nov 3 at 3:00 pm".
`describe_next(due, now)` renders the due moment relative to today.
Both are pinned by inline-snapshot tests.

## 6. The runner

The library is `system/libs/routines`, a uv workspace member in the root venv, with the console script `routines`.
`with_agent_env.sh` moves into it from `system/libs/automations`, unchanged.

### 6.1 The tick

The bootstrap writes one code-owned entry into `/etc/cron.d/routines` at every boot, beside the recovery guard (the `data/.state/cron.d` install keeps running for whatever the migration of section 12 leaves there):

```
* * * * *   root   /home/user/workspace/system/libs/routines/with_agent_env.sh uv run --no-sync routines tick >> /var/log/supervisor/routines-tick.log 2>&1
```

`routines tick`:

1. Takes the tick lock (`data/.state/routines/tick.lock`, `flock -n`) and exits silently if held.
2. Reaps: for every state whose `current_run` names a pid that is gone, or that is no longer a `routines run <id>` process (read from `/proc/<pid>/cmdline`, so a reused pid never passes), writes a `run_finished` event with outcome `interrupted` and clears it (section 7.2).
3. Reads every definition.
   For each that is enabled, not running, and due, spawns `routines run <id> --trigger scheduled` detached (its own session, the run's log as stdout and stderr) and moves on.
4. Once a day, by the stamp in `data/.state/routines/housekeeping.json`, rotates the ledger and prunes old run directories (section 7.2).
5. Exits.
   A tick never waits on a run.

The tick's own output is a line per spawned run and a line per reaped run, nothing while idle.

### 6.2 A run

`routines run <id> --trigger scheduled|manual`:

1. Takes the routine's lock (`data/.state/routines/<id>/lock`, `flock -n`).
   Held means a run is in flight: a scheduled run exits silently, a manual run exits 1 saying so.
   The switch gates scheduled runs only; a manual run of a routine that is off runs, since the user asked for exactly that.
2. Mints a run id, creates the run directory `data/.state/routines/<id>/runs/<run_id>/`, writes `run_started` to the ledger, and records the run as `current_run` in the state with this process's pid.
3. Runs the routine (6.3 or 6.4), streaming output to `<run_dir>/log` as it arrives.
4. Reads `<run_dir>/result.json` if the routine wrote one (6.5).
5. Writes `run_finished` with the outcome, updates the state, and applies the notification rules (section 8).
6. Exits with 0 for a success and 1 otherwise, so a caller with `--wait` can read it.

The run directory is passed to the routine as `ROUTINES_RUN_DIR`, with `ROUTINES_ROUTINE_ID` and `ROUTINES_RUN_ID` beside it.

### 6.3 A command run

The argv runs from the repo root with the agent environment, in its own process group, stdout and stderr to the log.
A run past `timeout` has its process group killed and the outcome `timed_out`.
Exit 0 is `succeeded`; anything else is `failed`.

### 6.4 A skill run

`skill = "<name>"` is sugar for `command = ["uv", "run", "--no-sync", "routines", "wake", "<name>"]`, and `routines wake` is what the Caretaker's check calls too.
Inside a run (`ROUTINES_RUN_ID` set) the wake attaches the chat to that run; outside one it is a plain wake with its own exit code.

1. **Find the chat.** The routine's chat id is in its state.
   With none, or one the chat app no longer knows, create the agent as the automation script does today: `uv run mngr create <id> --template automation --no-connect --format json --label routine=<id> --label workspace=<workspace> --message /<skill>`, record the chat id, and go to step 4, where any agent message counts as the answer, since the chat starts empty.
   The create needs a signed-in provider account; a refusal is a `failed` run whose summary is the refusal's text.
2. **Make sure it is free.** Read the chat's snapshot from `GET /api/chats`.
   A chat that is `working`, `background`, or `attention` is the previous run still going (or, rarely, the user talking to it, which this cuts short): stop it (`POST /api/chats/<id>/stop`), start it (`POST .../start`), wait until its status is `idle`, and note `restarted_previous_run` on this run.
   That note is a warning in the row and the run page, since it means the routine's timeout or cadence is wrong.
3. **Start fresh.** Send `/clear` through `message_chat.py`, then `/<skill>` with a message id the wake minted.
   The send route answers only once the harness has accepted the text, so a returned send is the acknowledgement; nothing sleeps.
4. **Wait for the turn.** Poll the chat's snapshot every second.
   The turn is over when the status is `idle` and the transcript (`GET /api/chats/<id>/events`) holds an agent message after the sent one; that is `succeeded`.
   `stopped` or `error` is `failed`.
   `attention` writes a `run_blocked` event once (the user must answer the agent) and keeps waiting, so a run the user unblocks can still end well.
   A chat that is still `idle` with no answer a minute after the send never started; that is `failed` with the summary saying so.
   Past `timeout`, interrupt the chat (`POST .../interrupt`) and end the run `timed_out`.
5. **Summarize.** The run's summary is the first line of that last agent message, cut at 200 characters.

The chat shows in the chat list like any chat, named after the routine, and the run page links to it.

### 6.5 The result file

A command may write `$ROUTINES_RUN_DIR/result.json` before it exits: `{"summary": "<one line>", "links": [{"label": "...", "url": "..."}]}`.
The summary is the line the row and the history show for the run ("Nothing new", "3 messages summarized"); without it the row shows the outcome alone.
Links are shown on the run page.
A skill run has no result file; its summary is the agent's last message (6.4), which is what the agent would have written anyway.

## 7. State and run records

### 7.1 State

`data/.state/routines/<id>/state.json`, one pydantic model, rewritten whole by the runner under the routine's lock:

```json
{
  "is_enabled": true,
  "chat_id": "agent-...",
  "last_started_at": "2026-10-20T14:30:00.000000+00:00",
  "last_succeeded_at": "2026-10-20T14:30:12.000000+00:00",
  "consecutive_failures": 0,
  "is_failure_notified": false,
  "current_run": null,
  "last_run": {"run_id": "...", "trigger": "scheduled", "outcome": "succeeded", "summary": "3 messages summarized", "started_at": "...", "finished_at": "..."}
}
```

`is_enabled` is absent until the user flips the switch; the definition's `enabled` applies while it is.
`current_run` carries the run id, the pid, the trigger, and when it started.
Every write to the file, the switch included, goes through the library under the routine's lock, so the app and a run never race on it.
Deleting a routine's state directory resets it; deleting `last_succeeded_at` makes it due.

### 7.2 The ledger

`data/.state/routines/events/runs/events.jsonl`, append-only, one event per line under the `imbue_common` `EventEnvelope` (`timestamp`, `type`, `event_id`, `source` = `runs`), every event carrying `routine_id` and `run_id`:

- `run_started`: `trigger`, `kind` (`command` or `skill`), `command`.
- `run_blocked`: a skill run's agent is waiting on the user.
- `run_finished`: `outcome` (`succeeded`, `failed`, `timed_out`, `interrupted`), `exit_code`, `duration_seconds`, `summary`, `chat_id`, `warnings`, `output_tail` (the log's last 4 KB).

Readers take the file from its tail and stop once they have what they need; the app never reads the whole file for one routine.
The tick's daily housekeeping (6.1) rotates the file past 16 MB to `events.<date>.jsonl.gz` and prunes run directories older than 90 days.
Every event is self-describing, so the per-routine run directory is a convenience and the ledger is the record.

### 7.3 The log

`<run_dir>/log` holds everything the routine printed, unprocessed.
It is the raw record behind every derived field, and the run page and `routines log` show it as is.

### 7.4 Health

One enum, matched exhaustively everywhere it is read; the first row that holds wins:

| Health | When |
|---|---|
| `broken` | The definition does not validate. |
| `off` | The switch is off. |
| `done` | A `once` routine that has succeeded. |
| `needs_user` | The run in flight is blocked on the user. |
| `failing` | `consecutive_failures` is above zero. |
| `overdue` | Section 5.2. |
| `not_run_yet` | No run has finished. |
| `working` | None of the above. |

Whether a run is in flight is a separate flag beside the health, because a failing routine can be mid-retry and the row has to say both.

## 8. Failure handling and notifications

The runner, at the end of every run, applies three rules against the state:

1. **Failing.** When `consecutive_failures` reaches `notify_after_failures` and `is_failure_notified` is false, post a notification ("Morning inbox digest has failed 3 times in a row.") and set the flag.
   A streak notifies once.
2. **Recovered.** When a run succeeds and `is_failure_notified` is true, post ("Morning inbox digest is working again.") and clear the flag.
3. **Blocked.** On `run_blocked`, post ("Morning inbox digest needs you.") once per run.

A notification is `POST /api/v1/agents/<MNGR_AGENT_ID>/notifications` through the latchkey gateway, exactly as `notify_user.py` does, from the services agent's environment the env wrapper restores, with a `destination` naming the routine's page (section 14).
The services agent is not a chat, so the desktop must not treat the entry as a chat's message; section 14 covers that.
A gateway that is not there, or an app that refuses, is a warning in the run's log and nothing else; a notification never fails a run.

The Caretaker's check (section 11) is the other layer: it reads the ledger for runs that failed or routines that went overdue since its last check and wakes its agent with them.

## 9. The command

`routines`, a `click` group, the agent-facing surface and what the app calls.
Every subcommand answers `--format json` for scripts.

| Command | Does |
|---|---|
| `routines list` | Every routine with health, schedule, next run, last run. |
| `routines show <id>` | One routine with its recent runs. |
| `routines add <id> --title --what (--every \| --once) [--at] [--days] [--day-of-month] (--command -- ... \| --skill) [--app] [--timeout] [--retry-after] [--notify-after-failures] [--disabled]` | Writes the definition after validating it; refuses an id that exists. |
| `routines edit <id> [same flags]` | Rewrites the named fields, keeping the rest and the comments. |
| `routines enable <id>`, `routines disable <id>` | Flips the switch in the state. |
| `routines run <id> [--wait]` | A manual run; without `--wait` it is detached and the command returns the run id. `--trigger scheduled` is the tick's spelling and nobody else's. |
| `routines runs <id> [--limit N]` | The routine's recent runs. |
| `routines log <id> [<run_id>]` | A run's log, the last run's by default. |
| `routines remove <id>` | Deletes the definition and the state, keeps the ledger; stops the routine's chat agent if it has one, and never destroys it, since the chat is the user's to read or delete. |
| `routines wake <skill>` | Section 6.4. |
| `routines tick` | Section 6.1. |
| `routines migrate-cron` | Section 12. |

`routines add --every 1d --at 07:30 --skill inbox-digest` is the whole of what used to be a skill, a template, a cron line in two copies, and a state directory.

## 10. The app

### 10.1 Manifest and program

`system/apps/routines`, name `routines`, display name "Routines", `priority = "routines"` (a new band in `oom_priority`'s table between `files` at 75 and `getting-started` at 80: it stores nothing of its own, and a shed costs a reload), `critical = false`, `stop_when_no_windows = true`, `launcher_rank = 45`, `system = false`, `api_schema_path = "/api/schema"`, a default shortcut on `open` in `focus` mode, and a `[preview]` table over a copy of `data/.state/routines`.
The program registers on port 8050 (no built-in uses it) and runs the `routines-app` entry point, like Memory & disk.
The app depends on the library and imports nothing from mngr.

### 10.2 Pages

The frontend is a Mithril and Tailwind build in the npm workspace, over `workspace_ui` (its tokens, `Button`, badges, the Menu, toasts, the app contract, the element context menu), laid out like Files.
One document serves every page; the page routes on its path and reports it through `shell:location`.

- **`/`, the list.** A summary strip (how many routines, how many need attention, the next run), then one row per routine: title and sentence, the schedule and "Next: tomorrow 7:30 am", a health pill, "Last run 3 hours ago, automatic", and the run's summary.
  Rows needing attention sort first, then by title.
  Routines with an `app` group under that app's display name (from the registry), the rest under "Workspace".
  A text field at the top, "Describe a routine to add", hands "Add a routine: <the text>" to the shell through `startWithText`, so a chat opens on it and the agent, following the `manage-routines` skill, writes the definition.
- **`/<id>`, the routine.** The definition in plain words, the controls (Run now, On/Off, Change schedule, Fix it, Remove), and the run history: one row per run with when, trigger, outcome, duration, summary, and for a skill run a link to its chat.
  Change schedule opens a dialog with the same fields as the CLI (a number and a unit, a time, weekdays, a day of the month) and previews the sentence it will read as.
- **`/<id>/runs/<run_id>`, the run.** The finished event's fields and the log, rendered as is and scrolled to its end.
- The phone layout stacks the row's cells and puts the controls in a menu.

Fix it builds a brief from the routine, its last runs, and their logs, and opens a chat on it through `message_chat.py --create` with `auto_open=true`, as the reference template did; the brief links the routine's page.

### 10.3 API

Typed routes in `app_schema`'s route table, every model in the library's `data_types.py` so the CLI's JSON and the API's JSON are the same shapes:

| Route | Answers |
|---|---|
| `GET /api/routines` | `RoutineListing`. |
| `GET /api/routines/<id>` | `RoutineDetail` with recent runs. |
| `GET /api/routines/<id>/runs/<run_id>` | `RunDetail` with the log tail; `?log` the whole log as text. |
| `POST /api/routines/<id>/run` | Starts a manual run; 409 while one is in flight. |
| `PUT /api/routines/<id>/enabled` | `{"is_enabled": bool}`. |
| `PUT /api/routines/<id>/schedule` | The schedule fields; 400 with the validation message. |
| `POST /api/routines/<id>/fix` | Opens the fix chat; answers its id. |
| `DELETE /api/routines/<id>` | Removes the routine. |
| `GET /api/health`, `GET /api/schema` | As every app. |

Every mutation goes through the library, which is what the CLI runs, so the app and an agent cannot disagree.
The page polls the listing every 30 seconds, every 5 while a run is in flight, and never while a dialog is open.

## 11. Built-in routines and the Caretaker

The template ships one definition, `system/routines/caretaker.toml`:

```toml
title = "Weekly check-up"
what = "Looks over the workspace once a week and opens a chat if something needs attention."
every = "1w"
at = "03:00"
command = ["bash", "system/services/caretaker/caretaker_check.sh"]
enabled = false
timeout = "2h"
```

The check keeps its four findings and adds a fifth, read with `routines list --format json`: routines whose last run failed, that are overdue, or that are blocked, since the check's last run.
With findings it ends with `exec uv run --no-sync routines wake caretaker`, so the agent's chat is the run's chat and the run ends when the agent's turn does.
The `caretaker` create template goes; the role it carried moves into the `caretaker` skill's opening, and the agent is created from the `automation` template like every other.
The `enable-caretaker` and `disable-caretaker` skills go; the Routines app's switch and `routines enable caretaker` are the switch.
The Caretaker's own notes and permissions stay under `data/.state/caretaker/`, untouched by the switch, as before.

The daily routines-only check is a second definition later, `caretaker-routines.toml`, running the same script with `--only routines`; the script takes the flag now and nothing else is needed then.

## 12. Migration and compatibility

`routines migrate-cron` converts what a workspace has:

- Every `data/.state/cron.d` entry whose line runs `run_job.sh` becomes a definition: the job id, `--every`, `--at`, and `--retry-after` map to the fields; a command that is `run_automation.sh <skill>` becomes `skill`; a `caretaker` entry becomes the switch on the shipped definition.
  `data/.state/jobs/<id>/` becomes the state's `last_succeeded_at` and `consecutive_failures`.
  The title is the id with the hyphens read as spaces, and `what` is the command, until an agent describes it.
- A plain cron line whose five fields are one of the shapes section 5 expresses becomes a definition the same way; one that is not is left in place with a warning in the tick log, since the daemon still runs it.
- Both copies of every converted entry are removed.

The bootstrap runs it at every boot, after the first-boot commit and before writing the tick entry; it is a no-op once nothing is left, and the recovery guard is never touched.
The definitions it writes are committed as every definition write is (section 4), one commit for the whole migration.

`system/libs/automations` goes once the migration ships; `run_job.sh`'s tests become the library's.
`CLEANUP:` marks the migration and the legacy readers for removal once every workspace has booted a build that has them.

## 13. Documents, skills, and instructions

- A `manage-routines` skill replaces `manage-scheduled-tasks`, `enable-caretaker`, and `disable-caretaker`: when to make something a routine, the `routines add` forms, how to describe one, and the timezone check it keeps.
- `build-app` and `update-app`: periodic work in an app is a routine with `app = <name>`, never a loop or a thread inside the service; the scaffold's README says so.
- `AGENTS.md`: the "Apps and services" paragraph names routines and the skill; the vocabulary paragraph says an automation is a skill routine.
- `system/apps/README.md`, `system/libs/README.md`, `docs/system/workspace-internals.md`, `system/services/caretaker/README.md`, and the root README's creations list.
- The library's README is the reference for the file formats; this spec is the design.
- Changelog entries for every project touched.

## 14. Changes outside this repo

One, in the Imbue Studio app (`apps/minds` in the mngr repo): `AgentNotificationRequest` gains an optional `destination`, `{"app": "<app name>", "path": "/<path>"}`.
The feed entry carries it, and opening the entry lands the user on that app's page in the workspace rather than in a chat; an entry from an agent that is not a chat (the services agent) and names no destination raises the workspace.
A desktop that does not know the field keeps today's behaviour, so the runner sends it unconditionally.
The latchkey gateway's per-agent grant for the notifications route must cover the services agent; if it does not, that grant is part of the same change.
That change is its own PR on the mngr repo and lands before the template's.

## 15. Testing

- `schedule_test.py`: every rule of 5.1 as a table, the month clamp, the weekday move, the retry floor, catch-up after a gap, `once` before and after success, and the described sentences by inline snapshot.
- `runner_test.py`: a command run over a real subprocess (a script that prints and exits as told): the log is streamed, the events are written, the state is updated, a timeout kills the process group, a held lock refuses a second run, a dead `current_run` is reaped as `interrupted`, `result.json` is read.
- `wake_test.py`: the skill run over a fake chat app (an HTTP server answering the four routes it uses) and a fake `mngr` on the PATH: create on first run, restart when busy with the warning, blocked then succeeded, stopped is failed, timeout interrupts.
- `notifications_test.py`: the three rules over a fake gateway: one notification per streak, recovery, blocked once per run, and a dead gateway logged and ignored.
- `cli_test.py`: every subcommand over a temporary workspace root, `add` refusing a bad definition with the validator's message, `edit` keeping a comment.
- `migrate_cron_test.py`: the shapes of 12 and the one left in place.
- The app: `assert_api_schema_describes_app`, every route, and `vitest` over the views as Files does; the manifest in `system/test_app_manifests.py`'s built-in table.
- The bootstrap: the tick entry is rewritten every boot and can run from cron's own PATH, as the recovery guard's tests check.
- `system/test_routines.py`: a routine with `every = "1m"` in a temporary state dir runs through a real tick and shows up in `routines list`.
- Manual, on a workspace: add a routine from a chat, see it listed; run it now and watch the row turn to running and back; turn it off; turn on the Caretaker and see its introduction; break a routine and see the feed notification land on its page.

## 16. Implementation order

One commit per step, each leaving the tree green:

1. The library's definitions, schedule, state, and ledger with their tests.
2. The runner for command runs, the tick, and the bootstrap entry.
3. The skill run and `routines wake`.
4. Notifications.
5. The CLI.
6. The migration, the Caretaker definition, and the retirement of `system/libs/automations` and the two enabling skills.
7. The app's backend and API.
8. The app's frontend.
9. The skills and documents.

The minds change (section 14) can land at any point before step 4 ships to users.

## 17. Out of scope

- Routines that run while the workspace is stopped (the `mngr schedule` plugin on Modal is the path when it comes).
- Services with internal timers.
- Cron expressions and anything they express that section 5 does not.
- Running a routine's command somewhere other than the workspace.
- Cost per run; `mngr usage` already attributes a chat's spend, and the run page links the chat.
