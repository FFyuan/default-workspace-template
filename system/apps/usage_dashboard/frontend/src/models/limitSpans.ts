/**
 * A subscription's limit windows, as spans of time to measure this workspace's own usage in.
 *
 * A harness reports each limit window's share used for the whole account, which counts usage from everywhere the
 * account is signed in, not only this workspace. So the page does not spread that share over the calls it sees.
 * It takes from the reading only when each window started and resets, and measures the calls recorded here within
 * that span by their cost at the models' API rates (the list price the collector puts on subscription calls).
 *
 * Once a window resets its harness reports nothing for it until the next call, so the last reading's span is kept,
 * and the page says the window shown is the earlier one.
 */

import type { Group, TotalsRow } from "./api";
import { type BreakdownId, NO_SOURCE_NAMES, breakdownLines } from "./breakdown";
import type { LimitWindow } from "./providers";

/** One limit window of a subscription, as a span of time. */
export interface LimitSpan {
  windowKey: string;
  label: string;
  /** Whether the window has reset since the reading the span comes from. */
  isFromEarlierWindow: boolean;
  /** When the reading's window started and reset, for measuring calls in and marking on a chart. */
  windowStart: Date;
  resetsAt: Date;
}

/** The span of the window a limit's last reading was in, or null for a window with no length or reset time. */
export function limitSpan(window: LimitWindow): LimitSpan | null {
  if (window.readingResetsAt === null || window.windowSeconds === null) return null;
  return {
    windowKey: window.key,
    label: window.label,
    isFromEarlierWindow: window.isResetSinceReading,
    windowStart: new Date(window.readingResetsAt.getTime() - window.windowSeconds * 1000),
    resetsAt: window.readingResetsAt,
  };
}

/** The span a subscription's usage is shown against: the window its viewer picked, else its shortest. */
export function chosenSpan(spans: readonly LimitSpan[], windowKey: string | undefined): LimitSpan | undefined {
  return spans.find((span) => span.windowKey === windowKey) ?? spans[0];
}

/** The key a breakdown line is known by, across answers for different spans of time. */
export function lineKey(group: Group): string {
  return JSON.stringify(group);
}

/**
 * Each breakdown line's cost at API rates within a limit's window, by ``lineKey``: the list price of its
 * subscription calls there. A line with no priced subscription calls in that window is left out.
 */
export function limitCosts(breakdown: BreakdownId, windowRows: readonly TotalsRow[]): Map<string, number> {
  const costs = new Map<string, number>();
  for (const line of breakdownLines(breakdown, windowRows, [], NO_SOURCE_NAMES)) {
    if (line.listPrice !== null) costs.set(lineKey(line.group), line.listPrice);
  }
  return costs;
}
