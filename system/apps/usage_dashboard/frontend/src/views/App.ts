/**
 * The Usage page: the window picker, the tiles, the chart, the breakdown and the latest calls.
 */

import m from "mithril";

import { bannerClass } from "@imbue/workspace-ui/src/components/banner";
import { Button } from "@imbue/workspace-ui/src/components/Button";
import { SegmentedControl } from "@imbue/workspace-ui/src/components/segmentedControl";

import type { LatencyRow, StoredCall } from "../models/api";
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
import type { ChartMetric, DashboardData, DashboardModel } from "../models/dashboard";
import {
  formatCalls,
  formatCallTime,
  formatClock,
  formatCount,
  formatDollars,
  formatDuration,
  formatPercent,
} from "../models/format";
import { SeriesColors } from "../models/series";
import { BILLED_MODES, totalTokens } from "../models/summary";
import { WINDOWS, type WindowId } from "../models/windows";
import { UsageChart } from "./chart";

const CARD_CLASS = "rounded-lg border border-default bg-surface p-4";

function tile(label: string, value: string, details: m.Children, attrs: m.Attributes = {}): m.Vnode {
  return m("div", { class: `${CARD_CLASS} flex min-w-0 flex-col gap-1`, ...attrs }, [
    m("span", { class: "type-tag uppercase tracking-wide text-faint" }, label),
    m("span", { class: "type-heading-lg tabular-nums text-primary" }, value),
    m("div", { class: "type-helper text-secondary" }, details),
  ]);
}

