/**
 * The Usage page: the window picker, the tiles, the chart, the breakdown and the latest calls.
 */

import m from "mithril";

import { bannerClass } from "@imbue/workspace-ui/src/components/banner";
import { Button } from "@imbue/workspace-ui/src/components/Button";
import { inputClass } from "@imbue/workspace-ui/src/components/Input";
import { Dropdown } from "@imbue/workspace-ui/src/components/dropdown";
import { SegmentedControl } from "@imbue/workspace-ui/src/components/segmentedControl";

import type { LatencyRow, StoredCall, TotalsRow } from "../models/api";
import { WIDGET_VARIANTS, WIDGET_VARIANT_LABELS } from "../models/widgetVariant";
import type { WidgetVariant, WidgetVariantPicker } from "../models/widgetVariant";
import {
  BREAKDOWNS,
  type BreakdownId,
  billingModeLabel,
  breakdownLines,
  callGroup,
  filterKey,
  filterOf,
  groupLabel,
  modelLabel,
  sourceLabel,
} from "../models/breakdown";
import type { ChartMetric, DashboardData, DashboardModel, SectionFigures, UsageFigures } from "../models/dashboard";
import {
  formatCalls,
  formatCallTime,
  formatClock,
  formatCount,
  formatDollars,
  formatDuration,
  formatPercent,
} from "../models/format";
import {
  ROWS_PER_PAGE_CHOICES,
  type RowsPerPage,
  pageCount,
  pageNumbers,
  pageRange,
  typedPage,
} from "../models/callPages";
import { SeriesColors } from "../models/series";
import { BILLED_MODES, totalTokens } from "../models/summary";
import { type Route, pathOf } from "../models/routing";
import type { SectionKind } from "../models/sections";
import { type UsageScale, chosenScale, formatShare, limitShares, lineKey } from "../models/usageEstimate";
import { WINDOWS, type WindowId } from "../models/windows";
import { type ChartMarker, UsageChart } from "./chart";
import { providerCard, providerSection } from "./providerCards";

const CARD_CLASS = "rounded-lg border border-default bg-surface p-4";

function tile(label: string, value: string, details: m.Children, attrs: m.Attributes = {}): m.Vnode {
  return m("div", { class: `${CARD_CLASS} flex min-w-0 flex-col gap-1`, ...attrs }, [
    m("span", { class: "type-tag uppercase tracking-wide text-faint" }, label),
    m("span", { class: "type-heading-lg tabular-nums text-primary" }, value),
    m("div", { class: "type-helper text-secondary" }, details),
  ]);
}

function spendTile(data: UsageFigures): m.Vnode {
  const { summary } = data;
  const prefix = summary.isSpendEstimated ? "~" : "";
  const modeLines = BILLED_MODES.filter((mode) => summary.spendByMode[mode] !== undefined).map((mode) =>
    m("div", `${billingModeLabel(mode)} ${formatDollars(summary.spendByMode[mode] ?? 0)}`),
  );
  return tile(
    "Spend",
    `${prefix}${formatDollars(summary.spend)}`,
    [
      modeLines.length === 0 ? m("div", "Nothing billed") : modeLines,
      summary.isSpendEstimated ? m("div", { class: "text-faint" }, "~ includes costs estimated from tokens") : null,
      summary.unknownCostCalls > 0
        ? m(
            "div",
            { class: "text-warning", "data-unknown-cost": summary.unknownCostCalls },
            `+${formatCalls(summary.unknownCostCalls)} with unknown cost`,
          )
        : null,
    ],
    { "data-tile": "spend" },
  );
}

function subscriptionTile(data: UsageFigures): m.Vnode | null {
  const { summary } = data;
  if (summary.subscriptionCalls === 0) return null;
  return tile(
    "Subscription",
    summary.subscriptionListPrice === null ? "Unpriced" : `≈ ${formatDollars(summary.subscriptionListPrice)}`,
    [
      m("div", `${formatCalls(summary.subscriptionCalls)} at list price`),
      m("div", { class: "text-faint" }, "Covered by the subscription, not billed per call"),
    ],
    { "data-tile": "subscription" },
  );
}

function tokensTile(data: UsageFigures): m.Vnode {
  const { tokens } = data.summary;
  return tile(
    "Tokens",
    formatCount(totalTokens(tokens)),
    [
      m("div", `${formatCount(tokens.input)} in · ${formatCount(tokens.output)} out`),
      m("div", `${formatCount(tokens.cache_read)} cache read · ${formatCount(tokens.cache_write)} cache write`),
    ],
    { "data-tile": "tokens" },
  );
}

