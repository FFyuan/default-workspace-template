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

const STORED = {
  widget_variant: "rings",
  widget_size: "medium",
  widget_detail: "standard",
  widget_tray: "rings",
  widget_taskbar: "tray",
  widget_toolbar: "chip",
};
const LOOK = { variant: "rings", size: "medium", detail: "standard", tray: "rings", taskbar: "tray", toolbar: "chip" };

describe("the widget's look", () => {
  it("reads known choices from a query, a message, or the settings, each unknown one taking its default", () => {
    expect(lookOverrides("?variant=bars&size=huge&detail=more&tray=stacked&toolbar=meters")).toEqual({
      variant: "bars",
      detail: "more",
      tray: "stacked",
      toolbar: "meters",
    });
    expect(lookOverrides("?toolbar=sparkle")).toEqual({});
    expect(asWidgetLook({ ...LOOK, size: "small", taskbar: "toolbar", toolbar: "inline" })).toEqual({
      ...LOOK,
      size: "small",
      taskbar: "toolbar",
      toolbar: "inline",
    });
    expect(asWidgetLook({ ...LOOK, taskbar: "dock" })).toBeNull();
    expect(asWidgetLook({ variant: "rings", size: "small" })).toBeNull();
    // An older file, from before the taskbar's row, reads whole with the defaults for the parts it lacks.
    expect(
      lookOfSettings({
        widget_variant: "bars",
        widget_size: "huge",
        widget_detail: "less",
        widget_tray: "sparkle",
      } as unknown as typeof STORED),
    ).toEqual({ ...LOOK, variant: "bars", detail: "less" });
  });

  it("reads the stored look, and nothing when the settings cannot be read", async () => {
    stubServer({ ...STORED, widget_variant: "bars", widget_taskbar: "toolbar", widget_toolbar: "line" });
    expect(await readWidgetLook()).toEqual({ ...LOOK, variant: "bars", taskbar: "toolbar", toolbar: "line" });
    stubServer({}, 503);
    expect(await readWidgetLook()).toBeNull();
  });

  it("saves a change to one part and announces the whole look, and puts the old one back when refused", async () => {
    const { channel, sent } = recordingChannel();
    const placeInTaskbar = vi.fn();
    const picker = new WidgetLookPicker({ redraw: () => undefined, openChannel: () => channel, placeInTaskbar });
    const posted = stubServer(STORED);
    await picker.load();
    expect(picker.look).toEqual(LOOK);

    await picker.select({ size: "large" });
    expect(picker.look).toEqual({ ...LOOK, size: "large" });
    expect(posted).toEqual([{ ...STORED, widget_size: "large" }]);
    expect(sent).toEqual([{ ...LOOK, size: "large" }]);
    expect(placeInTaskbar).not.toHaveBeenCalled();

    stubServer({}, 500);
    await picker.select({ variant: "bars" });
    expect(picker.look?.variant).toBe("rings");
    expect(picker.errorMessage).toContain("Could not change the widget");
    expect(sent).toHaveLength(1);
    expect(placeInTaskbar).not.toHaveBeenCalled();
  });

  it("puts this client's widget where in the taskbar was picked, on a pick of the spot or of a design there", async () => {
    const { channel } = recordingChannel();
    const placeInTaskbar = vi.fn();
    const picker = new WidgetLookPicker({ redraw: () => undefined, openChannel: () => channel, placeInTaskbar });
    stubServer(STORED);
    await picker.load();

    await picker.select({ tray: "stacked" });
    await picker.select({ taskbar: "toolbar" });
    await picker.select({ toolbar: "meters" });
    expect(picker.look).toEqual({ ...LOOK, tray: "stacked", taskbar: "toolbar", toolbar: "meters" });
    expect(placeInTaskbar.mock.calls).toEqual([["tray"], ["toolbar"], ["toolbar"]]);
  });
});
