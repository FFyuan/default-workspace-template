import { describe, expect, it } from "vitest";

import { CALLS_PER_PAGE, callPage, needsMoreCalls, newerOffset, offsetAfterNewCalls, olderOffset } from "./callPages";

const calls = (count: number): number[] => Array.from({ length: count }, (_, index) => index);

describe("callPage", () => {
  it("shows the newest page first, with older pages after it", () => {
    const page = callPage(calls(45), 0, false);
    expect(page.rows).toEqual(calls(CALLS_PER_PAGE));
    expect([page.first, page.last, page.hasNewer, page.hasOlder]).toEqual([1, 20, false, true]);
  });

  it("ends on a short last page when nothing older is left to load", () => {
    const page = callPage(calls(45), 40, false);
    expect(page.rows).toEqual([40, 41, 42, 43, 44]);
    expect([page.first, page.last, page.hasNewer, page.hasOlder]).toEqual([41, 45, true, false]);
  });

  it("offers older calls past the loaded ones while the collector has more", () => {
    expect(callPage(calls(40), 20, true).hasOlder).toBe(true);
    expect(callPage(calls(40), 20, false).hasOlder).toBe(false);
  });

  it("keeps an offset past the loaded calls on the last one", () => {
    const page = callPage(calls(5), 20, false);
    expect(page.rows).toEqual([4]);
    expect(page.first).toBe(5);
  });

  it("is empty with no calls", () => {
    const page = callPage([], 0, false);
    expect([page.rows.length, page.first, page.last, page.hasNewer, page.hasOlder]).toEqual([0, 0, 0, false, false]);
  });
});

describe("paging", () => {
  it("moves a page at a time, never before the newest", () => {
    expect(olderOffset(0)).toBe(20);
    expect(newerOffset(20)).toBe(0);
    expect(newerOffset(5)).toBe(0);
  });

  it("keeps the first page on the newest calls and an older page on the rows it shows", () => {
    expect(offsetAfterNewCalls(0, 3)).toBe(0);
    expect(offsetAfterNewCalls(20, 3)).toBe(23);
  });

  it("loads more only when the page runs past the loaded calls", () => {
    expect(needsMoreCalls(50, 20)).toBe(false);
    expect(needsMoreCalls(50, 40)).toBe(true);
  });
});