function callsTile(data: UsageFigures): m.Vnode {
  const { calls, failed } = data.failed;
  return tile(
    "Calls",
    formatCount(calls),
    failed === 0
      ? m("div", "None failed")
      : m("div", { class: "text-danger" }, `${formatPercent(failed, calls)} failed or rate-limited`),
    { "data-tile": "calls" },
  );
}

function latencyText(row: LatencyRow | null | undefined, which: "p50_ms" | "p95_ms"): string {
  const value = row?.[which];
  return value === null || value === undefined ? "–" : formatDuration(value);
}

function latencyTile(data: UsageFigures): m.Vnode {
  const row = data.latency;
  return tile(
    "Latency (p50)",
    latencyText(row, "p50_ms"),
    [
      m("div", `p95 ${latencyText(row, "p95_ms")}`),
      row !== null && row.untimed_calls > 0
        ? m("div", { class: "text-faint" }, `${formatCalls(row.untimed_calls)} without timing`)
        : null,
      row !== null && row.approximate_calls > 0
        ? m(
            "div",
            { class: "text-faint" },
            `${formatPercent(row.approximate_calls, row.timed_calls)} approximate (from session logs)`,
          )
        : null,
    ],
    { "data-tile": "latency" },
  );
}

/** A column for one limit: its scale and the breakdown rows within its most recent window. */
interface LimitColumn {
  scale: UsageScale;
  rows: readonly TotalsRow[];
}

/**
 * The usage columns the breakdown and the latest calls share on a page: a subscription's limit estimates, one
 * column per limit, or (with none) a money column, spend for the breakdown and cost for a call.
 */
type UsageColumns = readonly LimitColumn[];

function limitHeader(limit: LimitColumn, of: string): m.Vnode {
  return m(
    "th",
    {
      key: limit.scale.windowKey,
      class: "py-1.5 pr-3 text-right font-normal",
      title: `Estimated share of the ${limitName(limit.scale)} limit, ${of}`,
    },
    limit.scale.label.replace(" limit", ""),
  );
}

