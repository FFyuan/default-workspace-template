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
import { DEFAULT_ROWS_PER_PAGE, type RowsPerPage, pageCount, pageHolding, pageOffset } from "./callPages";
import { LIMITS_LOOKBACK_MS, type ProviderCard, providerCards } from "./providers";
import { type Route, combinedFilters, inScope, scopeFilters } from "./routing";
import { SECTION_FIELDS, type SectionSpec, detailSections, inSection } from "./sections";
import { type Summary, failedShare, summarize } from "./summary";
import { type UsageScale, calibrationSpan, percentPerDollar } from "./usageEstimate";
import { type WindowId, windowSpec, windowStart } from "./windows";

export const EVENT_DEBOUNCE_MS = 2_000;
export const SLOW_REFRESH_MS = 30_000;
export const PERIODIC_REFRESH_MS = 60_000;

export type ChartMetric = "spend" | "tokens" | "usage";

/** The tiles' numbers for some set of calls: the Total row's, or one provider section's. */
export interface UsageFigures {
  summary: Summary;
  failed: { calls: number; failed: number };
  latency: LatencyRow | null;
}

/** A set of calls' tiles, chart rows (bucketed, by model) and breakdown: all usage, or one provider's. */
export interface SectionFigures extends UsageFigures {
  chartRows: TotalsRow[];
  breakdownRows: TotalsRow[];
  breakdownLatency: LatencyRow[];
  /** For a subscription: its breakdown rows within each limit's most recent window, by window key. */
  limitWindowRows?: Record<string, TotalsRow[]>;
}

/** One provider's details. */
export interface DetailSection extends SectionFigures {
  spec: SectionSpec;
}

export interface DashboardData {
  total: SectionFigures;
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
  /** The page shown, which scopes the latest calls to its item. */
  route: Route;
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
  /** Each subscription's usage scales, by its section key: one per limit window that can be estimated. */
  usageScales: Record<string, UsageScale[]> = {};
  /** The limit window each subscription's usage chart is against, once its viewer picked one. */
  usageWindows: Record<string, string> = {};
  /** The cards at the top, which answer for now and this month whatever the Details window or filter. */
  providers: ProviderCard[] | null = null;
  data: DashboardData | null = null;
  calls: StoredCall[] = [];
  /** How many calls match the page's item and filter, over every page. */
  callsTotal = 0;
  /** The page of calls shown, from 1. */
  callsPage = 1;
  callsPerPage: RowsPerPage = DEFAULT_ROWS_PER_PAGE;
  appNames: Record<string, string> = {};
  isLoading = false;
  isCollectorDown = false;
  isCatchingUp = false;
  isLive = false;
  errorMessage: string | null = null;
  expandedCallId: string | null = null;

  private generation = 0;
  private callsGeneration = 0;
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

  selectUsageWindow(sectionKey: string, windowKey: string): void {
    this.usageWindows = { ...this.usageWindows, [sectionKey]: windowKey };
    this.deps.redraw();
  }

  selectChartMetric(sectionKey: string, metric: ChartMetric): void {
    this.chartMetrics = { ...this.chartMetrics, [sectionKey]: metric };
    this.deps.redraw();
  }

