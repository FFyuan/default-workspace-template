// @vitest-environment jsdom
import "@imbue/workspace-ui/src/testing/dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { detailOf, listingOf, rowOf } from "../testing/records";
import { AppModel, IDLE_REFRESH_MS, RUNNING_REFRESH_MS, type AppHost } from "./App";

const requests: string[] = [];
let answer: () => unknown = () => listingOf([]);

function host(): AppHost & { locations: [string, string][]; navigated: string[] } {
  const locations: [string, string][] = [];
  const navigated: string[] = [];
  return {
    locations,
    navigated,
    reportLocation: (path, title) => locations.push([path, title]),
    startWithText: () => undefined,
    confirmRemove: () => Promise.resolve(true),
    navigate: (path) => navigated.push(path),
  };
}

/** Let every pending fetch and the continuations after it run. */
async function settle(): Promise<void> {
  for (let i = 0; i < 5; i += 1) await Promise.resolve();
}

beforeEach(() => {
  vi.useFakeTimers();
  requests.length = 0;
  answer = () => listingOf([]);
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    requests.push(`${init?.method ?? "GET"} ${url}`);
    const body = answer();
    return Promise.resolve(
      new Response(body === undefined ? null : JSON.stringify(body), {
        status: body === undefined ? 204 : 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("AppModel", () => {
  it("reports the page's location at once and refines the title once the routine is known", async () => {
    answer = () => detailOf({ row: rowOf({ title: "News sync" }) });
    const page = host();
    const model = new AppModel("/news-sync", page, () => undefined);
    expect(page.locations).toEqual([["/news-sync", "news-sync"]]);
    await model.load();
    expect(page.locations[page.locations.length - 1]).toEqual(["/news-sync", "News sync"]);
    expect(model.loaded.kind).toBe("routine");
    model.dispose();
  });

  it("re-reads the list every 30 seconds, every 5 while a run is going, and never under the editor", async () => {
    const model = new AppModel("/", host(), () => undefined);
    await model.load();
    expect(requests).toEqual(["GET /api/routines"]);

    await vi.advanceTimersByTimeAsync(IDLE_REFRESH_MS - 1);
    expect(requests).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);
    await settle();
    expect(requests).toHaveLength(2);

    answer = () => listingOf([rowOf({ is_running: true })]);
    await vi.advanceTimersByTimeAsync(IDLE_REFRESH_MS);
    await settle();
    expect(requests).toHaveLength(3);
    await vi.advanceTimersByTimeAsync(RUNNING_REFRESH_MS);
    await settle();
    expect(requests).toHaveLength(4);

    // An open editor holds the polling; closing it lets the next tick read again.
    model.scheduleForm = { mode: "every", count: "1", unit: "h", at: "", days: [], dayOfMonth: "", once: "" };
    await vi.advanceTimersByTimeAsync(RUNNING_REFRESH_MS * 3);
    await settle();
    expect(requests).toHaveLength(4);
    model.scheduleForm = null;
    await vi.advanceTimersByTimeAsync(RUNNING_REFRESH_MS);
    await settle();
    expect(requests).toHaveLength(5);

    model.dispose();
    await vi.advanceTimersByTimeAsync(IDLE_REFRESH_MS * 2);
    await settle();
    expect(requests).toHaveLength(5);
  });

  it("keeps a failed read on screen with its reason", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve(new Response(JSON.stringify({ detail: "the ledger is unreadable" }), { status: 500 })),
    );
    const model = new AppModel("/", host(), () => undefined);
    await model.load();
    expect(model.loaded).toEqual({ kind: "error", message: "the ledger is unreadable" });
    model.dispose();
  });

  it("removes the routine and leaves for the list without reading the removed page", async () => {
    const page = host();
    answer = () => detailOf();
    const model = new AppModel("/news-sync", page, () => undefined);
    await model.load();
    answer = () => undefined;

    model.remove();
    await settle();

    expect(requests).toEqual(["GET /api/routines/news-sync", "DELETE /api/routines/news-sync"]);
    expect(page.navigated).toEqual(["/"]);
    expect(model.loaded.kind).toBe("routine");
  });
});
