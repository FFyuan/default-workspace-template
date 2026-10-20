# System monitor mocks

Static design mocks for the Memory & disk app (`system/apps/system_monitor/`):
the page as shipped today, then ten directions that add CPU usage and try a
different layout or information architecture each. They exist to decide what
the app should become; none of them is wired to the app, and the app is
unchanged.

Open `index.html` in a browser. It lists the variants, frames the chosen one
at 600 x 800 (the size the app is expected to be used at) with the shell's real
frames as alternatives, and shows all of them scaled down at the bottom. The
shell gives the app no size of its own: a new window opens at the cascade frame,
60% x 70% of the desktop (`system/apps/system_interface/frontend/src/geometry/frames.ts`,
desktop-interface contracts section 10), which is landscape on a laptop, and a
snapped window is one half of it. The presets for those are the page area inside such a window on a 1440 x 900
desktop: the frame less the shell's 36 px title bar (`--desk-title-bar-height`,
contracts section 11).

The app has to stay simple and low-resource, so each variant comes with what
the real app would need to become it:

- `00-current.html` -- the shipped page with sample data (no CPU). Baseline:
  one snapshot of `/proc`, supervisord and the memory guard's records, taken at
  most every 4 s and polled every 5 s by each window; read-only.
- `01-overview.html` -- three tiles with sparklines, one breakdown table with a
  CPU column. Needs CPU per process (two `/proc/<pid>/stat` samples per
  snapshot) and a CPU history like memory's. Cheap; read-only.
- `02-tabs.html` -- one resource per tab in a segmented control. Needs
  per-process CPU, a disk walk for the what's-on-it rows (slow under gVisor, so
  cached or sampled) and a backup time from the backup service. Read-only.
- `03-activity-monitor.html` -- after macOS Activity Monitor: process table and
  a bottom summary pane. Needs per-process CPU and the process list the app
  already gathers, shown unaggregated. Cheap; read-only unless the table gets a
  Stop action.
- `04-task-manager.html` -- after Windows Task Manager: resource list on the
  left, big graph on the right. Needs per-process CPU, 60-minute histories kept
  while the app runs (today the app keeps 10 minutes, and the history starts over
  when the app restarts), and machine facts (vCPU model, size, runtime) the app has no source for yet.
  Read-only.
- `05-usage-and-tokens.html` -- machine meters plus today's AI usage (cost,
  tokens, rate-limit windows, per chat). Needs a new data source: per-chat
  tokens and cost from the chat records (what `mngr usage` reads), rate-limit
  windows (subscription accounts only), and cloud credits from the connector.
  Read-only, but another app's data.
- `06-timeline.html` -- CPU and memory on one time chart with events marked on
  it. Needs a CPU history beside memory's, kept for up to 24 h (a few KB), and
  events derived from the stop ledger and thresholds the app computes. Cheap;
  read-only.
- `07-by-chat.html` -- a card per chat, checker and app, each with a Stop
  button. Needs per-process CPU, idle time from the chat records, and
  Stop/Quit actions, which make the monitor a control surface (POST routes
  that stop agents and apps). Not read-only.
- `08-widget.html` -- a small pinned strip of three meters that unfolds on
  click. Needs per-process CPU and a pinned, title-bar-less window, which the
  shell offers only to taskbar entries today. Cheap data; a shell change.
- `09-health.html` -- a verdict, ring gauges, and what to do about it; details
  fold away. Needs rules for the verdict and suggestions (idle time per chat,
  what each would free), and the Stop/Clear/Resize actions if the suggestions
  are buttons rather than advice.
- `10-terminal.html` -- after htop: monospace, per-core bars, block-character
  history. Needs per-core CPU (`/proc/stat`) and per-process CPU; otherwise the
  data the app has. Cheap; read-only.

Every page is plain HTML with no build step, as the shipped page is. They share
`shared/mock.css` (the workspace's design tokens copied from
`system/libs/workspace_ui/src/base.css`, plus the few recipes the pages reuse)
and `shared/mock.js` (one set of sample data and the sparkline helpers). The
headline figures and histories come from that data; several pages hard-code
their labels and side facts (the tab labels, the details grids, the terminal's
process rows), so they are pictures of a direction rather than renderings of
the data, and a change to the sample data does not reach every number.
