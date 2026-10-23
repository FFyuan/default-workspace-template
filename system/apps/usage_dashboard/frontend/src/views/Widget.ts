/**
 * The Usage widget's view (app-widgets plan section 7), drawn on the shell's dark widget panel in the manner of a
 * system monitor: the whole widget is one link to the Usage page, opened in a window of its own
 * (``target="_blank"``, which the shell's link rule turns into raising the Usage window).
 *
 * Collapsed, a pair of concentric rings per subscription (the weekly limit outside, the 5-hour limit inside, each
 * over a faint track) with the 5-hour figure in the middle and the subscription's name beneath, or with no
 * subscription one figure of the month's spend. Expanded, a section per subscription headed by its name: the ring
 * pair beside a row per window, each with a dot in its ring's colour, when it resets, and the share used; then a
 * row per pay-as-you-go provider's spend. A ring is its window's hue while comfortable and the level's colour as it
 * nears the cap. While the collector indexes its first history the widget says so rather than show partial totals,
 * and while the stream is down it keeps the last figures, dimmed. Hover detail is each section's and each ring
 * pair's ``title``: a drawn tooltip would be clipped by the widget's small frame.
 */

import m from "mithril";
import type { WidgetMode } from "@imbue/workspace-ui/src/app_contract";
import type { LimitWindow } from "../models/providers";
import { resetText, ringFraction, widgetPill, widgetRings, widgetRows, windowName } from "../models/widget";
import type { LimitRow, RingPair, SpendRow, WidgetModel } from "../models/widget";

type RingRole = "inner" | "outer";

// A comfortable window keeps its ring's own hue; a high or critical one takes the level's colour.
const ROLE_COLOUR: Record<RingRole, string> = { inner: "var(--widget-short)", outer: "var(--widget-long)" };

function windowColour(window: LimitWindow, role: RingRole): string {
  if (window.level === "critical") return "var(--widget-critical)";
  if (window.level === "high") return "var(--widget-high)";
  return ROLE_COLOUR[role];
}

// The rings' drawing, in the units of its own view box: two circles about one centre, a stroke's width apart.
const RING_BOX = 40;
const RING_CENTRE = RING_BOX / 2;
const OUTER_RADIUS = 18;
const INNER_RADIUS = 13.5;
const RING_STROKE = 3;

/** One ring: a faint full track, and over it, from twelve o'clock clockwise, the arc of the share used. */
function ringView(window: LimitWindow, radius: number, role: RingRole): m.Vnode[] {
  const fraction = ringFraction(window);
  const circle = { cx: RING_CENTRE, cy: RING_CENTRE, r: radius, fill: "none", "stroke-width": RING_STROKE };
  const track = m("circle", { ...circle, stroke: "var(--widget-track)" });
  if (fraction === 0) return [track];
  const arc = m("circle", {
    ...circle,
    "data-ring": role,
    "data-ring-level": window.level,
    stroke: windowColour(window, role),
    pathLength: 100,
    "stroke-dasharray": `${fraction * 100} 100`,
    "stroke-linecap": "round",
    transform: `rotate(-90 ${RING_CENTRE} ${RING_CENTRE})`,
  });
  return [track, arc];
}