function spendTile(data: DashboardData): m.Vnode {
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

function subscriptionTile(data: DashboardData): m.Vnode | null {
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

function tokensTile(data: DashboardData): m.Vnode {
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

function callsTile(data: DashboardData): m.Vnode {
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

function latencyTile(data: DashboardData): m.Vnode {
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

function breakdownSection(model: DashboardModel, data: DashboardData): m.Vnode {
  const lines = breakdownLines(data.breakdown, data.breakdownRows, data.breakdownLatency, model.appNames);
  const totalTokensAll = lines.reduce((sum, line) => sum + line.tokens, 0);
  const activeKey = model.filter === null ? null : filterKey(model.filter);
  return m("section", { class: `${CARD_CLASS} flex flex-col gap-3` }, [
    m("div", { class: "flex flex-wrap items-center justify-between gap-2" }, [
      m("h2", { class: "type-section text-primary" }, "Breakdown"),
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
                m(
                  "th",
                  { class: "py-1.5 pr-3 font-normal" },
                  BREAKDOWNS.find((spec) => spec.id === data.breakdown)?.label,
                ),
                m("th", { class: "py-1.5 pr-3 text-right font-normal" }, "Calls"),
                m("th", { class: "py-1.5 pr-3 text-right font-normal" }, "Tokens"),
                m("th", { class: "w-32 py-1.5 pr-3 font-normal" }, "Share"),
                m("th", { class: "py-1.5 pr-3 text-right font-normal" }, "Spend"),
                m("th", { class: "py-1.5 text-right font-normal" }, "p50"),
              ]),
            ]),
            m(
              "tbody",
              lines.map((line) => {
                const filter = filterOf(data.breakdown, line.group);
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
                    m("td", { class: "py-2 pr-3" }, [
                      m("div", { class: "flex items-center gap-2" }, [
                        m("div", { class: "h-1.5 flex-1 rounded-full bg-fill-hover" }, [
                          m("div", {
                            class: "h-1.5 rounded-full bg-(--series-1)",
                            style: { width: `${totalTokensAll === 0 ? 0 : (100 * line.tokens) / totalTokensAll}%` },
                          }),
                        ]),
                        m(
                          "span",
                          { class: "w-9 text-right type-tag tabular-nums text-faint" },
                          formatPercent(line.tokens, totalTokensAll),
                        ),
                      ]),
                    ]),
                    m("td", { class: "py-2 pr-3 text-right tabular-nums text-secondary" }, [
                      line.billedCalls === 0 ? "–" : formatDollars(line.spend),
                      line.listPrice === null
                        ? null
                        : m(
                            "div",
                            { class: "type-tag text-faint" },
                            `≈ ${formatDollars(line.listPrice)} subscription`,
                          ),
                    ]),
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
      "Click a row to show only its usage. Subscription usage is shown at list price, apart from spend.",
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

function callsSection(model: DashboardModel, now: Date): m.Vnode {
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
                m("th", { class: "py-1.5 pr-3 text-right font-normal" }, "Cost"),
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
                      m("td", { class: "py-1.5 pr-3 text-right tabular-nums text-secondary" }, callCost(call)),
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
                      m("td", { colspan: 7, class: "py-2" }, [
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
    model.hasOlderCalls
      ? m("div", [m(Button, { sm: true, onclick: () => void model.loadOlderCalls() }, "Show older calls")])
      : null,
  ]);
}

function header(model: DashboardModel, appNames: Record<string, string>): m.Vnode {
  const filter = model.filter;
  return m("header", { class: "flex flex-wrap items-center justify-between gap-3" }, [
    m("div", { class: "flex items-center gap-3" }, [
      m("h1", { class: "type-heading text-primary" }, "Usage"),
      m(
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
      ),
      filter === null
        ? null
        : m(
            "button",
            {
              type: "button",
              class:
                "filter-chip flex items-center gap-1 rounded-full border border-default px-2.5 py-0.5 type-helper text-primary hover:bg-fill-hover",
              title: "Show everything again",
              onclick: () => model.toggleFilter(null),
            },
            [
              `Only ${groupLabel(filter.breakdown, filter.values, appNames)}`,
              m("span", { class: "text-faint" }, " ×"),
            ],
          ),
    ]),
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

export interface AppAttrs {
  model: DashboardModel;
  now: () => Date;
}

export function App(): m.Component<AppAttrs> {
  const colors = new SeriesColors();
  return {
    view({ attrs: { model, now } }) {
      if (model.isVisitor) {
        return m("main", { class: "flex min-h-screen items-center justify-center p-6" }, [
          m(
            "p",
            { class: "visitor-notice type-body text-secondary" },
            "Usage is visible only to the workspace owner.",
          ),
        ]);
      }
      const data = model.data;
      const current = now();
      const metric: ChartMetric = model.chartMetric ?? (data !== null && data.summary.spend > 0 ? "spend" : "tokens");
      return m(
        "div",
        { class: "h-screen overflow-y-auto" },
        m("main", { class: "mx-auto flex max-w-6xl flex-col gap-4 px-4 py-4 sm:px-6" }, [
          header(model, model.appNames),
          banners(model),
          data === null
            ? m(
                "div",
                { class: "type-helper py-10 text-center text-faint" },
                model.isCollectorDown ? "" : "Loading usage…",
              )
            : m("div", { class: `flex flex-col gap-4 ${model.isCollectorDown ? "opacity-60" : ""}` }, [
                data.summary.calls === 0 && model.filter === null
                  ? m(
                      "div",
                      { class: `${CARD_CLASS} empty-window type-body text-secondary` },
                      data.windowId === "month"
                        ? "No model calls yet this month."
                        : "No model calls yet in this window. Try 7 days or this month.",
                    )
                  : [
                      m("div", { class: "grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-3" }, [
                        spendTile(data),
                        subscriptionTile(data),
                        tokensTile(data),
                        callsTile(data),
                        latencyTile(data),
                      ]),
                      m("section", { class: `${CARD_CLASS} flex flex-col gap-3` }, [
                        m("div", { class: "flex flex-wrap items-center justify-between gap-2" }, [
                          m(
                            "h2",
                            { class: "type-section text-primary" },
                            metric === "spend" ? "Spend by model" : "Tokens by model",
                          ),
                          m(SegmentedControl<ChartMetric>(), {
                            label: "Chart",
                            segments: [
                              { value: "spend", label: "Spend" },
                              { value: "tokens", label: "Tokens" },
                            ],
                            value: metric,
                            onSelect: (choice) => model.selectChartMetric(choice),
                          }),
                        ]),
                        m(UsageChart, { windowId: data.windowId, now: current, rows: data.chartRows, metric, colors }),
                      ]),
                      breakdownSection(model, data),
                    ],
                callsSection(model, current),
              ]),
        ]),
      );
    },
  };
}