function breakdownSection(
  model: DashboardModel,
  breakdown: BreakdownId,
  section: SectionFigures,
  columns: UsageColumns,
): m.Vnode {
  const lines = breakdownLines(breakdown, section.breakdownRows, section.breakdownLatency, model.appNames);
  const limitColumns = columns.map((limit) => ({ ...limit, shares: limitShares(breakdown, limit.rows, limit.scale) }));
  const showsMoney = columns.length === 0;
  const activeKey = model.filter === null ? null : filterKey(model.filter);
  return m("div", { class: "flex flex-col gap-3" }, [
    m("div", { class: "flex flex-wrap items-center justify-between gap-2" }, [
      m("h3", { class: "type-tag uppercase tracking-wide text-faint" }, "Breakdown"),
      m(SegmentedControl<BreakdownId>(), {
        label: "Break usage down by",
        segments: BREAKDOWNS.map((spec) => ({ value: spec.id, label: spec.label })),
        value: model.breakdown,
        onSelect: (id) => model.selectBreakdown(id),
      }),
    ]),
    lines.length === 0
      ? m("div", { class: "type-helper text-faint" }, "No calls in this window.")
      : m("div", { class: "overflow-x-auto" }, [
          m("table", { class: "breakdown-table w-full border-collapse type-body" }, [
            m("thead", [
              m("tr", { class: "border-b border-default text-left type-tag uppercase tracking-wide text-faint" }, [
                m("th", { class: "py-1.5 pr-3 font-normal" }, BREAKDOWNS.find((spec) => spec.id === breakdown)?.label),
                m("th", { class: "py-1.5 pr-3 text-right font-normal" }, "Calls"),
                m("th", { class: "py-1.5 pr-3 text-right font-normal" }, "Tokens"),
                showsMoney ? m("th", { class: "py-1.5 pr-3 text-right font-normal" }, "Spend") : null,
                limitColumns.map((limit) => limitHeader(limit, "within its most recent window")),
                m("th", { class: "py-1.5 text-right font-normal" }, "p50"),
              ]),
            ]),
            m(
              "tbody",
              lines.map((line) => {
                const filter = filterOf(breakdown, line.group);
                const isActive = activeKey === filterKey(filter);
                return m(
                  "tr",
                  {
                    key: filterKey(filter),
                    class: `breakdown-row cursor-pointer border-b border-subtle hover:bg-fill-hover ${isActive ? "bg-fill-active" : ""}`,
                    "data-breakdown-row": line.label,
                    "aria-selected": isActive ? "true" : "false",
                    title: isActive ? "Show everything again" : `Show only ${line.label}`,
                    onclick: () => model.toggleFilter(filter),
                  },
                  [
                    m("td", { class: "max-w-64 truncate py-2 pr-3 text-primary" }, line.label),
                    m("td", { class: "py-2 pr-3 text-right tabular-nums text-secondary" }, formatCount(line.calls)),
                    m("td", { class: "py-2 pr-3 text-right tabular-nums text-secondary" }, formatCount(line.tokens)),
                    showsMoney
                      ? m("td", { class: "py-2 pr-3 text-right tabular-nums text-secondary" }, [
                          line.billedCalls === 0 ? "–" : formatDollars(line.spend),
                          line.listPrice === null
                            ? null
                            : m(
                                "div",
                                { class: "type-tag text-faint" },
                                `≈ ${formatDollars(line.listPrice)} subscription`,
                              ),
                        ])
                      : null,
                    limitColumns.map((limit) => {
                      const share = limit.shares.get(lineKey(line.group));
                      return m(
                        "td",
                        {
                          key: limit.scale.windowKey,
                          class: "breakdown-usage py-2 pr-3 text-right tabular-nums text-secondary",
                          "data-limit": limit.scale.windowKey,
                          title: `Estimated share of the ${limitName(limit.scale)} limit in its most recent window`,
                        },
                        share === undefined ? "–" : formatShare(share),
                      );
                    }),
                    m(
                      "td",
                      { class: "py-2 text-right tabular-nums text-secondary" },
                      latencyText(line.latency, "p50_ms"),
                    ),
                  ],
                );
              }),
            ),
          ]),
        ]),
    m(
      "p",
      { class: "type-helper text-faint" },
      showsMoney
        ? "Click a row to show only its usage. Subscription usage is shown at list price, apart from spend."
        : "Click a row to show only its usage. Each limit column is the row's estimated share of that limit within its most recent window.",
    ),
  ]);
}

function callCost(call: StoredCall): string {
  const { cost_usd: cost, billing_mode: mode, cost_provenance: provenance } = call.event;
  if (cost === null || cost === undefined) return "unknown";
  const amount = formatDollars(Number(cost));
  if (mode === "SUBSCRIPTION") return `≈ ${amount}`;
  return provenance === "ESTIMATED" ? `~${amount}` : amount;
}

function callTokens(call: StoredCall): number {
  const tokens = call.event.tokens;
  return (tokens.input ?? 0) + (tokens.output ?? 0) + (tokens.cache_read ?? 0) + (tokens.cache_write ?? 0);
}

/** Where the scale's limit reset: when its window started, and when the window ended once that has happened. */
function resetMarkers(scale: UsageScale, now: Date): ChartMarker[] {
  const label = `${capitalized(limitName(scale))} reset`;
  return [{ at: scale.windowStart, label }, ...(scale.resetsAt <= now ? [{ at: scale.resetsAt, label }] : [])];
}

function capitalized(text: string): string {
  return text.length === 0 ? text : text[0].toUpperCase() + text.slice(1);
}

/** "5-hour", "weekly": the limit a usage scale is against. */
function limitName(scale: UsageScale): string {
  return scale.label.replace(" limit", "").toLowerCase();
}

/** A subscription call's estimated share of a limit, from its list price; null for any other call. */
function callShare(call: StoredCall, scale: UsageScale): number | null {
  const { billing_mode: mode, cost_usd: cost } = call.event;
  if (mode !== "SUBSCRIPTION" || cost === null || cost === undefined) return null;
  return Number(cost) * scale.percentPerDollar;
}

