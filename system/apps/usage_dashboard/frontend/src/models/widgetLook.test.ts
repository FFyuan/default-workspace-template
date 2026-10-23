import { afterEach, describe, expect, it, vi } from "vitest";

import { WidgetLookPicker, asWidgetLook, lookOfSettings, lookOverrides, readWidgetLook } from "./widgetLook";
import type { ChannelLike } from "./widgetLook";

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

describe("the widget's look", () => {
  it("reads known choices from a query, a message, or the settings, each unknown one taking its default", () => {
    expect(lookOverrides("?variant=bars&size=huge&detail=more&tray=stacked")).toEqual({
      variant: "bars",
      detail: "more",
      tray: "stacked",
    });
    expect(lookOverrides("")).toEqual({});
    expect(asWidgetLook({ variant: "rings", size: "small", detail: "less", tray: "ring" })).toEqual({
      variant: "rings",
      size: "small",
      detail: "less",
      tray: "ring",
    });
    expect(asWidgetLook({ variant: "rings", size: "small" })).toBeNull();
    expect(
      lookOfSettings({ widget_variant: "bars", widget_size: "huge", widget_detail: "less", widget_tray: "sparkle" }),
    ).toEqual({ variant: "bars", size: "medium", detail: "less", tray: "rings" });
  });

  it("reads the stored look, and nothing when the settings cannot be read", async () => {
    stubServer({ widget_variant: "bars", widget_size: "large", widget_detail: "more", widget_tray: "numbers" });
    expect(await readWidgetLook()).toEqual({ variant: "bars", size: "large", detail: "more", tray: "numbers" });
    stubServer({}, 503);
    expect(await readWidgetLook()).toBeNull();
  });

  it("saves a change to one part and announces the whole look, and puts the old one back when refused", async () => {
    const { channel, sent } = recordingChannel();
    const placeInTray = vi.fn();
    const picker = new WidgetLookPicker({ redraw: () => undefined, openChannel: () => channel, placeInTray });
    const posted = stubServer({
      widget_variant: "rings",
      widget_size: "medium",
      widget_detail: "standard",
      widget_tray: "rings",
    });
    await picker.load();
    expect(picker.look).toEqual({ variant: "rings", size: "medium", detail: "standard", tray: "rings" });

    await picker.select({ size: "large" });
    expect(picker.look).toEqual({ variant: "rings", size: "large", detail: "standard", tray: "rings" });
    expect(posted).toEqual([
      { widget_variant: "rings", widget_size: "large", widget_detail: "standard", widget_tray: "rings" },
    ]);
    expect(sent).toEqual([{ variant: "rings", size: "large", detail: "standard", tray: "rings" }]);
    expect(placeInTray).not.toHaveBeenCalled();

    // A tray design is seen only in the tray: picking one puts this client's widget there.
    await picker.select({ tray: "stacked" });
    expect(picker.look?.tray).toBe("stacked");
    expect(placeInTray).toHaveBeenCalledTimes(1);

    stubServer({}, 500);
    await picker.select({ variant: "bars" });
    expect(picker.look?.variant).toBe("rings");
    expect(picker.errorMessage).toContain("Could not change the widget");
    expect(sent).toHaveLength(2);
    expect(placeInTray).toHaveBeenCalledTimes(1);
  });
});