  /** Filter the page to ``filter``, or clear the filter when it is the one already set. */
  toggleFilter(filter: Filter | null): void {
    this.filter =
      filter !== null && this.filter !== null && filterKey(filter) === filterKey(this.filter) ? null : filter;
    void this.refresh();
    this.showCallsPage(1);
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
      const [
        limits,
        monthRows,
        summaryRows,
        statusRows,
        chartRows,
        breakdownRows,
        totalLatency,
        totalBreakdownLatency,
        health,
      ] = await Promise.all([
        fetchLimits(new Date(now.getTime() - LIMITS_LOOKBACK_MS)),
        fetchTotals({ groupBy: ["provider", "billing_mode", "cost_provenance"], since: windowStart("month", now) }),
        fetchTotals({ groupBy: split(["cost_provenance"]), since }),
        fetchTotals({ groupBy: split(["status"]), since }),
        fetchTotals({ groupBy: split(["model"]), since, bucket }),
        fetchTotals({ groupBy: split(breakdownSpec(breakdown).fields), since }),
        fetchLatency(filterFields, since),
        fetchLatency(breakdownFields, since),
        fetchCollectorHealth(),
      ]);
      if (generation !== this.generation) return;
      const keep = <T extends { group: Record<string, string | null> }>(rows: T[]): T[] =>
        rows.filter((row) => matchesFilter(row.group, filter));
      const specs = detailSections(keep(summaryRows));
      const cards = providerCards(limits, monthRows, now);
      const calibrations = cards.flatMap((card) =>
        card.kind !== "subscription"
          ? []
          : card.windows.flatMap((window) => {
              const span = calibrationSpan(window);
              return span === null ? [] : [{ card, window, span }];
            }),
      );
      const [sectionLatency, calibrationRows, limitWindowRows] = await Promise.all([
        Promise.all(
          specs.map((spec) => {
            const only = { provider: [spec.provider], billing_mode: spec.billingModes };
            return Promise.all([fetchLatency(filterFields, since, only), fetchLatency(breakdownFields, since, only)]);
          }),
        ),
        Promise.all(
          calibrations.map(({ span }) =>
            fetchTotals({ groupBy: ["provider", "billing_mode"], since: span.since, until: span.until }),
          ),
        ),
        // Each limit's most recent window, up to its reset or now, for the breakdown's per-limit columns.
        Promise.all(
          calibrations.map(({ window, span }) =>
            fetchTotals({
              groupBy: withFilterFields([...breakdownSpec(breakdown).fields, ...SECTION_FIELDS], filter),
              since: span.since,
              until: window.readingResetsAt !== null && window.readingResetsAt < now ? window.readingResetsAt : now,
            }),
          ),
        ),
      ]);
      if (generation !== this.generation) return;
      const within = <T extends { group: Record<string, string | null> }>(rows: T[], spec: SectionSpec): T[] =>
        keep(rows).filter((row) => inSection(row.group, spec));
      this.providers = cards;
      const scales: Record<string, UsageScale[]> = {};
      calibrations.forEach(({ card, window, span }, index) => {
        const provider = card.sectionKey.slice("subscription:".length);
        const listPrice = calibrationRows[index]
          .filter((row) => row.group.provider === provider && row.group.billing_mode === "SUBSCRIPTION")
          .reduce((sum, row) => sum + (row.cost_usd === null ? 0 : Number(row.cost_usd)), 0);
        const rate = percentPerDollar(window.readingPercent ?? 0, listPrice);
        if (rate === null || window.readingResetsAt === null) return;
        scales[card.sectionKey] = [
          ...(scales[card.sectionKey] ?? []),
          {
            windowKey: window.key,
            label: window.label,
            percentPerDollar: rate,
            isFromEarlierWindow: window.isResetSinceReading,
            windowStart: span.since,
            resetsAt: window.readingResetsAt,
          },
        ];
      });
      this.usageScales = scales;
      this.data = {
        total: {
          summary: summarize(keep(summaryRows)),
          failed: failedShare(keep(statusRows)),
          latency: keep(totalLatency)[0] ?? null,
          chartRows: keep(chartRows),
          breakdownRows: keep(breakdownRows),
          breakdownLatency: keep(totalBreakdownLatency),
        },
        sections: specs.map((spec, index) => ({
          spec,
          summary: summarize(within(summaryRows, spec)),
          failed: failedShare(within(statusRows, spec)),
          latency: keep(sectionLatency[index][0])[0] ?? null,
          chartRows: within(chartRows, spec),
          breakdownRows: within(breakdownRows, spec),
          breakdownLatency: keep(sectionLatency[index][1]),
          limitWindowRows: Object.fromEntries(
            calibrations.flatMap(({ card, window }, calibration) =>
              card.sectionKey === spec.key ? [[window.key, within(limitWindowRows[calibration], spec)]] : [],
            ),
          ),
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

  /** Load the page of calls shown, for the current filter. */
  async loadCalls(): Promise<void> {
    const generation = ++this.callsGeneration;
    try {
      const answer = await fetchCalls({
        filters: this.callFilters(this.filter),
        limit: this.callsPerPage,
        offset: pageOffset(this.callsPage, this.callsPerPage),
      });
      if (generation !== this.callsGeneration) return;
      this.calls = answer.calls;
      this.callsTotal = answer.total;
      // Calls can leave between asks only through a rebuilt index, which can leave the page past the last one.
      const count = pageCount(answer.total, this.callsPerPage);
      if (this.callsPage > count) {
        this.showCallsPage(count);
        return;
      }
    } catch (error) {
      this.noteFailure(error, () => void this.loadCalls());
    }
    this.deps.redraw();
  }

  /** Show ``perPage`` calls to a page, on the page holding the first call shown before. */
  selectCallsPerPage(perPage: RowsPerPage): void {
    const page = pageHolding(pageOffset(this.callsPage, this.callsPerPage), perPage);
    this.callsPerPage = perPage;
    this.showCallsPage(page);
  }

  showCallsPage(page: number): void {
    this.callsPage = page;
    this.expandedCallId = null;
    void this.loadCalls();
  }

  /** Take one streamed call: show it if it matches the filter, and schedule a refetch of the totals. */
  receiveCall(call: ModelCall): void {
    const group = callGroup(call);
    if (matchesFilter(group, this.filter) && inScope(group, this.deps.route)) {
      this.callsTotal += 1;
      // Only the first page takes new calls in; a later one keeps the rows being read.
      if (this.callsPage === 1) this.addNewestCall({ sequence: 0, event: call });
    }
    this.scheduleEventRefresh();
    this.deps.redraw();
  }

  /** The calls filters for the page's item, narrowed by ``filter``. */
  private callFilters(filter: Filter | null): Record<string, readonly string[]> {
    return combinedFilters(scopeFilters(this.deps.route), filter?.values ?? null);
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

  /** Put a new call at the top of the first page, keeping the page to its length. */
  private addNewestCall(call: StoredCall): void {
    if (this.calls.some((known) => known.event.event_id === call.event.event_id)) return;
    this.calls = [call, ...this.calls]
      .sort((a, b) => Date.parse(b.event.ended_at) - Date.parse(a.event.ended_at))
      .slice(0, this.callsPerPage);
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
        this.fillGap();
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

  /** After a reconnect: the page of calls again, with any stored while the stream was down, then fresh totals. */
  private fillGap(): void {
    void this.loadCalls();
    void this.refresh();
  }
}
