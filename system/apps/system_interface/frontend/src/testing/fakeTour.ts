/**
 * A fake of the show-around tour's two routes (``GET`` and ``POST /api/tour``) for the controller and view tests:
 * the flag is set by hand, a read can be made to fail, and every write is recorded.
 */

import type { TourApi } from "../model/tour";

export class FakeTourApi implements TourApi {
  isSeen = false;
  isFetchFailing = false;
  readonly writes: boolean[] = [];

  constructor(options: { isSeen?: boolean } = {}) {
    this.isSeen = options.isSeen ?? false;
  }

  async fetchIsSeen(): Promise<boolean> {
    if (this.isFetchFailing) throw new Error("down");
    return this.isSeen;
  }

  async markSeen(): Promise<void> {
    this.writes.push(true);
    this.isSeen = true;
  }
}
