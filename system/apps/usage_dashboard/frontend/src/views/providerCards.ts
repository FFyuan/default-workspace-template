/**
 * The top of the page: one card per provider in use. A subscription card shows how much of each limit is used
 * and when it resets; a spend card shows this month's pay-as-you-go spend.
 */

import m from "mithril";

import { formatCalls, formatClock, formatDollars } from "../models/format";
import type { LimitLevel, LimitWindow, ProviderCard, SpendCard, SubscriptionCard } from "../models/providers";

const CARD_CLASS = "provider-card flex min-w-0 flex-col gap-3 rounded-lg border border-default bg-surface p-4";

const BAR_CLASSES: Record<LimitLevel, string> = {
  ok: "bg-(--color-accent)",
  high: "bg-(--color-warning)",
  critical: "bg-(--color-danger)",
};
const LEVEL_NOTES: Record<LimitLevel, string | null> = { ok: null, high: "Getting close", critical: "Almost out" };

/** "resets 9:30 PM" today, "resets Mon 2:00 PM" another day. */
export function resetText(resetsAt: Date, now: Date): string {
  const time = resetsAt.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  if (resetsAt.toDateString() === now.toDateString()) return `resets ${time}`;
  return `resets ${resetsAt.toLocaleDateString(undefined, { weekday: "short" })} ${time}`;
}

/** When a reading was taken: the clock today, the weekday and clock before that. */
export function asOfText(observedAt: Date, now: Date): string {
  if (observedAt.toDateString() === now.toDateString()) return formatClock(observedAt);
  return `${observedAt.toLocaleDateString(undefined, { weekday: "short" })} ${formatClock(observedAt)}`;
}

function limitRow(window: LimitWindow, now: Date): m.Vnode {
  const percent = window.usedPercent;
  const note = LEVEL_NOTES[window.level];
  return m("div", { class: "limit-window flex flex-col gap-1", "data-window": window.key }, [
    m("div", { class: "flex items-baseline justify-between gap-2" }, [
      m("span", { class: "type-body text-primary" }, window.label),
      m(
        "span",
        { class: "type-body tabular-nums font-semibold text-primary" },
        percent === null ? "–" : `${Math.round(percent)}%`,
      ),
    ]),
    m(
      "div",
      {
        class: "h-2 rounded-full bg-fill-hover",
        role: "meter",
        "aria-label": window.label,
        "aria-valuemin": 0,
        "aria-valuemax": 100,
        "aria-valuenow": percent ?? 0,
      },
      m("div", {
        class: `h-2 rounded-full ${BAR_CLASSES[window.level]}`,
        style: { width: `${Math.min(100, Math.max(0, percent ?? 0))}%` },
      }),
    ),
    m("div", { class: "flex justify-between gap-2 type-helper text-secondary" }, [
      m(
        "span",
        window.isResetSinceReading
          ? "Reset since the last reading"
          : window.resetsAt === null
            ? ""
            : resetText(window.resetsAt, now),
      ),
      note === null ? null : m("span", { class: window.level === "critical" ? "text-danger" : "text-warning" }, note),
    ]),
  ]);
}

function subscriptionCard(card: SubscriptionCard, now: Date): m.Vnode {
  return m("section", { class: CARD_CLASS, "data-card": card.key }, [
    m("div", { class: "flex items-baseline justify-between gap-2" }, [
      m("h2", { class: "type-section text-primary" }, card.title),
      m(
        "span",
        { class: "shrink-0 whitespace-nowrap type-tag text-faint" },
        `as of ${asOfText(card.observedAt, now)}`,
      ),
    ]),
    card.windows.map((window) => limitRow(window, now)),
    card.listPriceThisMonth === null
      ? null
      : m(
          "div",
          { class: "type-helper text-faint" },
          `This month's use would be ≈ ${formatDollars(card.listPriceThisMonth)} at API prices.`,
        ),
  ]);
}

function spendCard(card: SpendCard): m.Vnode {
  return m("section", { class: CARD_CLASS, "data-card": card.key }, [
    m("div", { class: "flex items-baseline justify-between gap-2" }, [
      m("h2", { class: "type-section text-primary" }, card.title),
      m("span", { class: "shrink-0 whitespace-nowrap type-tag text-faint" }, "this month"),
    ]),
    m("div", { class: "flex items-baseline gap-2" }, [
      m(
        "span",
        { class: "type-heading-lg tabular-nums text-primary" },
        `${card.isEstimated ? "~" : ""}${formatDollars(card.spend)}`,
      ),
      m("span", { class: "type-helper text-secondary" }, formatCalls(card.calls)),
    ]),
    card.unknownCostCalls === 0
      ? null
      : m("div", { class: "type-helper text-warning" }, `+${formatCalls(card.unknownCostCalls)} with unknown cost`),
    card.isEstimated ? m("div", { class: "type-helper text-faint" }, "~ includes costs estimated from tokens") : null,
  ]);
}

export function providerSection(cards: readonly ProviderCard[] | null, now: Date): m.Vnode {
  if (cards === null) return m("div", { class: "type-helper py-6 text-center text-faint" }, "Loading usage…");
  if (cards.length === 0) {
    return m(
      "div",
      { class: "provider-empty rounded-lg border border-default bg-surface p-4 type-body text-secondary" },
      "No model usage yet this month.",
    );
  }
  return m(
    "div",
    { class: "provider-cards grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-3" },
    cards.map((card) => (card.kind === "subscription" ? subscriptionCard(card, now) : spendCard(card))),
  );
}
