/**
 * The page's state: the chosen window, breakdown and filter, what the collector last answered for them, the
 * latest calls, and the live stream that keeps them current.
 *
 * The page never adds up streamed calls itself: a new call schedules a refetch of the totals shortly after
 * (debounced, so a burst costs one), and the calls list takes the call as it arrives. The live windows refetch on
 * every new call; the long ones at most every SLOW_REFRESH_MS. A timer refetches every PERIODIC_REFRESH_MS too,
 * so a rolling window keeps moving with no calls at all.
 */

import { ReconnectBackoff } from "@imbue/workspace-ui/src/models/backoff";

import {
  type LatencyRow,
  type ModelCall,
  type StoredCall,
  type TotalsRow,
  fetchAppNames,
  fetchCalls,
  fetchCollectorHealth,
  fetchLatency,
  fetchTotals,
  isUnreachable,
} from "./api";
import {
  type BreakdownId,
  type Filter,
  breakdownSpec,
  callGroup,
  filterKey,
  matchesFilter,
  withFilterFields,
} from "./breakdown";
import { type Summary, failedShare, summarize } from "./summary";
import { type WindowId, windowSpec, windowStart } from "./windows";

export const EVENT_DEBOUNCE_MS = 2_000;
export const SLOW_REFRESH_MS = 30_000;
export const PERIODIC_REFRESH_MS = 60_000;
export const CALLS_PAGE = 50;
const MAX_CALLS_KEPT = 300;
const GAP_FILL_LIMIT = 500;

export type ChartMetric = "spend" | "tokens";

export interface DashboardData {
  summary: Summary;
  failed: { calls: number; failed: number };
  latency: LatencyRow | null;
  /** Totals by model and billing mode (and the filter's fields), bucketed, already filtered. */
  chartRows: TotalsRow[];
  /** Totals by the breakdown's fields and billing mode (and the filter's), already filtered. */
  breakdownRows: TotalsRow[];
  breakdownLatency: LatencyRow[];
  windowId: WindowId;
  breakdown: BreakdownId;
  loadedAt: Date;
}

export interface StreamLike {
  addEventListener(type: string, listener: (event: MessageEvent<string>) => void): void;
  onopen: ((event: Event) => void) | null;
  onerror: ((event: Event) => void) | null;
  close(): void;
}

export interface DashboardDeps {
  now: () => Date;
  redraw: () => void;
  openStream: (url: string) => StreamLike;
}

export const STREAM_URL = "/api/usage/stream";

export class DashboardModel {
  windowId: WindowId = "24h";
  breakdown: BreakdownId = "model";
  filter: Filter | null = null;
  chartMetric: ChartMetric | null = null;
  data: DashboardData | null = null;
  calls: StoredCall[] = [];
  hasOlderCalls = false;
  appNames: Record<string, string> = {};
  isLoading = false;
  isCollectorDown = false;
  isCatchingUp = false;
  isLive = false;
  errorMessage: string | null = null;
  expandedCallId: string | null = null;

  private generation = 0;
  private lastSequence: number | null = null;
  private lastRefreshAt = 0;
  private stream: StreamLike | null = null;
  private wasDisconnected = false;
  private readonly streamBackoff = new ReconnectBackoff();
  private readonly retryBackoff = new ReconnectBackoff();
  private eventRefresh: ReturnType<typeof setTimeout> | null = null;
  private retry: ReturnType<typeof setTimeout> | null = null;
  private periodic: ReturnType<typeof setInterval> | null = null;

  constructor(private readonly deps: DashboardDeps) {}

  start(): void {
    void fetchAppNames()
      .then((names) => {
        this.appNames = names;
        this.deps.redraw();
      })
      .catch(() => undefined);
    void this.refresh();
    void this.loadCalls();
    this.connectStream();
    this.periodic = setInterval(() => void this.refresh(), PERIODIC_REFRESH_MS);
  }