function percentText(window: LimitWindow): string {
  return window.isResetSinceReading || window.usedPercent === null ? "—" : `${Math.round(window.usedPercent)}%`;
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
      [...(outer === null ? [] : ringView(outer, OUTER_RADIUS, "outer")), ...ringView(inner, INNER_RADIUS, "inner")],
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

function ringPairView(pair: RingPair): m.Vnode {
  return m(
    "span",
    {
      key: pair.key,
      "data-widget-rings": pair.key,
      class: "flex flex-col items-center gap-1",
      title: pair.tooltip,
    },
    [
      ringsView(pair.inner, pair.outer, pair.tooltip),
      m(
        "span",
        {
          "data-ring-name": "",
          class: "text-[9px] leading-none font-semibold tracking-wider text-(--widget-muted) uppercase",
        },
        pair.name,
      ),
    ],
  );
}

function sectionHeading(name: string): m.Vnode {
  return m(
    "span",
    { class: "text-[10px] leading-none font-semibold tracking-wider text-(--widget-heading) uppercase" },
    name,
  );
}

function windowRowView(window: LimitWindow, role: RingRole): m.Vnode {
  return m("div", { "data-widget-window": window.key, class: "flex items-center gap-1.5" }, [
    m("span", {
      class: "inline-block size-1.5 shrink-0 rounded-full",
      style: { background: windowColour(window, role) },
    }),
    m("span", { class: "shrink-0 text-(--widget-text)" }, windowName(window)),
    m(
      "span",
      { "data-widget-reset": "", class: "ml-auto min-w-0 truncate tabular-nums text-(--widget-faint)" },
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
        windowRowView(row.primary, "inner"),
        row.secondary === null ? null : windowRowView(row.secondary, "outer"),
      ]),
    ]),
  ]);
}

function spendRowView(row: SpendRow): m.Vnode {
  return m(
    "div",
    { key: row.key, "data-widget-row": row.key, class: "flex items-center gap-1.5", title: row.tooltip },
    [
      m("span", { class: "inline-block size-1.5 shrink-0 rounded-full bg-(--widget-spend)" }),
      m("span", { class: "truncate text-(--widget-text)" }, row.name),
      m("span", { class: "ml-auto font-semibold tabular-nums text-(--widget-text)" }, row.spend),
    ],
  );
}

function expandedView(model: WidgetModel): m.Children {
  const rows = widgetRows(model.cards ?? []);
  const limits = rows.filter((row): row is LimitRow => row.kind === "limit");
  const spends = rows.filter((row): row is SpendRow => row.kind === "spend");
  const sections = limits.map(limitSectionView);
  if (spends.length > 0) {
    sections.push(
      m("div", { key: "spend", class: "flex flex-col gap-1" }, [
        sectionHeading("API this month"),
        ...spends.map(spendRowView),
      ]),
    );
  }
  return m("div", { class: "flex flex-col gap-3" }, sections);
}

function collapsedView(model: WidgetModel): m.Children {
  const cards = model.cards ?? [];
  const rings = widgetRings(cards);
  if (rings.length > 0) return m("span", { class: "flex items-start gap-3" }, rings.map(ringPairView));
  const pill = widgetPill(cards);
  return m(
    "span",
    {
      class: "font-semibold whitespace-nowrap tabular-nums text-(--widget-text)",
      "data-widget-pill": pill?.level ?? "",
      title: pill?.tooltip,
    },
    pill?.text ?? "",
  );
}

export interface WidgetAttrs {
  readonly model: WidgetModel;
  readonly mode: WidgetMode;
}

export const Widget: m.Component<WidgetAttrs> = {
  view(vnode) {
    const { model, mode } = vnode.attrs;
    const isCollapsed = mode === "collapsed";
    const content: m.Children = model.isCatchingUp
      ? m("span", { class: "text-(--widget-muted)" }, isCollapsed ? "..." : "Indexing usage...")
      : isCollapsed
        ? collapsedView(model)
        : expandedView(model);
    return m(
      "a",
      {
        id: "usage-widget",
        href: "/",
        target: "_blank",
        "data-widget-mode": mode,
        "data-live": model.isLive ? "true" : "false",
        class:
          "usage-widget inline-flex flex-col type-helper text-(--widget-text) no-underline " +
          (isCollapsed ? "gap-1 p-1 " : "w-56 gap-2 p-1.5 ") +
          (model.isLive ? "" : "opacity-60"),
      },
      [
        content,
        model.isLive || isCollapsed
          ? null
          : m("span", { "data-reconnecting": "", class: "flex items-center gap-1 text-(--widget-faint)" }, [
              m("span", { class: "inline-block size-1.5 rounded-full bg-(--widget-faint)" }),
              "Reconnecting",
            ]),
      ],
    );
  },
};
