// @vitest-environment jsdom

import m from "mithril";
import { describe, expect, it } from "vitest";

import type { LimitReading } from "../models/api";
import { formatClock } from "../models/format";
import { providerCards } from "../models/providers";
import type { WidgetModel } from "../models/widget";
import { totalsRow } from "../testing/rows";
import type { WidgetVariant } from "../models/widgetVariant";
import { Widget } from "./Widget";

const NOW = new Date("2026-10-22T20:00:00Z");

function reading(patch: Partial<LimitReading>): LimitReading {
  return {
    source: "claude",
    window: "five_hour",
    label: "5h",
    used_percentage: 61,
    resets_at: "2026-10-22T22:30:00Z",
    window_seconds: 18_000,
    observed_at: "2026-10-22T19:45:00Z",
    ...patch,
  };
}

const WEEKLY = { window: "seven_day", label: "7d", window_seconds: 604_800, resets_at: "2026-10-26T21:00:00Z" };

function rendered(
  limits: LimitReading[],
  mode: "expanded" | "collapsed",
  variant: WidgetVariant = "rings",
): HTMLElement {
  const model = { cards: providerCards(limits, [], NOW), isLive: true, isCatchingUp: false } as WidgetModel;
  const root = document.createElement("div");
  m.render(root, m(Widget, { model, mode, variant }));
  return root;
}

describe("the collapsed Usage widget", () => {
  it("draws a subscription's weekly limit as the outer ring and its 5-hour limit as the inner, at their levels", () => {
    const root = rendered(
      [reading({ used_percentage: 80 }), reading({ ...WEEKLY, used_percentage: 34 })],
      "collapsed",
    );

    const pair = root.querySelector('[data-widget-rings="subscription:claude"]');
    expect(pair?.getAttribute("title")).toContain("5-hour limit: 80% used");
    const outer = pair?.querySelector('[data-ring="outer"]');
    const inner = pair?.querySelector('[data-ring="inner"]');
    expect([outer?.getAttribute("r"), outer?.getAttribute("stroke-dasharray")]).toEqual(["18", "34 100"]);
    expect([inner?.getAttribute("r"), inner?.getAttribute("stroke-dasharray")]).toEqual(["13.5", "80 100"]);
    expect(inner?.getAttribute("data-ring-level")).toBe("high");
    // A comfortable ring keeps its window's hue; a high one takes the level's colour.
    expect(outer?.getAttribute("stroke")).toBe("var(--widget-long)");
    expect(inner?.getAttribute("stroke")).toBe("var(--widget-high)");
    // The 5-hour figure sits in the middle, and the pair carries its provider's name, alone as beside another.
    expect(pair?.querySelector("[data-ring-figure]")?.textContent).toBe("80%");
    expect(pair?.querySelector("[data-ring-name]")?.textContent).toBe("Claude");
  });

  it("names each of several pairs, and leaves a reset window's ring as a bare track", () => {
    const root = rendered(
      [reading({ resets_at: "2026-10-22T19:00:00Z" }), reading({ source: "codex", used_percentage: 18 })],
      "collapsed",
    );

    const pairs = [...root.querySelectorAll("[data-widget-rings]")];
    expect(pairs.map((pair) => pair.querySelector("[data-ring-name]")?.textContent)).toEqual(["Claude", "Codex"]);
    expect(pairs.map((pair) => pair.querySelector("[data-ring-figure]")?.textContent)).toEqual(["—", "18%"]);
    expect(pairs[0].querySelector("[data-ring]")).toBeNull();
    expect(pairs[0].querySelectorAll("circle")).toHaveLength(1);
  });

  it("falls back to the month's spend with no subscription, and keeps the rows when expanded", () => {
    const model = {
      cards: providerCards(
        [],
        [totalsRow({ group: { provider: "anthropic", billing_mode: "API_KEY" }, cost_usd: "9.5" })],
        NOW,
      ),
      isLive: true,
      isCatchingUp: false,
    } as WidgetModel;
    const root = document.createElement("div");
    m.render(root, m(Widget, { model, mode: "collapsed", variant: "rings" }));
    expect(root.querySelector("[data-widget-rings]")).toBeNull();
    expect(root.textContent).toContain("$9.50");
    expect(rendered([reading({})], "expanded").querySelector("[data-widget-row]")).not.toBeNull();
  });
});