  stop(): void {
    this.stream?.close();
    this.stream = null;
    for (const timer of [this.eventRefresh, this.retry]) if (timer !== null) clearTimeout(timer);
    if (this.periodic !== null) clearInterval(this.periodic);
  }

  selectWindow(windowId: WindowId): void {
    this.windowId = windowId;
    void this.refresh();
  }

  selectBreakdown(breakdown: BreakdownId): void {
    this.breakdown = breakdown;
    void this.refresh();
  }

  selectChartMetric(metric: ChartMetric): void {
    this.chartMetric = metric;
    this.deps.redraw();
  }

  /** Filter the page to ``filter``, or clear the filter when it is the one already set. */
  toggleFilter(filter: Filter | null): void {
    this.filter =
      filter !== null && this.filter !== null && filterKey(filter) === filterKey(this.filter) ? null : filter;
    void this.refresh();
    void this.loadCalls();
  }

  toggleCall(eventId: string): void {
    this.expandedCallId = this.expandedCallId === eventId ? null : eventId;
    this.deps.redraw();
  }

  /** Fetch everything the tiles, the chart and the breakdown show for the current window, breakdown and filter. */
  async refresh(): Promise<void> {
    const generation = ++this.generation;
    const { windowId, breakdown, filter } = this;
    const now = this.deps.now();
    const since = windowStart(windowId, now);
    const bucket = windowSpec(windowId).bucket;
    const filterFields = withFilterFields([], filter);
    const breakdownFields = withFilterFields(breakdownSpec(breakdown).fields, filter);
    this.isLoading = true;
    this.lastRefreshAt = now.getTime();
    this.deps.redraw();
    try {
      const [summaryRows, statusRows, chartRows, breakdownRows, latencyRows, breakdownLatency, health] =
        await Promise.all([
          fetchTotals({ groupBy: withFilterFields(["billing_mode", "cost_provenance"], filter), since }),
          fetchTotals({ groupBy: withFilterFields(["status"], filter), since }),
          fetchTotals({ groupBy: withFilterFields(["model", "billing_mode"], filter), since, bucket }),
          fetchTotals({
            groupBy: withFilterFields([...breakdownSpec(breakdown).fields, "billing_mode"], filter),
            since,
          }),
          fetchLatency(filterFields, since),
          fetchLatency(breakdownFields, since),
          fetchCollectorHealth(),
        ]);
      if (generation !== this.generation) return;
      const keep = <T extends { group: Record<string, string | null> }>(rows: T[]): T[] =>
        rows.filter((row) => matchesFilter(row.group, filter));
      this.data = {
        summary: summarize(keep(summaryRows)),
        failed: failedShare(keep(statusRows)),
        latency: keep(latencyRows)[0] ?? null,
        chartRows: keep(chartRows),
        breakdownRows: keep(breakdownRows),
        breakdownLatency: keep(breakdownLatency),
        windowId,
        breakdown,
        loadedAt: now,
      };
      this.isCatchingUp = health.catching_up;
      this.isCollectorDown = false;
      this.errorMessage = null;
      this.retryBackoff.reset();
    } catch (error) {
      if (generation !== this.generation) return;
      this.noteFailure(error, () => void this.refresh());
    } finally {
      if (generation === this.generation) {
        this.isLoading = false;
        this.deps.redraw();
      }
    }
  }

  /** Replace the calls list with the newest calls matching the filter. */
  async loadCalls(): Promise<void> {
    const filter = this.filter;
    try {
      const calls = await fetchCalls({ filters: filter?.values ?? {}, limit: CALLS_PAGE });
      if (filter !== this.filter) return;
      this.calls = calls;
      this.hasOlderCalls = calls.length === CALLS_PAGE;
      this.noteSequences(calls);
    } catch (error) {
      this.noteFailure(error, () => void this.loadCalls());
    }
    this.deps.redraw();
  }

