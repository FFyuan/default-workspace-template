// @vitest-environment jsdom

import m from "mithril";
import { describe, expect, it } from "vitest";

import type { LimitReading } from "../models/api";
import { providerCards } from "../models/providers";
import type { WidgetModel } from "../models/widget";
import { totalsRow } from "../testing/rows";
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

function rendered(limits: LimitReading[], mode: "expanded" | "collapsed"): HTMLElement {
  const model = { cards: providerCards(limits, [], NOW), isLive: true, isCatchingUp: false } as WidgetModel;
  const root = document.createElement("div");
  m.render(root, m(Widget, { model, mode }));
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
    expect([outer?.getAttribute("r"), outer?.getAttribute("stroke-dasharray")]).toEqual(["12.5", "34 100"]);
    expect([inner?.getAttribute("r"), inner?.getAttribute("stroke-dasharray")]).toEqual(["8.5", "80 100"]);
    expect(inner?.getAttribute("data-ring-level")).toBe("high");
    // A pair carries its provider's name, alone as beside another.
    expect(pair?.textContent).toBe("Claude");
  });

  it("names each of several pairs, and leaves a reset window's ring as a bare track", () => {
    const root = rendered(
      [reading({ resets_at: "2026-10-22T19:00:00Z" }), reading({ source: "codex", used_percentage: 18 })],
      "collapsed",
    );

    const pairs = [...root.querySelectorAll("[data-widget-rings]")];
    expect(pairs.map((pair) => pair.textContent)).toEqual(["Claude", "Codex"]);
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
    m.render(root, m(Widget, { model, mode: "collapsed" }));
    expect(root.querySelector("[data-widget-rings]")).toBeNull();
    expect(root.textContent).toContain("$9.50");
    expect(rendered([reading({})], "expanded").querySelector("[data-widget-row]")).not.toBeNull();
  });
});
