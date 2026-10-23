/**
 * What every version of the Usage widget draws alike (app-widgets plan section 7): the colour a window is shown in,
 * its figure, a section's heading, a pay-as-you-go row, and the one figure of the month's spend a collapsed widget
 * falls back to with no subscription.
 */

import m from "mithril";
import type { LimitWindow } from "../models/providers";
import { widgetPill } from "../models/widget";
import type { SpendRow } from "../models/widget";
import type { ProviderCard } from "../models/providers";

/** Which of a subscription's windows a mark stands for: the shortest (5-hour) inside or above, the longest outside or
 *  below. */
export type WindowRole = "short" | "long";

// A comfortable window keeps its own hue; a high or critical one takes the level's colour.
const ROLE_COLOUR: Record<WindowRole, string> = { short: "var(--widget-short)", long: "var(--widget-long)" };

export function windowColour(window: LimitWindow, role: WindowRole): string {
  if (window.level === "critical") return "var(--widget-critical)";
  if (window.level === "high") return "var(--widget-high)";
  return ROLE_COLOUR[role];
}

export function percentText(window: LimitWindow): string {
  return window.isResetSinceReading || window.usedPercent === null ? "—" : `${Math.round(window.usedPercent)}%`;
}

export function sectionHeading(name: string): m.Vnode {
  return m(
    "span",
    { class: "text-[10px] leading-none font-semibold tracking-wider text-(--widget-heading) uppercase" },
    name,
  );
}

export function spendRowView(row: SpendRow): m.Vnode {
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

/** Pay-as-you-go spend under its heading, or nothing with none. */
export function spendSectionView(spends: readonly SpendRow[]): m.Vnode | null {
  if (spends.length === 0) return null;
  return m("div", { key: "spend", class: "flex flex-col gap-1" }, [
    sectionHeading("API this month"),
    ...spends.map(spendRowView),
  ]);
}

/** The collapsed widget with no subscription: one figure of this month's spend. */
export function pillView(cards: readonly ProviderCard[]): m.Vnode {
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
