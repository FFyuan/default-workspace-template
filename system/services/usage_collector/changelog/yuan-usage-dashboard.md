The usage collector answers the questions the Usage dashboard asks:

- `GET /v1/latency` reports p50 and p95 call duration per group, leaving out and counting calls with no duration, and counting the ones timed from Claude session logs as approximate.

- `GET /v1/calls` lists stored calls newest first, filtered by origin, agent, model or billing mode, paging back with `before` and catching up after a reconnect with `after`.

- Totals can be grouped by `cost_provenance`, so a reader can tell which costs were estimated from tokens.

- `GET /health` reports `catching_up` until the collector has read every event file to its end.


- Visitors are no longer refused: the API listens on 127.0.0.1 only, so who may read usage is decided by the share gateway's grants on the Usage app, like any other app.