function callsSection(model: DashboardModel, now: Date, columns: UsageColumns): m.Vnode {
  const showsMoney = columns.length === 0;
  const columnCount = 6 + (showsMoney ? 1 : columns.length);
  return m("section", { class: `${CARD_CLASS} flex flex-col gap-3` }, [
    m("div", { class: "flex items-center justify-between gap-2" }, [
      m("h2", { class: "type-section text-primary" }, "Latest calls"),
      m("span", { class: "type-helper text-faint" }, model.filter === null ? "All usage" : "Filtered"),
    ]),
    model.calls.length === 0
      ? m("div", { class: "type-helper text-faint" }, "No calls yet.")
      : m("div", { class: "overflow-x-auto" }, [
          m("table", { class: "calls-table w-full border-collapse type-body" }, [
            m("thead", [
              m("tr", { class: "border-b border-default text-left type-tag uppercase tracking-wide text-faint" }, [
                m("th", { class: "py-1.5 pr-3 font-normal" }, "Time"),
                m("th", { class: "py-1.5 pr-3 font-normal" }, "Source"),
                m("th", { class: "py-1.5 pr-3 font-normal" }, "Model"),
                m("th", { class: "py-1.5 pr-3 text-right font-normal" }, "Tokens"),
                showsMoney ? m("th", { class: "py-1.5 pr-3 text-right font-normal" }, "Cost") : null,
                columns.map((limit) => limitHeader(limit, "from the call's list price")),
                m("th", { class: "py-1.5 pr-3 text-right font-normal" }, "Duration"),
                m("th", { class: "py-1.5 font-normal" }, "Status"),
              ]),
            ]),
            m(
              "tbody",
              model.calls.flatMap((call) => {
                const event = call.event;
                const group = callGroup(event);
                const duration = Date.parse(event.ended_at) - Date.parse(event.started_at);
                const isExpanded = model.expandedCallId === event.event_id;
                const rows = [
                  m(
                    "tr",
                    {
                      key: event.event_id,
                      class: "call-row cursor-pointer border-b border-subtle hover:bg-fill-hover",
                      "data-call": event.event_id,
                      title: isExpanded ? "Hide the raw event" : "Show the raw event",
                      onclick: () => model.toggleCall(event.event_id),
                    },
                    [
                      m(
                        "td",
                        { class: "whitespace-nowrap py-1.5 pr-3 tabular-nums text-secondary" },
                        formatCallTime(new Date(event.ended_at), now),
                      ),
                      m(
                        "td",
                        { class: "max-w-48 truncate py-1.5 pr-3 text-primary" },
                        sourceLabel(group.origin_kind, group.origin_id, model.appNames),
                      ),
                      m("td", { class: "max-w-48 truncate py-1.5 pr-3 text-secondary" }, modelLabel(event.model)),
                      m(
                        "td",
                        { class: "py-1.5 pr-3 text-right tabular-nums text-secondary" },
                        formatCount(callTokens(call)),
                      ),
                      showsMoney
                        ? m("td", { class: "py-1.5 pr-3 text-right tabular-nums text-secondary" }, callCost(call))
                        : null,
                      columns.map((limit) => {
                        const share = callShare(call, limit.scale);
                        return m(
                          "td",
                          {
                            key: limit.scale.windowKey,
                            class: "call-usage py-1.5 pr-3 text-right tabular-nums text-secondary",
                            "data-limit": limit.scale.windowKey,
                          },
                          share === null ? "–" : formatShare(share),
                        );
                      }),
                      m(
                        "td",
                        { class: "py-1.5 pr-3 text-right tabular-nums text-secondary" },
                        duration > 0 ? formatDuration(duration) : "–",
                      ),
                      m(
                        "td",
                        { class: `py-1.5 ${event.status === "OK" ? "text-faint" : "text-danger"}` },
                        event.status.toLowerCase().replace("_", " "),
                      ),
                    ],
                  ),
                ];
                if (isExpanded) {
                  rows.push(
                    m("tr", { key: `${event.event_id}:raw`, class: "border-b border-subtle" }, [
                      m("td", { colspan: columnCount, class: "py-2" }, [
                        m(
                          "pre",
                          {
                            class:
                              "call-raw max-h-80 overflow-auto rounded-md bg-surface-secondary p-3 font-mono type-helper text-secondary",
                          },
                          JSON.stringify(event, null, 2),
                        ),
                      ]),
                    ]),
                  );
                }
                return rows;
              }),
            ),
          ]),
        ]),
    callPager(model),
  ]);
}

/**
 * The latest calls' pager, laid out as data tables usually are: the calls shown on the left; on the right the
 * page numbers, how many rows to a page, and a box to jump to a page. Nothing while every call fits on the
 * smallest page.
 */
