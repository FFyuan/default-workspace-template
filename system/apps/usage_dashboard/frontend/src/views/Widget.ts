/**
 * The Usage widget's view (app-widgets plan section 7): the whole widget is one link to the Usage page, opened in a
 * window of its own (``target="_blank"``, which the shell's link rule turns into raising the Usage window). Expanded,
 * a row per provider; collapsed, a pair of concentric hairline rings per subscription (the weekly limit outside, the
 * 5-hour limit inside, each drawn in its level's colour over a faint track), or with no subscription one pill of
 * the month's spend. While the collector indexes its first history the widget says so rather
 * than show partial totals, and while the stream is down it keeps the last figures, dimmed. Hover detail is each
 * row's and each ring pair's ``title``: a drawn tooltip would be clipped by the widget's small frame.
 */

import m from "mithril";
import type { WidgetMode } from "@imbue/workspace-ui/src/app_contract";
import type { LimitLevel, LimitWindow } from "../models/providers";
import { ringFraction, widgetPill, widgetRings, widgetRows } from "../models/widget";
import type { RingPair, WidgetModel, WidgetRow } from "../models/widget";

const LEVEL_FILL: Record<LimitLevel, string> = {
  ok: "bg-(--color-accent)",
  high: "bg-(--color-warning)",
  critical: "bg-(--color-danger)",
};
const LEVEL_TEXT: Record<LimitLevel, string> = { ok: "text-primary", high: "text-warning", critical: "text-danger" };
const LEVEL_STROKE: Record<LimitLevel, string> = {
  ok: "stroke-(--color-accent)",
  high: "stroke-(--color-warning)",
  critical: "stroke-(--color-danger)",
};

// The rings' drawing, in the units of its own view box: two circles about one centre, a hairline apart.
const RING_BOX = 28;
const RING_CENTRE = RING_BOX / 2;
const OUTER_RADIUS = 12.5;
const INNER_RADIUS = 8.5;
const RING_STROKE = 2;

/** One ring: a faint full track, and over it, from twelve o'clock clockwise, the arc of the share used. */
function ringView(window: LimitWindow, radius: number, role: "inner" | "outer"): m.Vnode[] {
  const fraction = ringFraction(window);
  const circle = { cx: RING_CENTRE, cy: RING_CENTRE, r: radius, fill: "none", "stroke-width": RING_STROKE };
  const track = m("circle", { ...circle, class: "stroke-fill-hover" });
  if (fraction === 0) return [track];
  const arc = m("circle", {
    ...circle,
    "data-ring": role,
    "data-ring-level": window.level,
    class: LEVEL_STROKE[window.level],
    pathLength: 100,
    "stroke-dasharray": `${fraction * 100} 100`,
    "stroke-linecap": "round",
    transform: `rotate(-90 ${RING_CENTRE} ${RING_CENTRE})`,
  });
  return [track, arc];
}

function ringPairView(pair: RingPair): m.Vnode {
  return m(
    "span",
    { key: pair.key, "data-widget-rings": pair.key, class: "flex items-center gap-1", title: pair.tooltip },
    [
      m(
        "svg",
        { viewBox: `0 0 ${RING_BOX} ${RING_BOX}`, class: "size-7 shrink-0", "aria-label": pair.tooltip, role: "img" },
        [
          ...(pair.outer === null ? [] : ringView(pair.outer, OUTER_RADIUS, "outer")),
          ...ringView(pair.inner, INNER_RADIUS, "inner"),
        ],
      ),
      m("span", { class: "text-secondary" }, pair.name),
    ],
  );
}

function percentText(window: LimitWindow): string {
  return window.isResetSinceReading || window.usedPercent === null ? "—" : `${Math.round(window.usedPercent)}%`;
}

function rowView(row: WidgetRow): m.Vnode {
  if (row.kind === "spend") {
    return m(
      "div",
      { key: row.key, "data-widget-row": row.key, class: "flex items-center gap-2", title: row.tooltip },
      [
        m("span", { class: "w-16 shrink-0 truncate text-secondary" }, row.name),
        m("span", { class: "ml-auto font-medium tabular-nums" }, row.spend),
      ],
    );
  }
  const { primary, secondary } = row;
  const width = primary.isResetSinceReading ? 0 : Math.min(100, Math.max(0, primary.usedPercent ?? 0));
  return m("div", { key: row.key, "data-widget-row": row.key, class: "flex items-center gap-2", title: row.tooltip }, [
    m("span", { class: "w-16 shrink-0 truncate text-secondary" }, row.name),
    m("div", { class: "h-1.5 w-12 shrink-0 overflow-hidden rounded-full bg-fill-hover" }, [
      m("div", { class: `h-full rounded-full ${LEVEL_FILL[primary.level]}`, style: { width: `${width}%` } }),
    ]),
    m(
      "span",
      {
        "data-widget-reset": primary.isResetSinceReading ? "true" : "false",
        class: `w-9 text-right font-medium tabular-nums ${primary.isResetSinceReading ? "text-faint" : LEVEL_TEXT[primary.level]}`,
      },
      percentText(primary),
    ),
    secondary === null ? null : m("span", { class: `tabular-nums text-faint` }, `· ${percentText(secondary)}`),
  ]);
}

export interface WidgetAttrs {
  readonly model: WidgetModel;
  readonly mode: WidgetMode;
}

export const Widget: m.Component<WidgetAttrs> = {
  view(vnode) {
    const { model, mode } = vnode.attrs;
    const isCollapsed = mode === "collapsed";
    const cards = model.cards ?? [];
    const pill = widgetPill(cards);
    const rings = widgetRings(cards);
    const content: m.Children = model.isCatchingUp
      ? m("span", { class: "text-secondary" }, isCollapsed ? "..." : "Indexing usage...")
      : isCollapsed && rings.length > 0
        ? m("span", { class: "flex items-center gap-2" }, rings.map(ringPairView))
        : isCollapsed
          ? m(
              "span",
              {
                class: `font-medium whitespace-nowrap tabular-nums ${pill === null ? "" : LEVEL_TEXT[pill.level]}`,
                title: pill?.tooltip,
              },
              pill?.text ?? "",
            )
          : widgetRows(cards).map(rowView);
    return m(
      "a",
      {
        id: "usage-widget",
        href: "/",
        target: "_blank",
        "data-widget-mode": mode,
        "data-live": model.isLive ? "true" : "false",
        class:
          "usage-widget inline-flex flex-col gap-1 px-2 py-1.5 type-helper text-primary no-underline " +
          (isCollapsed ? "" : "w-56 ") +
          (model.isLive ? "" : "opacity-60"),
      },
      [
        content,
        model.isLive || isCollapsed
          ? null
          : m("span", { "data-reconnecting": "", class: "flex items-center gap-1 text-faint" }, [
              m("span", { class: "inline-block size-1.5 rounded-full bg-(--color-faint)" }),
              "Reconnecting",
            ]),
      ],
    );
  },
};
