# usage_dashboard (the Usage app)

The Usage app: one window over the workspace's model usage. It is the user's view
of the usage collector (`system/services/usage_collector`), which indexes every
model call made in the workspace; the app stores nothing of its own.

The page shows, for the last 30 minutes, 24 hours, 7 days or this month (the
billing period, which starts at local midnight on the 1st):

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
| `GET /api/usage/totals`, `/latency`, `/calls`, `/health` | the collector's `/v1/totals`, `/v1/latency`, `/v1/calls` and `/health`, with the same query |
| `GET /api/usage/stream` | the collector's server-sent events, relayed |
| `GET /api/apps` | the display name of every registered app |
| `GET /api/health` | whether the app is up and its page built |

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
