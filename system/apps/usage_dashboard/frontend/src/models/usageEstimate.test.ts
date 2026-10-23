import { describe, expect, it } from "vitest";

import type { LimitWindow } from "./providers";
import { calibrationSpan, chosenScale, formatShare, percentPerDollar } from "./usageEstimate";

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

describe("calibrationSpan", () => {
  it("runs from the window's start to the reading", () => {
    expect(calibrationSpan(window({}))).toEqual({
      since: new Date("2026-10-20T00:00:00Z"),
      until: new Date("2026-10-22T20:00:00Z"),
    });
  });

  it("keeps the last reading's span once its window has reset", () => {
    const reset = window({ isResetSinceReading: true, usedPercent: 0, resetsAt: null });

    expect(calibrationSpan(reset)?.since).toEqual(new Date("2026-10-20T00:00:00Z"));
  });

  it("has nothing to calibrate on for an unused or open-ended window", () => {
    expect(calibrationSpan(window({ readingPercent: 0 }))).toBeNull();
    expect(calibrationSpan(window({ windowSeconds: null }))).toBeNull();
  });
});

describe("percentPerDollar", () => {
  it("spreads the reported share over the window's list price", () => {
    expect(percentPerDollar(34, 85)).toBeCloseTo(0.4);
    expect(percentPerDollar(34, 0)).toBeNull();
  });
});

describe("chosenScale and formatShare", () => {
  const at = { isFromEarlierWindow: false, windowStart: new Date(0), resetsAt: new Date(0) };
  const scales = [
    { windowKey: "five_hour", label: "5-hour limit", percentPerDollar: 2, ...at },
    { windowKey: "seven_day", label: "Weekly limit", percentPerDollar: 0.4, ...at },
  ];

  it("picks the viewer's window, else the first", () => {
    expect(chosenScale(scales, "seven_day")?.percentPerDollar).toBe(0.4);
    expect(chosenScale(scales, undefined)?.windowKey).toBe("five_hour");
    expect(chosenScale([], undefined)).toBeUndefined();
  });

  it("writes small shares with enough digits to tell calls apart", () => {
    expect(formatShare(0.004)).toBe("<0.01%");
    expect(formatShare(0.4213)).toBe("0.42%");
    expect(formatShare(3.14)).toBe("3.1%");
  });
});
