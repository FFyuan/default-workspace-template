import { describe, expect, it } from "vitest";

import type { LimitWindow } from "./providers";
import { totalsRow } from "../testing/rows";
import { chosenSpan, limitCosts, limitSpan, lineKey } from "./limitSpans";

function window(patch: Partial<LimitWindow>): LimitWindow {
  return {
    key: "seven_day",
    label: "Weekly limit",
    usedPercent: 34,
    resetsAt: new Date("2026-10-27T00:00:00Z"),
    isResetSinceReading: false,
    level: "ok",
    windowSeconds: 604_800,
    observedAt: new Date("2026-10-22T20:00:00Z"),
    readingPercent: 34,
    readingResetsAt: new Date("2026-10-27T00:00:00Z"),
    ...patch,
  };
}

describe("limitSpan", () => {
  it("runs from the window's start to its reset", () => {
    expect(limitSpan(window({}))).toEqual({
      windowKey: "seven_day",
      label: "Weekly limit",
      isFromEarlierWindow: false,
      windowStart: new Date("2026-10-20T00:00:00Z"),
      resetsAt: new Date("2026-10-27T00:00:00Z"),
    });
  });

  it("keeps the last reading's window once it has reset, and says so", () => {
    const span = limitSpan(window({ isResetSinceReading: true, usedPercent: 0, resetsAt: null }));

    expect(span?.windowStart).toEqual(new Date("2026-10-20T00:00:00Z"));
    expect(span?.isFromEarlierWindow).toBe(true);
  });

  it("does not need the account to have used any of the limit", () => {
    // The span measures this workspace's calls, whatever share the account reports.
    expect(limitSpan(window({ readingPercent: 0 }))).not.toBeNull();
  });

  it("has no span for an open-ended window", () => {
    expect(limitSpan(window({ windowSeconds: null }))).toBeNull();
    expect(limitSpan(window({ readingResetsAt: null }))).toBeNull();
  });
});

describe("chosenSpan", () => {
  const at = { isFromEarlierWindow: false, windowStart: new Date(0), resetsAt: new Date(0) };
  const spans = [
    { windowKey: "five_hour", label: "5-hour limit", ...at },
    { windowKey: "seven_day", label: "Weekly limit", ...at },
  ];

  it("picks the viewer's window, else the first", () => {
    expect(chosenSpan(spans, "seven_day")?.label).toBe("Weekly limit");
    expect(chosenSpan(spans, undefined)?.windowKey).toBe("five_hour");
    expect(chosenSpan([], undefined)).toBeUndefined();
  });
});

describe("limitCosts", () => {
  it("is each line's list price of subscription calls in the window", () => {
    const rows = [
      totalsRow({ group: { model: "anthropic/opus", billing_mode: "SUBSCRIPTION" }, cost_usd: "2" }),
      totalsRow({ group: { model: "anthropic/haiku", billing_mode: "SUBSCRIPTION" }, cost_usd: "0.5" }),
      totalsRow({ group: { model: "anthropic/sonnet", billing_mode: "SUBSCRIPTION" }, cost_usd: null }),
    ];

    const costs = limitCosts("model", rows);

    expect(costs.get(lineKey({ model: "anthropic/opus" }))).toBe(2);
    expect(costs.get(lineKey({ model: "anthropic/haiku" }))).toBe(0.5);
    expect(costs.has(lineKey({ model: "anthropic/sonnet" }))).toBe(false);
  });
});
