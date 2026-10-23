/**
 * An estimate of how much of a subscription's limit each call used, from its tokens.
 *
 * A harness reports only each limit window's total share used, not what each call took. The calls in a window
 * are priced at their models' API rates (the list price the collector already puts on subscription calls), which
 * weighs an Opus token above a Haiku one much as the limits do, and the window's reported share is spread over
 * them in proportion: the reading's share divided by the list price of the provider's subscription calls between
 * the window's start and the reading gives a share per dollar, and a call's estimated share is its list price
 * times that. It is an estimate: the providers do not publish how their limits are counted.
 *
 * Once a window resets its harness reports nothing for it until the next call, so the last reading's rate is kept:
 * it is the account's rate, which a reset does not change, and the page says the estimate rests on it.
 */

import type { Group, TotalsRow } from "./api";
import { type BreakdownId, NO_SOURCE_NAMES, breakdownLines } from "./breakdown";
import type { LimitWindow } from "./providers";

/** The share of one limit window a dollar of list price uses, for one subscription. */
export interface UsageScale {
  windowKey: string;
  label: string;
  percentPerDollar: number;
  /** Whether the window has reset since the reading the rate comes from. */
  isFromEarlierWindow: boolean;
  /** When the reading's window started and reset, for marking on a chart. */
  windowStart: Date;
  resetsAt: Date;
}

/** The span a window's reading covers, from the window's start to the reading, whether or not it has reset since. */
export function calibrationSpan(window: LimitWindow): { since: Date; until: Date } | null {
  if (window.readingResetsAt === null || window.windowSeconds === null) return null;
  if (window.readingPercent === null || window.readingPercent <= 0) return null;
  const since = new Date(window.readingResetsAt.getTime() - window.windowSeconds * 1000);
  return since < window.observedAt ? { since, until: window.observedAt } : null;
}

/** The share per dollar of list price, or null when the window's calls had no list price to spread it over. */
export function percentPerDollar(usedPercent: number, listPrice: number): number | null {
  return listPrice > 0 ? usedPercent / listPrice : null;
}

/** The scale a subscription's usage is shown against: the window its viewer picked, else its shortest. */
export function chosenScale(scales: readonly UsageScale[], windowKey: string | undefined): UsageScale | undefined {
  return scales.find((scale) => scale.windowKey === windowKey) ?? scales[0];
}

/** "0.42%", "3.1%", "<0.01%": a call's estimated share of a limit. */
export function formatShare(percent: number): string {
  if (percent > 0 && percent < 0.01) return "<0.01%";
  if (percent < 1) return `${percent.toFixed(2)}%`;
  return `${percent.toFixed(1)}%`;
}

/** The key a breakdown line is known by, across answers for different spans of time. */
export function lineKey(group: Group): string {
  return JSON.stringify(group);
}

/**
 * Each breakdown line's estimated share of a limit within the limit's most recent window, by ``lineKey``: its list
 * price there times the scale's rate. A line with no subscription calls in that window is left out.
 */
export function limitShares(
  breakdown: BreakdownId,
  windowRows: readonly TotalsRow[],
  scale: UsageScale,
): Map<string, number> {
  const shares = new Map<string, number>();
  for (const line of breakdownLines(breakdown, windowRows, [], NO_SOURCE_NAMES)) {
    if (line.listPrice !== null) shares.set(lineKey(line.group), line.listPrice * scale.percentPerDollar);
  }
  return shares;
}
