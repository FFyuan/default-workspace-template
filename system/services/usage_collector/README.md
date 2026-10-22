# usage_collector

The workspace's record of model calls. Every model call made in the workspace
is one `model_call` event (the schema in mngr's `imbue.mngr_usage.model_call`)
in an event file; the collector follows those files, keeps an index of them in
SQLite under `data/.apps/usage/usage.db`, and serves it on
`http://127.0.0.1:8795`. Usage data never leaves the workspace except in its
own encrypted backup.

## Where events come from

Every emitter appends to a file, and the collector only reads files, about
once a second, each from where it left off (its place survives restarts):

- **Agents.** Agent harnesses write `model_call` events to each agent's own
  mngr_usage event file (`$MNGR_HOST_DIR/agents/<agent>/events/<source>/usage/events.jsonl`),
  and mngr preserves a destroyed agent's files under `$MNGR_HOST_DIR/preserved/`.
  Lines that are not `model_call` events are left to `mngr usage`.
- **Apps and one-shot calls.** The `workspace_usage` library appends their
  events to `data/.apps/usage/events/<origin>.jsonl`: LiteLLM calls, and
  `claude -p` one-shots read from their session logs.

The files are the source of truth: the database is an index of them, and
deleting it rebuilds it by re-reading them. Events are idempotent by
`event_id`, so a re-read never double-counts. Every event is attributed to this
workspace. A call whose cost is unknown is stored with no cost, never $0; one
with tokens but no cost is priced from mngr_usage's price table and marked
estimated. The database keeps raw events 90 days and per-minute rollups
indefinitely; older raw events stay in the files.

## API

- `GET /v1/totals?group_by=origin_id,model&since=24h[&until=...][&bucket=hour]`:
  calls, cost and tokens per group. `since` and `until` take a duration
  (`90s`, `30m`, `24h`, `7d`) or an ISO timestamp. Grouping only by origin,
  agent, model and billing mode reads per-minute rollups; any other field reads
  raw events.
- `GET /v1/latency?group_by=model&since=24h[&until=...]`: p50 and p95 call
  duration (`ended_at` minus `started_at`) per group, from raw events. Calls
  with no duration are left out of the percentiles and counted, and calls
  timed from Claude session logs are counted as approximate.
- `GET /v1/calls?limit=50[&model=...][&before=<event id>][&after=<sequence>]`:
  stored calls, newest first, filtered by any of origin_kind, origin_id,
  agent_id, model and billing_mode. `before` pages back; `after` returns the
  calls stored since a `sequence` a client last saw.
- `GET /v1/stream`: server-sent events, one `model_call` message per newly
  stored event.
- `GET /health`: `catching_up` is true until a pass has read every event file
  to its end, so totals during a first start or a rebuild are incomplete.

The API listens on 127.0.0.1 only, so who may read usage is the share
gateway's grants: a visitor reaches it only through the Usage app, which the
gateway admits by a workspace-wide grant or a grant on the app.
