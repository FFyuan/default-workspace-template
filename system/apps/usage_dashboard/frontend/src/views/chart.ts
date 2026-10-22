/**
 * The usage chart: one bar per minute, hour or day of the window, stacked by model, with a legend and a tooltip
 * per bar. Bars are plain SVG; the axis labels are HTML beside it so they stay legible at any width.
 */

import m from "mithril";

import type { TotalsRow } from "../models/api";
import { modelLabel } from "../models/breakdown";
import type { ChartMetric } from "../models/dashboard";
import { formatCount, formatDollars } from "../models/format";
import { OTHER_SERIES, type SeriesColors, seriesOf } from "../models/series";
import { BILLED_MODES } from "../models/summary";
import { totalTokens } from "../models/summary";
import { type WindowId, barLabel, binRows } from "../models/windows";

const VIEW_WIDTH = 720;
const VIEW_HEIGHT = 180;
const SEGMENT_GAP = 2;
const BAR_RADIUS = 4;

function valueOf(metric: ChartMetric): (row: TotalsRow) => number {
  if (metric === "tokens") return (row) => totalTokens(row.tokens);
  return (row) =>
    (BILLED_MODES as readonly string[]).includes(row.group.billing_mode ?? "") && row.cost_usd !== null
      ? Number(row.cost_usd)
      : 0;
}

export function formatMetric(metric: ChartMetric, value: number): string {
  return metric === "spend" ? formatDollars(value) : formatCount(value);
}

function seriesColor(slot: number | null): string {
  return slot === null ? "var(--series-other)" : `var(--series-${slot})`;
}

export interface ChartAttrs {
  windowId: WindowId;
  now: Date;
  rows: readonly TotalsRow[];
  metric: ChartMetric;
  colors: SeriesColors;
}

