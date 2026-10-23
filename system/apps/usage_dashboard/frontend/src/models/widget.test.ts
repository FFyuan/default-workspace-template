import { afterEach, describe, expect, it, vi } from "vitest";

import type { LimitReading } from "./api";
import { totalsRow } from "../testing/rows";
import { providerCards } from "./providers";
import { WidgetModel, widgetPill, widgetRows } from "./widget";

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

const API_SPEND = totalsRow({
  group: { provider: "anthropic", billing_mode: "API_KEY", cost_provenance: "ESTIMATED" },
  calls: 12,
  cost_usd: "142.31",
});

describe("widgetRows", () => {
  it("gives a subscription its shortest window as the bar and its longest beside it, and an API its spend", () => {
    const cards = providerCards([reading({}), reading({ ...WEEKLY, used_percentage: 34 })], [API_SPEND], NOW);

    const rows = widgetRows(cards);

    expect(rows.map((row) => [row.kind, row.name])).toEqual([
      ["limit", "Claude"],
      ["spend", "Anthropic"],
    ]);
    const [limit, spend] = rows;
    if (limit.kind !== "limit" || spend.kind !== "spend") throw new Error("rows out of order");
    expect([limit.primary.label, limit.primary.usedPercent, limit.secondary?.usedPercent]).toEqual([
      "5-hour limit",
      61,
      34,
    ]);
    expect(limit.tooltip).toContain("5-hour limit: 61% used, resets");
    expect(limit.tooltip).toContain("as of");
    expect(spend.spend).toBe("~$142.31");
  });

  it("draws nothing for a provider with no data, and one window alone with no figure beside it", () => {
    expect(widgetRows([])).toEqual([]);
    const [row] = widgetRows(providerCards([reading({})], [], NOW));
    expect(row.kind === "limit" ? row.secondary : "not a limit row").toBeNull();
  });
});

describe("widgetPill", () => {
  it("names the most used subscription window not reset since its reading, at its level", () => {
    const cards = providerCards(
      [
        reading({ used_percentage: 96, resets_at: "2026-10-22T19:00:00Z" }),
        reading({ ...WEEKLY, used_percentage: 80 }),
        reading({ source: "codex", used_percentage: 18 }),
      ],
      [API_SPEND],
      NOW,
    );

    // The 96% window reset at 19:00, before now: it is left out, and the weekly 80% is the most used.
    expect(widgetPill(cards)).toMatchObject({ text: "Claude 80%", level: "high" });
  });

  it("falls back to this month's total spend with no subscription, and to nothing with no usage", () => {
    const openai = totalsRow({ group: { provider: "openai", billing_mode: "API_KEY" }, cost_usd: "22.90" });
    expect(widgetPill(providerCards([], [API_SPEND, openai], NOW))).toMatchObject({ text: "$165.21", level: "ok" });
    expect(widgetPill([])).toBeNull();
  });
});

describe("WidgetModel", () => {
  /** A collector that answers ``limits``, no totals, and ``health``; ``status`` for every read when it is set. */
  function stubCollector(limits: LimitReading[], isCatchingUp: boolean, status: number | null = null): void {
    vi.stubGlobal("fetch", async (url: string) => {
      if (status !== null) return new Response(JSON.stringify({ detail: "down" }), { status });
      const answer = url.includes("/limits")
        ? { limits }
        : url.includes("/totals")
          ? { rows: [] }
          : { status: "ok", catching_up: isCatchingUp };
      return new Response(JSON.stringify(answer), { status: 200 });
    });
  }

  function model(): WidgetModel {
    const stream = { addEventListener: () => undefined, onopen: null, onerror: null, close: () => undefined };
    return new WidgetModel({ now: () => NOW, redraw: () => undefined, openStream: () => stream });
  }

  afterEach(() => vi.unstubAllGlobals());

  it("is empty only once a read found no usage and the collector is not still indexing", async () => {
    const widget = model();
    expect(widget.isEmpty).toBe(false);
    stubCollector([], false);
    await widget.refresh();
    expect(widget.isEmpty).toBe(true);

    stubCollector([], true);
    await widget.refresh();
    expect([widget.isEmpty, widget.isCatchingUp]).toEqual([false, true]);

    stubCollector([reading({})], false);
    await widget.refresh();
    expect(widget.isEmpty).toBe(false);
    expect(widgetRows(widget.cards ?? []).map((row) => row.name)).toEqual(["Claude"]);
  });

  it("keeps the last figures when the collector cannot be reached", async () => {
    const widget = model();
    stubCollector([reading({})], false);
    await widget.refresh();
    stubCollector([], false, 503);
    await widget.refresh();
    expect(widget.isCollectorDown).toBe(true);
    expect(widget.cards).toHaveLength(1);
  });
});
