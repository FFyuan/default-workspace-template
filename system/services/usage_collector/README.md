# usage_collector

The workspace's record of model calls. Every model call made in the workspace
becomes one `model_call` event (the schema in mngr's `imbue.mngr_usage.model_call`),
stored in SQLite under `data/.apps/usage/usage.db` and served on
`http://127.0.0.1:8795`. Usage data never leaves the workspace except in its own
encrypted backup.

## Where events come from

- **Agents.** Agent harnesses write `model_call` events to each agent's own
  mngr_usage event file (`$MNGR_HOST_DIR/agents/<agent>/events/<source>/usage/events.jsonl`,
  and the copies mngr preserves for destroyed agents). The collector reads each
  file from where it left off, about once a second, and remembers its place
  across restarts. Lines that are not `model_call` events are left to `mngr usage`.
- **Apps.** Apps report through the `workspace_usage` library: `POST /v1/events`
  with one event or a list of them.
- **`claude -p` one-shots.** The caller runs the one-shot under a known session
  id and reports it with `POST /v1/claude-sessions`; the collector reads the
  calls from its session log with mngr_usage's reader, then deletes the log.

When the collector is down, `workspace_usage` spools reports under
`data/.apps/usage/spool/`, and the collector drains them when it is back.
Events are idempotent by `event_id`, so a replay never double-counts. A call
whose cost is unknown is stored with no cost, never $0; one with tokens but no
cost is priced from mngr_usage's price table and marked estimated.

## API

- `GET /v1/totals?group_by=origin_id,model&since=24h[&until=...][&bucket=hour]`:
  calls, cost and tokens per group. `since` and `until` take a duration
  (`90s`, `30m`, `24h`, `7d`) or an ISO timestamp. Grouping only by origin,
  agent, model and billing mode reads per-minute rollups; any other field reads
  raw events (kept 90 days).
- `GET /v1/stream`: server-sent events, one `model_call` message per newly
  stored event.
- `GET /health`.

Requests the share gateway marks as a visitor's (`X-Imbue-Identity` with
`"owner": false`) are refused: usage is the owner's alone.
