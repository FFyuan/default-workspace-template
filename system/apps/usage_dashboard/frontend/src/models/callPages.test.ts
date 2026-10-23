import { describe, expect, it } from "vitest";

import { pageCount, pageNumbers, pageOffset, pageRange } from "./callPages";

describe("pages", () => {
  it("fills 20 calls to a page, with one page even with no calls", () => {
    expect([pageCount(0), pageCount(20), pageCount(21), pageCount(45)]).toEqual([1, 1, 2, 3]);
  });

  it("skips the pages before it", () => {
    expect([pageOffset(1), pageOffset(3)]).toEqual([0, 40]);
  });

  it("names the calls a page shows, ending short on the last page", () => {
    expect(pageRange(1, 45)).toEqual([1, 20]);
    expect(pageRange(3, 45)).toEqual([41, 45]);
    expect(pageRange(1, 0)).toEqual([0, 0]);
  });
});

describe("pageNumbers", () => {
  it("lists every page when there are few", () => {
    expect(pageNumbers(1, 1)).toEqual([1]);
    expect(pageNumbers(2, 5)).toEqual([1, 2, 3, 4, 5]);
  });

  it("keeps the first and last pages and the current one's neighbours, with gaps between", () => {
    expect(pageNumbers(10, 20)).toEqual([1, "gap", 9, 10, 11, "gap", 20]);
  });

  it("keeps the row's length near either end", () => {
    expect(pageNumbers(1, 20)).toEqual([1, 2, 3, 4, "gap", 20]);
    expect(pageNumbers(20, 20)).toEqual([1, "gap", 17, 18, 19, 20]);
  });

  it("shows a single left-out page instead of a gap", () => {
    expect(pageNumbers(4, 20)).toEqual([1, 2, 3, 4, 5, "gap", 20]);
  });
});
