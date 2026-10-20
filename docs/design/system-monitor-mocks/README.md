# System monitor mocks

Static design mocks for the Memory & disk app (`system/apps/system_monitor/`):
the page as shipped today, then ten directions that add CPU usage and try a
different layout or information architecture each. They exist to decide what
the app should become; none of them is wired to the app.

Open `index.html` in a browser. It lists the variants, frames the chosen one
at the app's usual window size (600 x 800, with a few other sizes to try), and
shows all of them scaled down at the bottom.

- `00-current.html` -- the shipped page with sample data (no CPU).
- `01-overview.html` -- three tiles with sparklines, one breakdown table with a CPU column.
- `02-tabs.html` -- one resource per tab in a segmented control.
- `03-activity-monitor.html` -- after macOS Activity Monitor: process table and a bottom summary pane.
- `04-task-manager.html` -- after Windows Task Manager: resource list on the left, big graph on the right.
- `05-usage-and-tokens.html` -- machine meters plus today's AI usage (cost, tokens, rate-limit windows, per chat).
- `06-timeline.html` -- CPU and memory on one time chart with events marked on it.
- `07-by-chat.html` -- a card per chat, checker and app, each with a Stop button.
- `08-widget.html` -- a small pinned strip of three meters that unfolds on click.
- `09-health.html` -- a verdict, ring gauges, and what to do about it; details fold away.
- `10-terminal.html` -- after htop: monospace, per-core bars, block-character history.

Every page is plain HTML with no build step, as the shipped page is. They share
`shared/mock.css` (the workspace's design tokens copied from
`system/libs/workspace_ui/src/base.css`, plus the few recipes the pages reuse)
and `shared/mock.js` (one set of sample data and the sparkline helpers), so a
change to the data or the tokens shows on every page.
