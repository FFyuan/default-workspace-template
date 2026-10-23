import { afterEach, describe, expect, it, vi } from "vitest";

import { WidgetVariantPicker, asWidgetVariant, readWidgetVariant, variantFromQuery } from "./widgetVariant";
import type { ChannelLike } from "./widgetVariant";

/** A Usage server that answers its settings with ``stored`` and records what is posted; ``status`` for every request
 *  when it is set. */
function stubServer(stored: unknown, status: number | null = null): unknown[] {
  const posted: unknown[] = [];
  vi.stubGlobal("fetch", async (_url: string, init?: RequestInit) => {
    if (status !== null) return new Response(JSON.stringify({ detail: "refused" }), { status });
    if (init?.method === "POST") {
      const body: unknown = JSON.parse(String(init.body));
      posted.push(body);
      return new Response(JSON.stringify(body), { status: 200 });
    }
    return new Response(JSON.stringify(stored), { status: 200 });
  });
  return posted;
}

function recordingChannel(): { channel: ChannelLike; sent: unknown[] } {
  const sent: unknown[] = [];
  return { channel: { postMessage: (message) => sent.push(message), onmessage: null, close: () => undefined }, sent };
}

afterEach(() => vi.unstubAllGlobals());

describe("widget variants", () => {
  it("reads a known version from a query or a value, and nothing else", () => {
    expect(variantFromQuery("?variant=bars")).toBe("bars");
    expect([variantFromQuery("?variant=dials"), variantFromQuery("")]).toEqual([null, null]);
    expect([asWidgetVariant("rings"), asWidgetVariant(3)]).toEqual(["rings", null]);
  });

  it("reads the stored version, and nothing when the settings cannot be read or name an unknown one", async () => {
    stubServer({ widget_variant: "bars" });
    expect(await readWidgetVariant()).toBe("bars");
    stubServer({ widget_variant: "dials" });
    expect(await readWidgetVariant()).toBeNull();
    stubServer({}, 503);
    expect(await readWidgetVariant()).toBeNull();
  });

  it("saves a pick and announces it, and puts the old one back when the save is refused", async () => {
    const { channel, sent } = recordingChannel();
    const picker = new WidgetVariantPicker({ redraw: () => undefined, openChannel: () => channel });
    const posted = stubServer({ widget_variant: "rings" });
    await picker.load();
    expect(picker.variant).toBe("rings");

    await picker.select("bars");
    expect([picker.variant, posted, sent]).toEqual(["bars", [{ widget_variant: "bars" }], [{ variant: "bars" }]]);

    stubServer({}, 500);
    await picker.select("rings");
    expect(picker.variant).toBe("bars");
    expect(picker.errorMessage).toContain("Could not change the widget");
    expect(sent).toHaveLength(1);
  });
});