export function UsageChart(): m.Component<ChartAttrs> {
  let hovered: number | null = null;
  return {
    view({ attrs: { windowId, now, rows, metric, colors } }) {
      const value = valueOf(metric);
      const totalsByModel = new Map<string, number>();
      for (const row of rows) {
        const model = modelLabel(row.group.model ?? null);
        totalsByModel.set(model, (totalsByModel.get(model) ?? 0) + value(row));
      }
      const ranked = [...totalsByModel.entries()]
        .filter(([, total]) => total > 0)
        .sort((a, b) => b[1] - a[1])
        .map(([model]) => model);
      const { shown, slotOf } = colors.assign(ranked);
      const order = [...shown, ...(ranked.some((model) => !shown.includes(model)) ? [OTHER_SERIES] : [])];
      const { starts, values } = binRows(
        windowId,
        now,
        rows,
        (row) => seriesOf(modelLabel(row.group.model ?? null), shown),
        value,
      );
      const barTotals = values.map((bar) => [...bar.values()].reduce((sum, amount) => sum + amount, 0));
      const peak = Math.max(0, ...barTotals);
      if (peak === 0) {
        return m(
          "div",
          { class: "chart-empty type-helper py-10 text-center text-faint" },
          "Nothing to chart in this window.",
        );
      }
      const slotWidth = VIEW_WIDTH / starts.length;
      const barWidth = Math.max(2, slotWidth - SEGMENT_GAP * 2);
      const scale = (amount: number): number => (amount / peak) * (VIEW_HEIGHT - 4);
      const hoveredBar = hovered !== null && hovered < starts.length ? hovered : null;

      return m("div", { class: "usage-chart flex flex-col gap-2" }, [
        m("div", { class: "relative" }, [
          m(
            "div",
            { class: "pointer-events-none absolute top-0 left-0 type-tag text-faint" },
            formatMetric(metric, peak),
          ),
          m(
            "svg",
            {
              viewBox: `0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`,
              preserveAspectRatio: "none",
              class: "block h-44 w-full",
              role: "img",
              "aria-label": `${metric === "spend" ? "Spend" : "Tokens"} over the window, by model`,
              onmouseleave: () => (hovered = null),
            },
            [
              m("line", {
                x1: 0,
                x2: VIEW_WIDTH,
                y1: VIEW_HEIGHT - 0.5,
                y2: VIEW_HEIGHT - 0.5,
                class: "stroke-(--color-subtle)",
              }),
              starts.map((_, index) => {
                let top = VIEW_HEIGHT;
                const segments = order
                  .map((series) => ({ series, amount: values[index].get(series) ?? 0 }))
                  .filter((segment) => segment.amount > 0);
                const x = index * slotWidth + (slotWidth - barWidth) / 2;
                return m(
                  "g",
                  { key: index, "data-bar": index, opacity: hoveredBar === null || hoveredBar === index ? 1 : 0.55 },
                  [
                    segments.map((segment, position) => {
                      const height = Math.max(1, scale(segment.amount) - (position > 0 ? SEGMENT_GAP : 0));
                      top -= height + (position > 0 ? SEGMENT_GAP : 0);
                      const isTop = position === segments.length - 1;
                      return m("rect", {
                        x,
                        y: top,
                        width: barWidth,
                        height,
                        rx: isTop ? Math.min(BAR_RADIUS, barWidth / 2) : 0,
                        fill: seriesColor(segment.series === OTHER_SERIES ? null : slotOf(segment.series)),
                      });
                    }),
                    m("rect", {
                      x: index * slotWidth,
                      y: 0,
                      width: slotWidth,
                      height: VIEW_HEIGHT,
                      fill: "transparent",
                      onmouseenter: () => (hovered = index),
                    }),
                  ],
                );
              }),
            ],
          ),
          hoveredBar === null
            ? null
            : m(
                "div",
                {
                  class:
                    "chart-tooltip pointer-events-none absolute top-2 z-10 min-w-40 rounded-md border border-default " +
                    "bg-surface px-2.5 py-2 type-helper text-primary shadow-sm",
                  style:
                    hoveredBar < starts.length / 2
                      ? { left: `${((hoveredBar + 1) / starts.length) * 100}%` }
                      : { right: `${(1 - hoveredBar / starts.length) * 100}%` },
                },
                [
                  m("div", { class: "mb-1 font-semibold" }, barLabel(windowId, starts[hoveredBar])),
                  order
                    .filter((series) => (values[hoveredBar].get(series) ?? 0) > 0)
                    .map((series) =>
                      m("div", { class: "flex items-center justify-between gap-3" }, [
                        m("span", { class: "flex items-center gap-1.5" }, [
                          m("span", {
                            class: "inline-block size-2 rounded-full",
                            style: { background: seriesColor(series === OTHER_SERIES ? null : slotOf(series)) },
                          }),
                          series,
                        ]),
                        m(
                          "span",
                          { class: "tabular-nums" },
                          formatMetric(metric, values[hoveredBar].get(series) ?? 0),
                        ),
                      ]),
                    ),
                  m("div", { class: "mt-1 flex justify-between border-t border-subtle pt-1 text-secondary" }, [
                    m("span", "Total"),
                    m("span", { class: "tabular-nums" }, formatMetric(metric, barTotals[hoveredBar])),
                  ]),
                ],
              ),
        ]),
        m("div", { class: "flex justify-between type-tag text-faint" }, [
          m("span", barLabel(windowId, starts[0])),
          m("span", barLabel(windowId, starts[starts.length - 1])),
        ]),
        m(
          "div",
          { class: "chart-legend flex flex-wrap gap-x-4 gap-y-1 type-helper text-secondary" },
          order.map((series) =>
            m("span", { class: "flex items-center gap-1.5" }, [
              m("span", {
                class: "inline-block size-2.5 rounded-sm",
                style: { background: seriesColor(series === OTHER_SERIES ? null : slotOf(series)) },
              }),
              series,
            ]),
          ),
        ),
      ]);
    },
  };
}
