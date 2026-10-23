New app: Usage, a window over the workspace's model usage, read from the usage collector. It opens on one card per provider in use, answering how much of each subscription is used: a subscription card with each limit's share used and when it resets (Claude, Codex, any harness that reports limits), or a spend card with this month's spend for usage without a subscription.

Below the cards, a Total row of tiles across every provider has the time window picker. Each card opens its provider's detail page: a list of every provider on the left, and on the right that provider's card, tiles, chart, breakdown and latest calls. For the last 30 minutes, 24 hours, 7 days or this month (from local midnight on the 1st), the pages show:

- what was billed (Imbue key and API key spend), with a subscription's usage at list price in its own tile, calls of unknown cost counted beside the total rather than added as $0, and a "~" on totals that include costs estimated from tokens;

- tokens, calls with the share that failed or were rate-limited, and p50 and p95 latency, with untimed calls counted apart and durations from Claude session logs marked approximate;

- a chart of spend or tokens over the window, stacked by model, and a breakdown by model, source or billing mode, where clicking a row filters the whole page;

- the latest calls as they happen, in numbered pages of 10, 20, 50 or 100 rows with a box to jump to a page, each opening to its raw event.

It stores nothing of its own, reconnects to the collector's live stream after an outage, keeps its last numbers under a banner while the collector is down, and says when the collector is still indexing past usage.

Who sees it follows the workspace's sharing grants, like any app: a visitor with a workspace-wide grant or a grant on Usage sees the same numbers as the owner. The Share tab lists it under System.

A subscription's chart shows each model's estimated usage as a share of its 5-hour or weekly limit, its breakdown shows each row's estimated share of each limit within that limit's most recent window, and its latest calls show each call's estimated share of each limit, in place of spend and cost: the calls are priced at API rates and the limit's last reported share is spread over them in proportion. After a window resets the estimate keeps the last reading's rate and says so, and dashed lines mark where the window started and reset.
