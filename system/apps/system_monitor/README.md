# system-monitor

The System Monitor app: how much CPU, memory and disk this workspace is using,
on one page with an overview and a view per resource, refreshed every five
seconds. The design is `docs/system/specs/system-monitor.md`.

- **Overview** (`/`): three tiles, CPU as a share of the cores, memory and
  disk as a share of their totals, the first two with the last 10 minutes
  drawn under them; each opens its view. Then what is using the workspace
  (the breakdown below, with CPU and memory columns), and the recent events:
  the programs the memory guard stopped and the busy stretches of the last
  24 hours, newest first.
- **CPU** (`/cpu`): the share of the cores in use, a chart over 10 minutes, an
  hour or a day, what is using the CPU (the breakdown sorted by share; a
  chat's share includes whatever it is running), and the busy stretches.
- **Memory** (`/memory`): what the Memory & disk page showed: used out of
  total, the memory guard's 90% mark on the bar and the chart, a note from
  80% used naming the largest kind of memory the user can free, the
  breakdown, and the stops with their commands behind a Details toggle.
- **Disk** (`/disk`): used out of total; the state of the backups (read from
  the backup service's events and settings, never by running restic), with a
  link to that service's README; and "See what's using the disk", which
  measures the disk only when asked (walking it is slow under gVisor and the
  figures go stale at once): workspace files, uploads, each app's data,
  package caches, and everything else, as of when it ran.

Moving between views is a plain navigation, so the shell reopens a window on
the view it was on.

**What's using the workspace** (`usage`): chats on any agent type (claude,
codex, pi), each with whatever it is running, found through oom_priority's
agent-pid registry; code checkers; the workspace's own programs (chat app,
desktop, built-in apps, background services); and the apps the user built.

- Where the kernel reports each program's own and proportional memory
  (`/proc/<pid>/smaps_rollup`), each row holds its programs' private memory,
  about what stopping them frees. Memory several programs map (the Python
  and Node runtimes, Chromium, system libraries) is counted once in a Shared
  row, the files in the scratch space (`/tmp`) are a Temporary files row, and
  the rest of the memory in use (the kernel, programs this app cannot
  inspect) is a System row. The rows add up to the memory in use
  (`usage.exact_usage`).
- Where it does not (gVisor), only resident sizes are available, and each is
  scaled down by one factor until the rows add up to what is in use less the
  scratch space (`usage.scaled_usage`). The page then says the values are
  approximate.
- The Temporary files row appears only where `/tmp` is a tmpfs (every workspace
  today), since only then are its files held in memory; it shows its size
  limit, and an info popup explains what it is.
- Each row's CPU is the sum of the sampler's per-process shares (below) over
  the row's processes, rolled up by the same owner walk as memory; a process's
  share includes the children it has reaped, so a finished test run lands
  with the chat that ran it.

**The resource sampler.** CPU and the graphs come from the `resource_sampler`
program beside the memory guard (`system/services/oom_priority`), which walks
`/proc` every 5 s and writes under `data/.state/system-monitor/`: the latest
reading with each process's share and the last 10 minutes (`recent.json`), a
day of minute averages (`history.jsonl`), and the busy stretches, CPU above
90% for a minute or more, with the chats and programs that caused them
(`events/cpu_stretches/events.jsonl`). The app reads those files (`cpu`) and
writes nothing. A reading older than 30 s counts as none: the graphs say "No
readings yet" and the CPU column shows dashes.

**Programs stopped to free memory** (`stops`): each stop the memory guard
(earlyoom, see `system/services/oom_priority/`) recorded in the last 24
hours: when, and what it was in plain words, with the exact command behind a
Details toggle. The description and command come from pairing each record in
the shed ledger with the guard's own log line for it; a stop the log no
longer has keeps a plainer description and no Details.

The data comes from `/proc`, supervisord's control socket (through
`oom_priority.supervisor_rpc`), the app registry, the chat records under
`~/.mngr/agents/`, oom_priority's agent-pid registry and shed ledger,
earlyoom's log (`programs` and `stops`), the sampler's files, and the backup
service's events (`backups`).

The app keeps its own overhead low: running programs come from supervisord's
control socket, with no `supervisorctl` process started, every open window
shares one snapshot taken at most every 4 seconds (`stats.SharedSnapshot`), the
stop history and the guard's log are read only from their last 256 KB and 1 MB
and only again once they change (on a stop), the page is sent only the fields
it shows, and a hidden window stops polling. The on-demand disk walk runs one
`du` per row on a thread, at most one walk at a time (`disk.DiskScanner`).

Stops are paired with the guard's log lines newest first, on pid and process
name. The log is rotated and the ledger is not, so the oldest stops lose their
lines. Taken in that order they find none, so a later stop's line that reused
their pid can never mislabel them; they keep a plainer description with no
command.

Two known limits:

- A pid in the agent-pid registry is trusted while a process holds it. If an
  agent exits and an unrelated process reuses its pid before the next agent
  launch prunes the registry, that process counts as the agent's chat.
- Code checkers are recognised by command-line fragments of the common language
  servers (`programs.CODE_CHECKER_MARKERS`); one not in that list counts under
  the chat or program that started it.

The app describes its own HTTP API at `GET /api/schema` (the manifest's
`api_schema_path`), an OpenAPI document built from its routes by
`system/libs/app_schema`: `/api/stats` (the overview's reading),
`/api/history?span=1h|24h` (the longer graphs), `/api/disk` (the disk view),
and `POST /api/disk/scan` (start the walk).

Served on port 8040 by the `system-monitor` program.