function callPager(model: DashboardModel): m.Vnode | null {
  const perPage = model.callsPerPage;
  if (model.callsTotal <= ROWS_PER_PAGE_CHOICES[0]) return null;
  const count = pageCount(model.callsTotal, perPage);
  const current = model.callsPage;
  const [first, last] = pageRange(current, perPage, model.callsTotal);
  const pageButton = (page: number, label: string, attrs: Record<string, unknown>): m.Vnode =>
    m(
      Button,
      {
        variant: "ghost",
        extra: "min-w-[34px] px-2 tabular-nums",
        onclick: () => model.showCallsPage(page),
        ...attrs,
      },
      label,
    );
  const step = (page: number, label: string, title: string): m.Vnode =>
    pageButton(page, label, { disabled: page < 1 || page > count, title, "aria-label": title });
  return m("nav", { class: "calls-pages flex flex-wrap items-center justify-between gap-3", "aria-label": "Pages" }, [
    m(
      "span",
      { class: "calls-range type-helper tabular-nums text-secondary" },
      `${first.toLocaleString()}–${last.toLocaleString()} of ${model.callsTotal.toLocaleString()} calls`,
    ),
    m("div", { class: "flex flex-wrap items-center justify-end gap-x-4 gap-y-2" }, [
      count === 1
        ? null
        : m("div", { class: "flex items-center gap-1" }, [
            step(current - 1, "‹", "Previous page"),
            pageNumbers(current, count).map((item, index) =>
              item === "gap"
                ? m("span", { key: `gap${index}`, class: "min-w-[34px] text-center text-faint" }, "…")
                : pageButton(item, String(item), {
                    key: item,
                    selected: item === current,
                    "aria-current": item === current ? "page" : undefined,
                    "aria-label": `Page ${item}`,
                    "data-page": item,
                  }),
            ),
            step(current + 1, "›", "Next page"),
          ]),
      m("div", { class: "calls-per-page w-28" }, [
        m(Dropdown<string>, {
          options: ROWS_PER_PAGE_CHOICES.map((choice) => ({ value: String(choice), label: `${choice} / page` })),
          value: String(perPage),
          placeholder: `${perPage} / page`,
          "aria-label": "Rows per page",
          onSelect: (value: string) => model.selectCallsPerPage(Number(value) as RowsPerPage),
        }),
      ]),
      count === 1
        ? null
        : m("label", { class: "flex items-center gap-2 whitespace-nowrap type-helper text-secondary" }, [
            "Go to",
            m("div", { class: "w-16" }, [
              m("input", {
                class: inputClass({ extra: "calls-go-to text-center tabular-nums" }),
                type: "text",
                inputmode: "numeric",
                "aria-label": "Go to page",
                onkeydown: (event: KeyboardEvent) => {
                  if (event.key !== "Enter") return;
                  const field = event.target as HTMLInputElement;
                  const page = typedPage(field.value, count);
                  field.value = "";
                  if (page !== null) model.showCallsPage(page);
                },
              }),
            ]),
          ]),
    ]),
  ]);
}

function liveIndicator(model: DashboardModel): m.Vnode {
  return m(
    "span",
    {
      class: `live-indicator flex items-center gap-1.5 type-helper ${model.isLive ? "text-secondary" : "text-faint"}`,
      "data-live": model.isLive ? "true" : "false",
    },
    [
      m("span", {
        class: `inline-block size-2 rounded-full ${model.isLive ? "bg-(--color-success)" : "bg-(--color-faint)"}`,
      }),
      model.isLive ? "Live" : "Reconnecting",
    ],
  );
}

/** What the details below answer for: their window, and the filter a breakdown row set. */
function detailsControls(model: DashboardModel, appNames: Record<string, string>): m.Vnode {
  const filter = model.filter;
  return m("div", { class: "flex flex-wrap items-center justify-between gap-3" }, [
    filter === null
      ? m("span")
      : m(
          "button",
          {
            type: "button",
            class:
              "filter-chip flex items-center gap-1 rounded-full border border-default px-2.5 py-0.5 type-helper text-primary hover:bg-fill-hover",
            title: "Show everything again",
            onclick: () => model.toggleFilter(null),
          },
          [`Only ${groupLabel(filter.breakdown, filter.values, appNames)}`, m("span", { class: "text-faint" }, " ×")],
        ),
    m(SegmentedControl<WindowId>(), {
      label: "Time window",
      segments: WINDOWS.map((spec) => ({ value: spec.id, label: spec.label })),
      value: model.windowId,
      onSelect: (id) => model.selectWindow(id),
    }),
  ]);
}

