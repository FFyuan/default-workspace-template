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
  fetchLimits,
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
import { LIMITS_LOOKBACK_MS, type ProviderCard, providerCards } from "./providers";
import { SECTION_FIELDS, type SectionSpec, detailSections, inSection } from "./sections";
import { type Summary, failedShare, summarize } from "./summary";
import { type WindowId, windowSpec, windowStart } from "./windows";

export const EVENT_DEBOUNCE_MS = 2_000;
export const SLOW_REFRESH_MS = 30_000;
export const PERIODIC_REFRESH_MS = 60_000;
export const CALLS_PAGE = 50;
const MAX_CALLS_KEPT = 300;
const GAP_FILL_LIMIT = 500;

export type ChartMetric = "spend" | "tokens";

/** The tiles' numbers for some set of calls: the Total row's, or one provider section's. */
export interface UsageFigures {
  summary: Summary;
  failed: { calls: number; failed: number };
  latency: LatencyRow | null;
}

/** One provider's details: its tiles, its chart rows (bucketed, by model) and its breakdown. */
export interface DetailSection extends UsageFigures {
  spec: SectionSpec;
  chartRows: TotalsRow[];
  breakdownRows: TotalsRow[];
  breakdownLatency: LatencyRow[];
}

export interface DashboardData {
  total: UsageFigures;
  sections: DetailSection[];
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
  /** The chart each section shows, once its viewer picked one; a section otherwise shows its default. */
  chartMetrics: Record<string, ChartMetric> = {};
  collapsedSections = new Set<string>();
  /** The cards at the top, which answer for now and this month whatever the Details window or filter. */
  providers: ProviderCard[] | null = null;
  isDetailsOpen = false;
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

  toggleDetails(): void {
    this.isDetailsOpen = !this.isDetailsOpen;
    this.deps.redraw();
  }

  selectChartMetric(sectionKey: string, metric: ChartMetric): void {
    this.chartMetrics = { ...this.chartMetrics, [sectionKey]: metric };
    this.deps.redraw();
  }

  toggleSection(sectionKey: string): void {
    if (this.collapsedSections.has(sectionKey)) this.collapsedSections.delete(sectionKey);
    else this.collapsedSections.add(sectionKey);
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
      const split = (fields: readonly string[]): string[] => withFilterFields([...fields, ...SECTION_FIELDS], filter);
      const [limits, monthRows, summaryRows, statusRows, chartRows, breakdownRows, totalLatency, health] =
        await Promise.all([
          fetchLimits(new Date(now.getTime() - LIMITS_LOOKBACK_MS)),
          fetchTotals({ groupBy: ["provider", "billing_mode", "cost_provenance"], since: windowStart("month", now) }),
          fetchTotals({ groupBy: split(["cost_provenance"]), since }),
          fetchTotals({ groupBy: split(["status"]), since }),
          fetchTotals({ groupBy: split(["model"]), since, bucket }),
          fetchTotals({ groupBy: split(breakdownSpec(breakdown).fields), since }),
          fetchLatency(filterFields, since),
          fetchCollectorHealth(),
        ]);
      if (generation !== this.generation) return;
      const keep = <T extends { group: Record<string, string | null> }>(rows: T[]): T[] =>
        rows.filter((row) => matchesFilter(row.group, filter));
      const specs = detailSections(keep(summaryRows));
      const sectionLatency = await Promise.all(
        specs.map((spec) => {
          const only = { provider: [spec.provider], billing_mode: spec.billingModes };
          return Promise.all([fetchLatency(filterFields, since, only), fetchLatency(breakdownFields, since, only)]);
        }),
      );
      if (generation !== this.generation) return;
      const within = <T extends { group: Record<string, string | null> }>(rows: T[], spec: SectionSpec): T[] =>
        keep(rows).filter((row) => inSection(row.group, spec));
      this.providers = providerCards(limits, monthRows, now);
      this.data = {
        total: {
          summary: summarize(keep(summaryRows)),
          failed: failedShare(keep(statusRows)),
          latency: keep(totalLatency)[0] ?? null,
        },
        sections: specs.map((spec, index) => ({
          spec,
          summary: summarize(within(summaryRows, spec)),
          failed: failedShare(within(statusRows, spec)),
          latency: keep(sectionLatency[index][0])[0] ?? null,
          chartRows: within(chartRows, spec),
          breakdownRows: within(breakdownRows, spec),
          breakdownLatency: keep(sectionLatency[index][1]),
        })),
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
