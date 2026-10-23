/**
 * Pages of the latest calls.
 *
 * A page is a window into the loaded calls, newest first, that starts at an offset. Calls that stream in while
 * an older page is shown push the offset along with them, so the rows being read stay put; only the first
 * page takes new calls in.
 */

export const CALLS_PER_PAGE = 20;

export interface CallPage<T> {
  rows: readonly T[];
  /** 1-based positions of the first and last row shown. */
  first: number;
  last: number;
  hasNewer: boolean;
  hasOlder: boolean;
}

/** The page starting at ``offset``; ``hasMoreToLoad`` says whether older calls exist beyond those loaded. */
export function callPage<T>(calls: readonly T[], offset: number, hasMoreToLoad: boolean): CallPage<T> {
  const start = Math.min(Math.max(offset, 0), Math.max(calls.length - 1, 0));
  const rows = calls.slice(start, start + CALLS_PER_PAGE);
  return {
    rows,
    first: rows.length === 0 ? 0 : start + 1,
    last: start + rows.length,
    hasNewer: start > 0,
    hasOlder: start + CALLS_PER_PAGE < calls.length || hasMoreToLoad,
  };
}

/** The offset after ``added`` calls arrived above it: the first page stays on the newest, others stay put. */
export function offsetAfterNewCalls(offset: number, added: number): number {
  return offset === 0 ? 0 : offset + added;
}

/** The offset one page newer. */
export function newerOffset(offset: number): number {
  return Math.max(offset - CALLS_PER_PAGE, 0);
}

/** The offset one page older. */
export function olderOffset(offset: number): number {
  return offset + CALLS_PER_PAGE;
}

/** Whether showing the page at ``offset`` needs more calls than are loaded. */
export function needsMoreCalls(loaded: number, offset: number): boolean {
  return offset + CALLS_PER_PAGE > loaded;
}