function banners(model: DashboardModel): m.Children {
  return [
    model.isCollectorDown
      ? m(
          "div",
          { class: `${bannerClass("collector-down-banner", "warning")} rounded-md border` },
          model.data === null
            ? "The usage collector isn't responding. Retrying…"
            : `The usage collector isn't responding. Showing data from ${formatClock(model.data.loadedAt)}.`,
        )
      : null,
    model.isCatchingUp && !model.isCollectorDown
      ? m(
          "div",
          { class: `${bannerClass("catching-up-banner", "neutral")} rounded-md border` },
          "Still indexing past usage, so totals may be incomplete.",
        )
      : null,
    model.errorMessage === null
      ? null
      : m("div", { class: `${bannerClass("error-banner", "warning")} rounded-md border` }, model.errorMessage),
  ];
}

/** A set of calls' figures: their tiles, their usage over the window by model, and their breakdown. */
function figuresView(
  model: DashboardModel,
  data: DashboardData,
  figures: SectionFigures,
  kind: "all" | SectionKind,
  chartKey: string,
  now: Date,
  colors: SeriesColors,
  columns: UsageColumns,
): m.Children {
  const isSubscription = kind === "subscription";
  const scales = isSubscription ? (model.usageScales[chartKey] ?? []) : [];
  const scale = chosenScale(scales, model.usageWindows[chartKey]);
  // A subscription's calls are not billed per call, so its chart is tokens or their estimated share of a limit.
  const choices: { value: ChartMetric; label: string }[] = isSubscription
    ? [
        ...(scale === undefined ? [] : [{ value: "usage" as const, label: "Usage" }]),
        { value: "tokens", label: "Tokens" },
      ]
    : [
        { value: "spend", label: "Spend" },
        { value: "tokens", label: "Tokens" },
      ];
  const picked = model.chartMetrics[chartKey];
  const metric: ChartMetric =
    picked !== undefined && choices.some((choice) => choice.value === picked)
      ? picked
      : isSubscription
        ? (choices[0]?.value ?? "tokens")
        : figures.summary.spend > 0
          ? "spend"
          : "tokens";
  const heading =
    metric === "usage" && scale !== undefined
      ? `Usage by model · estimated % of ${scale.label.replace(" limit", "").toLowerCase()} limit`
      : metric === "spend"
        ? "Spend by model"
        : "Tokens by model";
  const tiles =
    kind === "all"
      ? [spendTile(figures), subscriptionTile(figures), tokensTile(figures), callsTile(figures), latencyTile(figures)]
      : [
          isSubscription ? subscriptionTile(figures) : spendTile(figures),
          tokensTile(figures),
          callsTile(figures),
          latencyTile(figures),
        ];
  return [
    m("div", { class: "grid grid-cols-[repeat(auto-fit,minmax(140px,1fr))] gap-3" }, tiles),
    m("section", { class: `${CARD_CLASS} flex flex-col gap-3` }, [
      m("div", { class: "flex flex-wrap items-center justify-between gap-2" }, [
        m("h3", { class: "type-tag uppercase tracking-wide text-faint" }, heading),
        m("div", { class: "flex flex-wrap items-center gap-2" }, [
          metric === "usage" && scales.length > 1
            ? m(SegmentedControl<string>(), {
                label: "Limit",
                segments: scales.map((candidate) => ({
                  value: candidate.windowKey,
                  label: candidate.label.replace(" limit", ""),
                })),
                value: scale?.windowKey ?? "",
                onSelect: (windowKey) => model.selectUsageWindow(chartKey, windowKey),
              })
            : null,
          choices.length > 1
            ? m(SegmentedControl<ChartMetric>(), {
                label: "Chart",
                segments: choices,
                value: metric,
                onSelect: (choice) => model.selectChartMetric(chartKey, choice),
              })
            : null,
        ]),
      ]),
      m(UsageChart, {
        windowId: data.windowId,
        now,
        rows: figures.chartRows,
        metric,
        colors,
        percentPerDollar: scale?.percentPerDollar,
        markers: scale === undefined ? [] : resetMarkers(scale, now),
        markerLegend: scale === undefined ? undefined : `${capitalized(limitName(scale))} reset`,
      }),
      metric === "usage" && scale !== undefined
        ? m(
            "p",
            { class: "usage-estimate-note type-helper text-faint" },
            scale.isFromEarlierWindow
              ? `Estimated at the rate of the ${limitName(scale)} window that reset at ${formatClock(scale.resetsAt)}: each model's tokens are priced at API rates.`
              : "Estimated: each model's tokens are priced at API rates, then scaled so the limit window adds up to its last reading.",
          )
        : null,
    ]),
    m("section", { class: CARD_CLASS }, breakdownSection(model, data.breakdown, figures, columns)),
  ];
}

