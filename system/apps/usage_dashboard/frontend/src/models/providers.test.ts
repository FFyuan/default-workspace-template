import { describe, expect, it } from "vitest";

import type { LimitReading } from "./api";
import { totalsRow } from "../testing/rows";
import { limitLevel, providerCards, windowLabel } from "./providers";

const NOW = new Date("2026-10-22T20:00:00Z");

function reading(patch: Partial<LimitReading>): LimitReading {
  return {
    source: "claude",
    window: "five_hour",
    label: "5h",
    used_percentage: 28,
    resets_at: "2026-10-22T22:30:00Z",
    window_seconds: 18_000,
    observed_at: "2026-10-22T19:45:00Z",
    ...patch,
  };
}

describe("providerCards", () => {
  it("gives a subscription card per reporting source, shortest window first", () => {
    const [card] = providerCards(
      [reading({ window: "seven_day", label: "7d", used_percentage: 8, window_seconds: 604_800 }), reading({})],
      [],
      NOW,
    );

    expect(card.kind).toBe("subscription");
    if (card.kind !== "subscription") return;
    expect(card.title).toBe("Claude subscription");
    expect(card.windows.map((window) => [window.label, window.usedPercent])).toEqual([
      ["5-hour limit", 28],
      ["Weekly limit", 8],
    ]);
    expect(card.observedAt).toEqual(new Date("2026-10-22T19:45:00Z"));
  });

  it("shows a window whose reset has passed since the reading as reset", () => {
    const [card] = providerCards([reading({ used_percentage: 96, resets_at: "2026-10-22T19:50:00Z" })], [], NOW);

    if (card.kind !== "subscription") throw new Error("expected a subscription card");
    expect(card.windows[0]).toMatchObject({ usedPercent: 0, isResetSinceReading: true, level: "ok" });
  });

  it("drops a source whose last reading is over a week old", () => {
    expect(providerCards([reading({ observed_at: "2026-10-14T19:00:00Z" })], [], NOW)).toEqual([]);
  });

  it("keeps a subscription's calls off the spend cards", () => {
    const cards = providerCards(
      [reading({})],
      [totalsRow({ group: { provider: "anthropic", billing_mode: "SUBSCRIPTION" }, calls: 9, cost_usd: "3.5" })],
      NOW,
    );

    expect(cards).toHaveLength(1);
    expect(cards[0]).toMatchObject({ kind: "subscription" });
  });

  it("gives a spend card per provider used without a subscription, counting unknown costs", () => {
    const cards = providerCards(
      [],
      [
        totalsRow({
          group: { provider: "anthropic", billing_mode: "API_KEY", cost_provenance: "REPORTED" },
          calls: 4,
          cost_usd: "2",
        }),
        totalsRow({
          group: { provider: "anthropic", billing_mode: "UNKNOWN", cost_provenance: "ESTIMATED" },
          calls: 3,
          cost_usd: "1",
        }),
        totalsRow({
          group: { provider: "openai", billing_mode: "API_KEY", cost_provenance: "ESTIMATED" },
          calls: 1,
          cost_usd: "0.5",
        }),
      ],
      NOW,
    );

    expect(cards.map((card) => card.title)).toEqual(["Anthropic API", "OpenAI API"]);
    expect(cards[0]).toMatchObject({ kind: "spend", spend: 2, calls: 7, unknownCostCalls: 3, isEstimated: false });
    expect(cards[1]).toMatchObject({ isEstimated: true });
  });
});

describe("windowLabel", () => {
  it("names a window by its length, and by its label without one", () => {
    expect(windowLabel({ window: "five_hour", label: "5h", window_seconds: 18_000 })).toBe("5-hour limit");
    expect(windowLabel({ window: "seven_day", label: "7d", window_seconds: 604_800 })).toBe("Weekly limit");
    expect(windowLabel({ window: "overage", label: null, window_seconds: null })).toBe("overage limit");
  });
});

describe("limitLevel", () => {
  it("is high from 75% and critical from 90%", () => {
    expect([74, 75, 89, 90].map(limitLevel)).toEqual(["ok", "high", "high", "critical"]);
  });
});
