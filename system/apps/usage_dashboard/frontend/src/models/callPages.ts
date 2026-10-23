/** Numbered pages of the latest calls, newest first. */

export const CALLS_PER_PAGE = 20;

/** How many pages ``total`` calls fill; one page even with none. */
export function pageCount(total: number): number {
  return Math.max(1, Math.ceil(total / CALLS_PER_PAGE));
}

/** How many of the newest calls page ``page`` (from 1) skips. */
export function pageOffset(page: number): number {
  return (page - 1) * CALLS_PER_PAGE;
}

/** 1-based positions of the first and last call on ``page``; [0, 0] with none. */
export function pageRange(page: number, total: number): [number, number] {
  if (total === 0) return [0, 0];
  return [pageOffset(page) + 1, Math.min(pageOffset(page) + CALLS_PER_PAGE, total)];
}

/**
 * The page numbers to offer around ``current``: always the first and last, the current one with a neighbour on
 * each side, and "gap" where numbers are left out. A gap never stands for a single page, which is shown instead.
 */
export function pageNumbers(current: number, count: number): (number | "gap")[] {
  const shown = new Set([1, count, current - 1, current, current + 1].filter((page) => page >= 1 && page <= count));
  // Near either end, show enough pages that the row keeps its length.
  if (current <= 3) for (let page = 2; page <= Math.min(4, count); page++) shown.add(page);
  if (current >= count - 2) for (let page = Math.max(count - 3, 1); page < count; page++) shown.add(page);
  const pages = [...shown].sort((a, b) => a - b);
  const items: (number | "gap")[] = [];
  for (const [index, page] of pages.entries()) {
    const previous = pages[index - 1];
    if (previous !== undefined && page - previous === 2) items.push(previous + 1);
    else if (previous !== undefined && page - previous > 2) items.push("gap");
    items.push(page);
  }
  return items;
}
