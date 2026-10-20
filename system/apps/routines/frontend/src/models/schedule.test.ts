import { describe, expect, it } from "vitest";

import type { RoutineDefinition } from "./api";
import { changeOf, formOf, offersTimeOfDay, problemOf, sentenceOf, type ScheduleForm } from "./schedule";

const DEFINITION: RoutineDefinition = {
  title: "Morning inbox digest",
  what: "Reads mail.",
  every: "1d",
  at: "07:30",
  days: ["MON", "FRI"],
  day_of_month: null,
  once: null,
  command: null,
  skill: "inbox-digest",
  enabled: true,
  timeout: "1h",
  retry_after: "2m",
  notify_after_failures: 3,
  app: null,
};

function form(patch: Partial<ScheduleForm>): ScheduleForm {
  return { mode: "every", count: "1", unit: "d", at: "", days: [], dayOfMonth: "", once: "", ...patch };
}

describe("formOf", () => {
  it("opens on what the definition says", () => {
    expect(formOf(DEFINITION)).toEqual(form({ count: "1", unit: "d", at: "07:30", days: ["mon", "fri"] }));
  });

  it("opens a one-off on its moment", () => {
    const once = formOf({ ...DEFINITION, every: null, at: null, days: [], once: "2026-11-03T15:00:00" });
    expect(once.mode).toBe("once");
    expect(once.once).toBe("2026-11-03T15:00");
  });
});

describe("changeOf", () => {
  it("spells the cadence the way a definition does", () => {
    expect(changeOf(form({ count: "2", unit: "h", days: ["mon"] }))).toEqual({
      every: "2h",
      at: null,
      days: ["mon"],
      day_of_month: null,
      once: null,
    });
    expect(changeOf(form({ count: "1", unit: "mo", at: "00:00", dayOfMonth: "1" }))).toEqual({
      every: "1mo",
      at: "00:00",
      days: [],
      day_of_month: 1,
      once: null,
    });
    expect(changeOf(form({ mode: "once", once: "2026-11-03T15:00" }))).toEqual({
      every: null,
      at: null,
      days: [],
      day_of_month: null,
      once: "2026-11-03T15:00",
    });
  });
});

describe("problemOf", () => {
  it("names what cannot be saved", () => {
    expect(problemOf(form({ count: "0" }))).toMatch(/at least 1/);
    expect(problemOf(form({ count: "x" }))).toMatch(/whole number/);
    expect(problemOf(form({ count: "2", unit: "h", at: "07:00" }))).toMatch(/daily or less/);
    expect(problemOf(form({ count: "400", unit: "d" }))).toMatch(/longer than a year/);
    expect(problemOf(form({ unit: "d", dayOfMonth: "3" }))).toMatch(/monthly/);
    expect(problemOf(form({ mode: "once", once: "" }))).toMatch(/date and a time/);
    expect(problemOf(form({ count: "1", unit: "d", at: "07:30" }))).toBeNull();
  });

  it("offers a time of day only from a day up", () => {
    expect(offersTimeOfDay(form({ count: "30", unit: "m" }))).toBe(false);
    expect(offersTimeOfDay(form({ count: "1", unit: "d" }))).toBe(true);
    expect(offersTimeOfDay(form({ count: "24", unit: "h" }))).toBe(true);
  });
});

describe("sentenceOf", () => {
  it("reads as the list reads", () => {
    expect(sentenceOf(form({ count: "15", unit: "m" }))).toBe("Every 15 minutes");
    expect(sentenceOf(form({ count: "1", unit: "h" }))).toBe("Every hour");
    expect(sentenceOf(form({ count: "1", unit: "d", at: "07:30" }))).toBe("Every day at 7:30 am");
    expect(sentenceOf(form({ count: "1", unit: "d", at: "09:00", days: ["mon", "fri"] }))).toBe(
      "Every Monday and Friday at 9:00 am",
    );
    expect(sentenceOf(form({ count: "1", unit: "d", days: ["mon", "tue", "wed", "thu", "fri"] }))).toBe(
      "Every weekdays",
    );
    expect(sentenceOf(form({ count: "2", unit: "w", days: ["sat"] }))).toBe("Every 2 weeks on Saturday");
    expect(sentenceOf(form({ count: "1", unit: "mo", dayOfMonth: "1", at: "00:00" }))).toBe(
      "Monthly on the 1st at midnight",
    );
    expect(sentenceOf(form({ count: "2", unit: "mo", dayOfMonth: "22", at: "12:00" }))).toBe(
      "Every 2 months on the 22nd at noon",
    );
    expect(sentenceOf(form({ mode: "once", once: "2026-11-03T15:00" }))).toBe("Once, Nov 3 at 3:00 pm");
  });
});