function windowPicker(model: DashboardModel): m.Children {
  return m(SegmentedControl<WindowId>(), {
    label: "Time window",
    segments: WINDOWS.map((spec) => ({ value: spec.id, label: spec.label })),
    value: model.windowId,
    onSelect: (id) => model.selectWindow(id),
  });
}

/** The workspace's pick of widget version, saved by the Usage app and shown by its widget at once. */
function widgetStylePicker(picker: WidgetVariantPicker): m.Children {
  if (picker.variant === null) return null;
  return m("div", { class: "widget-style ml-auto flex items-center gap-2" }, [
    picker.errorMessage === null
      ? null
      : m("span", { class: "type-helper text-danger", role: "alert" }, picker.errorMessage),
    m("span", { class: "type-helper text-secondary" }, "Widget"),
    m("div", { class: "w-24" }, [
      m(Dropdown<WidgetVariant>, {
        options: WIDGET_VARIANTS.map((variant) => ({ value: variant, label: WIDGET_VARIANT_LABELS[variant] })),
        value: picker.variant,
        placeholder: WIDGET_VARIANT_LABELS[picker.variant],
        "aria-label": "Widget style",
        onSelect: (variant: WidgetVariant) => void picker.select(variant),
      }),
    ]),
  ]);
}

function pageHeader(model: DashboardModel, picker: WidgetVariantPicker, back: boolean): m.Vnode {
  return m("header", { class: "flex flex-wrap items-center gap-3" }, [
    back
      ? m(
          "a",
          {
            href: pathOf({ page: "home" }),
            class: "back-link type-body text-secondary no-underline hover:text-primary",
          },
          "‹ Back",
        )
      : null,
    m("h1", { class: "type-heading text-primary" }, "Usage"),
    liveIndicator(model),
    widgetStylePicker(picker),
  ]);
}

/** The home page: one card per provider in use, then the Total row, which opens all usage. */
function homePage(model: DashboardModel, picker: WidgetVariantPicker, now: Date): m.Children {
  const data = model.data;
  return [
    pageHeader(model, picker, false),
    banners(model),
    m("div", { class: model.isCollectorDown ? "opacity-60" : "" }, providerSection(model.providers, now)),
    m(
      "section",
      { class: `total-row flex flex-col gap-2 ${model.isCollectorDown ? "opacity-60" : ""}`, "data-section": "total" },
      [
        m("div", { class: "flex flex-wrap items-center justify-between gap-3" }, [
          m("div", { class: "flex items-baseline gap-3" }, [
            m("h2", { class: "type-section text-primary" }, "Total"),
            m(
              "a",
              { href: pathOf({ page: "all" }), class: "all-link type-helper text-secondary hover:text-primary" },
              "See all usage ›",
            ),
          ]),
          windowPicker(model),
        ]),
        data === null
          ? m(
              "div",
              { class: "type-helper py-6 text-center text-faint" },
              model.isCollectorDown ? "" : "Loading usage…",
            )
          : m("div", { class: "grid grid-cols-[repeat(auto-fit,minmax(140px,1fr))] gap-3" }, [
              spendTile(data.total),
              subscriptionTile(data.total),
              tokensTile(data.total),
              callsTile(data.total),
              latencyTile(data.total),
            ]),
      ],
    ),
  ];
}

interface NavItem {
  route: Route;
  key: string;
  title: string;
  note: string;
}

/** The detail page's list: the providers in the order of the home page's cards, then any other with calls. */
function navItems(model: DashboardModel): NavItem[] {
  const items: NavItem[] = [];
  for (const card of model.providers ?? []) {
    const note =
      card.kind === "subscription"
        ? card.windows
            .map(
              (window) =>
                `${window.label.replace(" limit", "")} ${window.usedPercent === null ? "–" : `${Math.round(window.usedPercent)}%`}`,
            )
            .join(" · ")
        : `${card.isEstimated ? "~" : ""}${formatDollars(card.spend)} this month`;
    items.push({ route: { page: "item", key: card.sectionKey }, key: card.sectionKey, title: card.title, note });
  }
  for (const section of model.data?.sections ?? []) {
    if (items.some((item) => item.key === section.spec.key)) continue;
    items.push({
      route: { page: "item", key: section.spec.key },
      key: section.spec.key,
      title: section.spec.title,
      note: "",
    });
  }
  return items;
}

