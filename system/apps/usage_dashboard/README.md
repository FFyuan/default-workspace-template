# usage_dashboard (the Usage app)

The Usage app: one window over the workspace's model usage. It is the user's view
of the usage collector (`system/services/usage_collector`), which indexes every
model call made in the workspace; the app stores nothing of its own.

The app has three kinds of page, one document reading its path:

- **`/`, the home page**: one card per provider in use, answering "how much of my
  subscription am I using", then a **Total** row of tiles across every provider
  with the time window picker. Each card links to its provider's detail page, and
  the Total row to all usage.
  - **A subscription card** for every harness that reports its subscription's
    limits (Claude Pro/Max, a ChatGPT plan through Codex): each window's share
    used, as a bar, and when it resets, from the freshest reading the collector
    has. A reading is only as new as the last call that carried one, so the card
    says when it was taken; a window whose reset time has passed since then shows
    as reset. A provider is shown while it has a reading from the last 7 days, and
    its card adds what this month's use would cost at API prices.
  - **A spend card** for every provider used without a subscription (an API key,
    Imbue's proxy, a billing mode no writer could tell): this month's spend and
    calls, with calls of unknown cost counted rather than added as $0.
- **`/p/<item>`, a provider's detail page**, where the item is a section key
  (`subscription:anthropic`, `spend:openai`): a list of every provider (with its
  limits or spend) and All on the left, and on the right the provider's card,
  the window picker, its tiles, its chart, its breakdown and its latest calls.
  A provider's subscription use and its use without one are separate items.
- **`/all`**: the same for every provider at once.

Nothing names a provider it must find; a card or item exists only for what the
data shows. The window is the last 30 minutes, 24 hours, 7 days or this month
(the billing period, which starts at local midnight on the 1st). Every detail
query is grouped by provider and billing mode as well, so a provider's figures
are picked out of the same answers the Total row adds up; a provider's latency
and its latest calls are asked for on their own, filtered to its provider and
billing modes, since percentiles do not add up. What the tiles, charts and breakdowns show:

- **Spend**: what was billed, with Imbue key and API key spend apart. A
  subscription's usage is shown in its own tile at list price, since it is not
  billed per call. Calls whose cost or billing mode is unknown are counted beside
  the total rather than added as $0, and a total that includes a cost the
  collector estimated from tokens carries a "~".
- **Tokens** (input, output, cache read and cache write), **calls** with the share
  that failed or were rate-limited, and **latency** (p50 and p95 of each call's
  duration; calls with no duration are counted apart, and durations from Claude
  session logs are marked approximate).
- A chart of spend or tokens over the window, stacked by model.
- A breakdown by model, source (the app, chat or routine that made the calls) or
  billing mode. Clicking a row filters the whole page to it.
- The latest calls, newest first, as they happen, each with its raw event.

Day views ask the collector for hourly buckets and add them up into local days in
the browser, because the collector's own day buckets start at UTC midnight.

## Server

`usage-dashboard` serves the page on 8060 and forwards the page's reads to the
collector, which listens on 127.0.0.1:8795 only:

| Route | Answers |
|---|---|
| `GET /api/usage/totals`, `/latency`, `/calls`, `/limits`, `/health` | the collector's `/v1/totals`, `/v1/latency`, `/v1/calls`, `/v1/limits` and `/health`, with the same query |
| `GET /api/usage/stream` | the collector's server-sent events, relayed |
| `GET /api/apps` | the display name of every registered app |
| `GET /api/health` | whether the app is up and its page built |
| `GET /widget` | the Usage widget, which the workspace shell keeps in a corner of the desktop |

Who sees usage is the workspace's sharing grants, as for any app: the share
gateway admits a visitor with a workspace-wide grant or a grant on this app, and
the collector, listening on 127.0.0.1 only, is reached from outside the
workspace only through this server. The manifest declares `system = true`, so
the Share tab lists the app under System with System Monitor.
An unreachable collector is answered with 503; the page then keeps its last
numbers under a banner and retries.

## Frontend

`frontend/` is a Vite, TypeScript and Mithril build in the `system/package.json`
npm workspace, using `@imbue/workspace-ui`. `npm run build` in `system/` writes it
to `src/usage_dashboard/static/`. Charts are plain SVG.

The manifest declares a `[widget]` at `/widget`, enabled by default
(`docs/system/blueprint/app-widgets/plan-app-widgets.md`, section 7): a second
Vite entry (`widget.html`, `src/widget.ts`) that reads the limits, this month's
totals and the collector's health, and reuses the page's provider cards, so the
two never disagree. Expanded, it is a row per provider (a subscription's
5-hour bar and weekly figure, an API's spend this month); collapsed, the most
used subscription window, else the month's spend. It reports its size to the
shell after every change, hides itself while there is no usage, and opens the
Usage window when clicked. While the widget is enabled the shell keeps this app
running, though it declares `stop_when_no_windows`.