describe("the expanded Usage widget", () => {
  it("heads a section per subscription, with a row per window giving when it resets and the share used", () => {
    const root = rendered([reading({ used_percentage: 61 }), reading({ ...WEEKLY, used_percentage: 92 })], "expanded");

    const section = root.querySelector('[data-widget-row="subscription:claude"]');
    expect(section?.textContent).toContain("Claude");
    const rows = [...(section?.querySelectorAll("[data-widget-window]") ?? [])];
    expect(rows.map((row) => row.querySelector("span:nth-child(2)")?.textContent)).toEqual(["5-hour", "Weekly"]);
    expect(rows.map((row) => row.querySelector("[data-widget-percent]")?.textContent)).toEqual(["61%", "92%"]);
    expect(rows.map((row) => row.querySelector("[data-widget-percent]")?.getAttribute("data-widget-percent"))).toEqual(
      ["ok", "critical"],
    );
    // The 5-hour window resets on the clock; the weekly one by its day and hour.
    expect(rows.map((row) => row.querySelector("[data-widget-reset]")?.textContent)).toEqual([
      formatClock(new Date("2026-10-22T22:30:00Z")),
      new Date(WEEKLY.resets_at).toLocaleString(undefined, { weekday: "short", hour: "numeric" }),
    ]);
    expect(section?.querySelector('[data-ring="outer"]')?.getAttribute("stroke")).toBe("var(--widget-critical)");
  });
});

describe("the bars version of the Usage widget", () => {
  it("draws a row per subscription with the 5-hour bar above the weekly one, explained only under the pointer", () => {
    const root = rendered(
      [reading({ used_percentage: 61 }), reading({ ...WEEKLY, used_percentage: 92 })],
      "expanded",
      "bars",
    );

    expect(root.querySelector("#usage-widget")?.getAttribute("data-widget-variant")).toBe("bars");
    const row = root.querySelector('[data-widget-row="subscription:claude"]');
    expect(row?.textContent).toContain("Claude");
    const short = row?.querySelector('[data-widget-bar="short"]') as HTMLElement;
    const long = row?.querySelector('[data-widget-bar="long"]') as HTMLElement;
    expect([short.style.width, short.style.background]).toEqual(["61%", "var(--widget-short)"]);
    expect([long.style.width, long.style.background]).toEqual(["92%", "var(--widget-critical)"]);
    expect([...(row?.querySelectorAll("[data-widget-percent]") ?? [])].map((figure) => figure.textContent)).toEqual([
      "61%",
      "92%",
    ]);
    // Which window a bar stands for, and when it resets, is hidden until the pointer is over the widget.
    const details = [...(row?.querySelectorAll("[data-widget-bar-detail]") ?? [])];
    expect(details.map((detail) => detail.textContent)).toEqual([
      `5h · ${formatClock(new Date("2026-10-22T22:30:00Z"))}`,
      `wk · ${new Date(WEEKLY.resets_at).toLocaleString(undefined, { weekday: "short", hour: "numeric" })}`,
    ]);
    expect(details.every((detail) => detail.className.includes("opacity-0"))).toBe(true);
    expect(row?.textContent).not.toContain("5-hour");
    expect(row?.textContent).not.toContain("Weekly");
  });

  it("collapses to the name, both bars and the 5-hour figure, explained under the pointer, and empties a reset window's bar", () => {
    const root = rendered(
      [reading({ resets_at: "2026-10-22T19:00:00Z" }), reading({ ...WEEKLY, used_percentage: 34 })],
      "collapsed",
      "bars",
    );

    const row = root.querySelector('[data-widget-row="subscription:claude"]');
    expect((row?.querySelector('[data-widget-bar="short"]') as HTMLElement).style.width).toBe("0%");
    expect((row?.querySelector('[data-widget-bar="long"]') as HTMLElement).style.width).toBe("34%");
    expect([...(row?.querySelectorAll("[data-widget-percent]") ?? [])].map((figure) => figure.textContent)).toEqual([
      "—",
    ]);
    // Under the pointer each bar gives way to its window and reset time, set small to fit.
    expect([...(row?.querySelectorAll("[data-widget-bar-detail]") ?? [])].map((detail) => detail.textContent)).toEqual(
      [
        "5h reset",
        `wk ${new Date(WEEKLY.resets_at).toLocaleString(undefined, { weekday: "short", hour: "numeric" })}`,
      ],
    );
  });
});
