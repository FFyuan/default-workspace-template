/**
 * The bars version of the Usage widget (app-widgets plan section 7.8), after a system monitor's meters: a row per
 * subscription with its name, two horizontal bars (the 5-hour limit above, the weekly one thinner below) and their
 * shares used, the 5-hour one in bold. Nothing explains them at rest; while the pointer is over the widget, each bar
 * gives way to its window's name and when it resets, in the bar's own place, so the widget never changes size. Then
 * the pay-as-you-go spend. Collapsed, the same rows without the weekly figure, under the subscription's short name.
 */

import m from "mithril";
import type { LimitWindow } from "../models/providers";
import { ringFraction, resetText, widgetRows } from "../models/widget";
import type { LimitRow, SpendRow, WidgetModel } from "../models/widget";
import { percentText, pillView, spendSectionView, windowColour } from "./widgetParts";
import type { WindowRole } from "./widgetParts";

const SHORT_NAME: Record<WindowRole, string> = { short: "5h", long: "wk" };
const BAR_HEIGHT: Record<WindowRole, string> = { short: "h-1.5", long: "h-1" };

/** One window's line: its bar at rest, its name and reset time in the bar's place under the pointer. */
function barLine(window: LimitWindow, role: WindowRole, isDetailShown: boolean): m.Vnode {
  const width = ringFraction(window) * 100;
  return m("span", { "data-widget-bar-line": role, class: "relative flex h-3.5 min-w-0 flex-1 items-center" }, [
    m(
      "span",
      {
        class:
          `w-full overflow-hidden rounded-full bg-(--widget-track) ${BAR_HEIGHT[role]} transition-opacity ` +
          (isDetailShown ? "group-hover:opacity-0" : ""),
      },
      m("span", {
        "data-widget-bar": role,
        "data-widget-bar-level": window.level,
        class: "block h-full rounded-full",
        style: { width: `${width}%`, background: windowColour(window, role) },
      }),
    ),
    isDetailShown
      ? m(
          "span",
          {
            "data-widget-bar-detail": role,
            class:
              "absolute inset-0 flex items-center truncate text-[10px] tabular-nums text-(--widget-muted) " +
              "opacity-0 transition-opacity group-hover:opacity-100",
          },
          `${SHORT_NAME[role]} · ${resetText(window)}`,
        )
      : null,
  ]);
}

function figure(window: LimitWindow, role: WindowRole): m.Vnode {
  return m(
    "span",
    {
      "data-widget-percent": window.isResetSinceReading ? "reset" : window.level,
      class:
        "w-8 shrink-0 text-right tabular-nums " +
        (role === "short" ? "font-semibold text-(--widget-text)" : "text-[10px] text-(--widget-muted)"),
    },
    percentText(window),
  );
}

function limitRowView(row: LimitRow): m.Vnode {
  return m("div", { key: row.key, "data-widget-row": row.key, class: "flex items-center gap-2", title: row.tooltip }, [
    m("span", { class: "w-12 shrink-0 truncate text-(--widget-text)" }, row.name),
    m("div", { class: "flex min-w-0 flex-1 flex-col" }, [
      m("div", { class: "flex items-center gap-2" }, [
        barLine(row.primary, "short", true),
        figure(row.primary, "short"),
      ]),
      row.secondary === null
        ? null
        : m("div", { class: "flex items-center gap-2" }, [
            barLine(row.secondary, "long", true),
            figure(row.secondary, "long"),
          ]),
    ]),
  ]);
}

function collapsedRowView(row: LimitRow): m.Vnode {
  return m(
    "div",
    { key: row.key, "data-widget-row": row.key, class: "flex items-center gap-1.5", title: row.tooltip },
    [
      m(
        "span",
        { class: "w-12 shrink-0 truncate text-[9px] font-semibold tracking-wider text-(--widget-muted) uppercase" },
        row.name,
      ),
      m("div", { class: "flex w-12 flex-col gap-0.5" }, [
        barLine(row.primary, "short", false),
        row.secondary === null ? null : barLine(row.secondary, "long", false),
      ]),
      figure(row.primary, "short"),
    ],
  );
}

export function barsExpanded(model: WidgetModel): m.Children {
  const rows = widgetRows(model.cards ?? []);
  const limits = rows.filter((row): row is LimitRow => row.kind === "limit");
  const spends = rows.filter((row): row is SpendRow => row.kind === "spend");
  const sections: m.Vnode[] =
    limits.length === 0 ? [] : [m("div", { key: "limits", class: "flex flex-col gap-1.5" }, limits.map(limitRowView))];
  const spend = spendSectionView(spends);
  if (spend !== null) sections.push(spend);
  return m("div", { class: "flex flex-col gap-3" }, sections);
}

export function barsCollapsed(model: WidgetModel): m.Children {
  const cards = model.cards ?? [];
  const limits = widgetRows(cards).filter((row): row is LimitRow => row.kind === "limit");
  if (limits.length > 0) return m("div", { class: "flex flex-col gap-1" }, limits.map(collapsedRowView));
  return pillView(cards);
}