/** A detail page: the list of providers, and the chosen one's limits, figures and latest calls. */
function detailPage(
  model: DashboardModel,
  picker: WidgetVariantPicker,
  route: Route,
  now: Date,
  colors: SeriesColors,
): m.Children {
  const data = model.data;
  const selectedKey = route.page === "item" ? route.key : "all";
  const items = navItems(model);
  const selected = items.find((item) => item.key === selectedKey);
  const card = (model.providers ?? []).find((candidate) => candidate.sectionKey === selectedKey);
  const section = data?.sections.find((candidate) => candidate.spec.key === selectedKey);
  const kind: "all" | SectionKind =
    route.page === "item" ? (selectedKey.startsWith("subscription:") ? "subscription" : "spend") : "all";
  const figures = route.page === "all" ? data?.total : section;
  // A subscription's page measures both tables against its limits; any other page in money.
  const columns: UsageColumns =
    kind === "subscription"
      ? (model.usageScales[selectedKey] ?? []).flatMap((scale) => {
          const rows = section?.limitWindowRows?.[scale.windowKey];
          return rows === undefined ? [] : [{ scale, rows }];
        })
      : [];
  return [
    pageHeader(model, picker, true),
    banners(model),
    m("div", { class: "detail-layout grid gap-4 md:grid-cols-[15rem_minmax(0,1fr)]" }, [
      m(
        "nav",
        { class: "detail-nav flex gap-1 overflow-x-auto md:flex-col md:overflow-visible", "aria-label": "Providers" },
        items.map((item) => {
          const isSelected = item.key === selectedKey;
          return m(
            "a",
            {
              key: item.key,
              href: pathOf(item.route),
              class: `nav-item flex shrink-0 flex-col rounded-md px-3 py-2 no-underline ${isSelected ? "bg-fill-active" : "hover:bg-fill-hover"}`,
              "aria-current": isSelected ? "page" : undefined,
              "data-nav": item.key,
            },
            [
              m(
                "span",
                { class: `type-body ${isSelected ? "font-semibold text-primary" : "text-primary"}` },
                item.title,
              ),
              item.note === "" ? null : m("span", { class: "type-helper text-faint" }, item.note),
            ],
          );
        }),
      ),
      m("div", { class: `detail-content flex min-w-0 flex-col gap-4 ${model.isCollectorDown ? "opacity-60" : ""}` }, [
        // A card names its provider itself; without one the item needs a heading.
        card === undefined
          ? m(
              "h2",
              { class: "type-heading text-primary" },
              selected?.title ?? (route.page === "all" ? "All usage" : "Unknown provider"),
            )
          : null,
        card === undefined ? null : providerCard(card, now),
        detailsControls(model, model.appNames),
        data === null
          ? m(
              "div",
              { class: "type-helper py-10 text-center text-faint" },
              model.isCollectorDown ? "" : "Loading usage…",
            )
          : figures === undefined || figures.summary.calls === 0
            ? m(
                "div",
                { class: `${CARD_CLASS} empty-window type-body text-secondary` },
                data.windowId === "month"
                  ? "No calls this month."
                  : "No calls in this window. Try 7 days or this month.",
              )
            : figuresView(model, data, figures, kind, selectedKey, now, colors, columns),
        callsSection(model, now, columns),
      ]),
    ]),
  ];
}

export interface AppAttrs {
  model: DashboardModel;
  widgetStyle: WidgetVariantPicker;
  route: Route;
  now: () => Date;
}

export function App(): m.Component<AppAttrs> {
  const colors = new SeriesColors();
  return {
    view({ attrs: { model, widgetStyle, route, now } }) {
      const current = now();
      return m(
        "div",
        { class: "h-screen overflow-y-auto" },
        m(
          "main",
          { class: "mx-auto flex max-w-6xl flex-col gap-4 px-4 py-4 sm:px-6" },
          route.page === "home"
            ? homePage(model, widgetStyle, current)
            : detailPage(model, widgetStyle, route, current, colors),
        ),
      );
    },
  };
}
