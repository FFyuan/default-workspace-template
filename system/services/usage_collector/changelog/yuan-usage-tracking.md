New service: `usage-collector` keeps the workspace's record of model calls. It follows every usage event file in the workspace, about once a second and from where it left off: each agent's mngr_usage event file, the preserved files of destroyed agents, and the files `workspace_usage` writes for apps and one-shot calls under `data/.apps/usage/events/`. It indexes their `model_call` events in SQLite under `data/.apps/usage/`, with per-minute rollups, and serves cost and token totals grouped by any attribution field, model, billing mode and time bucket (`GET /v1/totals`) and a live stream of new calls (`GET /v1/stream`) on 127.0.0.1:8795.

The event files are the source of truth: the database is an index of them and is rebuilt by re-reading them when it is deleted. Events are idempotent by id and attributed to this workspace; an unknown cost is stored as unknown, never $0, and a token-only event is priced from mngr_usage's price table. Who may read usage is decided by the share gateway's grants on the Usage app, like any other app: the API listens on 127.0.0.1 only.

It also answers the questions the Usage app asks:

- `GET /v1/latency` reports p50 and p95 call duration per group, leaving out and counting calls with no duration, and counting the ones timed from Claude session logs as approximate; it can be filtered to calls whose fields take given values (a provider's calls on several billing modes), since percentiles do not add up across groups.

- `GET /v1/calls` lists stored calls newest first, filtered by origin, agent, model, billing mode or provider (any of several values), with how many calls match, paging by `offset` or back with `before`, and catching up after a reconnect with `after`.

- Totals can be grouped by `cost_provenance`, so a reader can tell which costs were estimated from tokens.

- `GET /health` reports `catching_up` until the collector has read every event file to its end.

- `GET /v1/limits` answers the freshest subscription limit reading of every window per source (Claude's 5-hour and weekly limits, Codex's): the collector now reads the `rate_limits` on agents' snapshot events and on model_calls instead of skipping them.

- The collector keeps the id of every event it has counted, past the 90 days it keeps raw events, so a file read again from its start (a destroyed agent's preserved copy, a restored backup) never counts an old call twice.

The usage collector stores each call's `turn_id` (a new, indexed column; an existing database gains it when the collector starts). Totals can be grouped by `turn_id` (`/v1/totals?group_by=turn_id`), and `/v1/calls` filters by `turn_id`, `session_id` and `run_id` as well as the rollup dimensions, e.g. `?turn_id=<id>` for one turn's calls.
