/**
 * The rings version of the Usage widget (app-widgets plan section 7.5). Collapsed, a pair of concentric rings per
 * subscription (the weekly limit outside, the 5-hour limit inside, each over a faint track) with the 5-hour figure in
 * the middle and the subscription's name beside it; while the pointer is over the widget the name gives way, in its
 * own place, to when each window resets, so the widget never changes size. The detail is drawn rather than left to a
 * native ``title`` tooltip, which not every host of the desktop shows. Expanded, a section per subscription headed by its name: the ring
 * pair beside a row per window, each with a dot in its ring's colour and the share used, and, while the pointer is
 * over the widget, when it resets; then the pay-as-you-go spend.
 */

import m from "mithril";
import type { LimitWindow } from "../models/providers";
import { resetText, ringFraction, widgetRings, widgetRows, windowName } from "../models/widget";
import type { LimitRow, RingPair, SpendRow, WidgetModel } from "../models/widget";
import { percentText, pillView, sectionHeading, spendSectionView, windowColour } from "./widgetParts";
import type { WindowRole } from "./widgetParts";

// The rings' drawing, in the units of its own view box: two circles about one centre, a stroke's width apart.
const RING_BOX = 40;
const RING_CENTRE = RING_BOX / 2;
const OUTER_RADIUS = 18;
const INNER_RADIUS = 13.5;
const RING_STROKE = 3;

const RING_OF_ROLE: Record<WindowRole, "inner" | "outer"> = { short: "inner", long: "outer" };

/** One ring: a faint full track, and over it, from twelve o'clock clockwise, the arc of the share used. */
function ringView(window: LimitWindow, radius: number, role: WindowRole): m.Vnode[] {
  const fraction = ringFraction(window);
  const circle = { cx: RING_CENTRE, cy: RING_CENTRE, r: radius, fill: "none", "stroke-width": RING_STROKE };
  const track = m("circle", { ...circle, stroke: "var(--widget-track)" });
  if (fraction === 0) return [track];
  const arc = m("circle", {
    ...circle,
    "data-ring": RING_OF_ROLE[role],
    "data-ring-level": window.level,
    stroke: windowColour(window, role),
    pathLength: 100,
    "stroke-dasharray": `${fraction * 100} 100`,
    "stroke-linecap": "round",
    transform: `rotate(-90 ${RING_CENTRE} ${RING_CENTRE})`,
  });
  return [track, arc];
}

/** A ring pair with the 5-hour figure in its middle. */
function ringsView(inner: LimitWindow, outer: LimitWindow | null, label: string): m.Vnode {
  return m("span", { class: "relative inline-flex size-10 shrink-0 items-center justify-center" }, [
    m(
      "svg",
      {
        viewBox: `0 0 ${RING_BOX} ${RING_BOX}`,
        class: "absolute inset-0 size-full",
        "aria-label": label,
        role: "img",
      },
      [...(outer === null ? [] : ringView(outer, OUTER_RADIUS, "long")), ...ringView(inner, INNER_RADIUS, "short")],
    ),
    m(
      "span",
      {
        "data-ring-figure": "",
        class: "relative text-[10px] leading-none font-semibold tabular-nums text-(--widget-text)",
      },
      percentText(inner),
    ),
  ]);
}

/** One line of a collapsed pair's hover detail: a window's short name and when it resets. */
function ringDetailLine(shortName: string, window: LimitWindow): m.Vnode {
  return m("span", { "data-ring-detail": shortName }, `${shortName} ${resetText(window)}`);
}

function ringPairView(pair: RingPair): m.Vnode {
  // The name and the detail share one grid cell, so it is as wide and tall as the larger of them at rest too.
  return m(
    "span",
    { key: pair.key, "data-widget-rings": pair.key, class: "flex items-center gap-1.5", title: pair.tooltip },
    [
      ringsView(pair.inner, pair.outer, pair.tooltip),
      m("span", { class: "grid items-center" }, [
        m(
          "span",
          {
            "data-ring-name": "",
            class:
              "[grid-area:1/1] text-[9px] leading-none font-semibold tracking-wider text-(--widget-muted) uppercase " +
              "transition-opacity group-hover:opacity-0",
          },
          pair.name,
        ),
        m(
          "span",
          {
            class:
              "[grid-area:1/1] flex flex-col gap-0.5 text-[9px] leading-tight whitespace-nowrap tabular-nums " +
              "text-(--widget-muted) opacity-0 transition-opacity group-hover:opacity-100",
          },
          [ringDetailLine("5h", pair.inner), pair.outer === null ? null : ringDetailLine("wk", pair.outer)],
        ),
      ]),
    ],
  );
}

function windowRowView(window: LimitWindow, role: WindowRole): m.Vnode {
  return m("div", { "data-widget-window": window.key, class: "flex items-center gap-1.5" }, [
    m("span", {
      class: "inline-block size-1.5 shrink-0 rounded-full",
      style: { background: windowColour(window, role) },
    }),
    m("span", { class: "shrink-0 text-(--widget-text)" }, windowName(window)),
    m(
      "span",
      {
        "data-widget-reset": "",
        class:
          "ml-auto min-w-0 truncate tabular-nums text-(--widget-faint) opacity-0 transition-opacity " +
          "group-hover:opacity-100",
      },
      resetText(window),
    ),
    m(
      "span",
      {
        "data-widget-percent": window.isResetSinceReading ? "reset" : window.level,
        class: "w-8 shrink-0 text-right font-semibold tabular-nums text-(--widget-text)",
      },
      percentText(window),
    ),
  ]);
}

function limitSectionView(row: LimitRow): m.Vnode {
  return m("div", { key: row.key, "data-widget-row": row.key, class: "flex flex-col gap-1.5", title: row.tooltip }, [
    sectionHeading(row.name),
    m("div", { class: "flex items-center gap-2.5" }, [
      ringsView(row.primary, row.secondary, row.tooltip),
      m("div", { class: "flex min-w-0 flex-1 flex-col gap-1" }, [
        windowRowView(row.primary, "short"),
        row.secondary === null ? null : windowRowView(row.secondary, "long"),
      ]),
    ]),
  ]);
}

export function ringsExpanded(model: WidgetModel): m.Children {
  const rows = widgetRows(model.cards ?? []);
  const limits = rows.filter((row): row is LimitRow => row.kind === "limit");
  const spends = rows.filter((row): row is SpendRow => row.kind === "spend");
  const sections: m.Vnode[] = limits.map(limitSectionView);
  const spend = spendSectionView(spends);
  if (spend !== null) sections.push(spend);
  return m("div", { class: "flex flex-col gap-3" }, sections);
}

export function ringsCollapsed(model: WidgetModel): m.Children {
  const cards = model.cards ?? [];
  const rings = widgetRings(cards);
  if (rings.length > 0) return m("span", { class: "flex items-start gap-3" }, rings.map(ringPairView));
  return pillView(cards);
}