  async loadOlderCalls(): Promise<void> {
    const oldest = this.calls[this.calls.length - 1] as StoredCall | undefined;
    if (oldest === undefined) return;
    const filter = this.filter;
    try {
      const older = await fetchCalls({
        filters: filter?.values ?? {},
        limit: CALLS_PAGE,
        before: oldest.event.event_id,
      });
      if (filter !== this.filter) return;
      this.calls = [...this.calls, ...older];
      this.hasOlderCalls = older.length === CALLS_PAGE;
    } catch (error) {
      this.noteFailure(error, () => undefined);
    }
    this.deps.redraw();
  }

  /** Take one streamed call: show it if it matches the filter, and schedule a refetch of the totals. */
  receiveCall(call: ModelCall): void {
    if (matchesFilter(callGroup(call), this.filter)) {
      this.mergeCalls([{ sequence: 0, event: call }]);
    }
    this.scheduleEventRefresh();
    this.deps.redraw();
  }

  /** Record why a read failed: a collector that is down (retried with backoff), or anything else. */
  private noteFailure(error: unknown, retry: () => void): void {
    if (isUnreachable(error)) {
      this.isCollectorDown = true;
      if (this.retry === null) {
        this.retry = setTimeout(() => {
          this.retry = null;
          retry();
        }, this.retryBackoff.nextDelay());
      }
      return;
    }
    this.errorMessage = error instanceof Error ? error.message : String(error);
  }

  private noteSequences(calls: readonly StoredCall[]): void {
    for (const call of calls) {
      if (call.sequence > (this.lastSequence ?? 0)) this.lastSequence = call.sequence;
    }
  }

  /** Add calls the list does not have yet, keeping it newest first. */
  private mergeCalls(incoming: readonly StoredCall[]): void {
    const known = new Set(this.calls.map((call) => call.event.event_id));
    const added = incoming.filter((call) => !known.has(call.event.event_id));
    if (added.length === 0) return;
    this.calls = [...added, ...this.calls]
      .sort((a, b) => Date.parse(b.event.ended_at) - Date.parse(a.event.ended_at))
      .slice(0, MAX_CALLS_KEPT);
  }

  private scheduleEventRefresh(): void {
    if (this.eventRefresh !== null) return;
    const sinceLast = this.deps.now().getTime() - this.lastRefreshAt;
    const wait = windowSpec(this.windowId).isLive
      ? EVENT_DEBOUNCE_MS
      : Math.max(EVENT_DEBOUNCE_MS, SLOW_REFRESH_MS - sinceLast);
    this.eventRefresh = setTimeout(() => {
      this.eventRefresh = null;
      void this.refresh();
    }, wait);
  }

  private connectStream(): void {
    const stream = this.deps.openStream(STREAM_URL);
    this.stream = stream;
    stream.onopen = () => {
      this.isLive = true;
      this.streamBackoff.reset();
      if (this.wasDisconnected) {
        this.wasDisconnected = false;
        void this.fillGap();
      }
      this.deps.redraw();
    };
    stream.addEventListener("model_call", (event) => {
      this.receiveCall(JSON.parse(event.data) as ModelCall);
    });
    stream.onerror = () => {
      stream.close();
      if (this.stream !== stream) return;
      this.stream = null;
      this.isLive = false;
      this.wasDisconnected = true;
      this.deps.redraw();
      setTimeout(() => this.connectStream(), this.streamBackoff.nextDelay());
    };
  }

  /** After a reconnect: the calls stored while the stream was down, then fresh totals. */
  private async fillGap(): Promise<void> {
    const filter = this.filter;
    try {
      const missed = await fetchCalls({
        filters: filter?.values ?? {},
        limit: GAP_FILL_LIMIT,
        after: this.lastSequence ?? undefined,
      });
      if (filter === this.filter) {
        this.mergeCalls(missed);
        this.noteSequences(missed);
      }
    } catch (error) {
      this.noteFailure(error, () => void this.fillGap());
    }
    void this.refresh();
  }
}
