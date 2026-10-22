/**
 * The show-around tour's test doubles: a fake of its two routes (``GET`` and ``POST /api/tour``), whose flag is set
 * by hand, whose read can be made to fail, and whose every write is recorded; and a short list of cards, one of
 * each kind the tour draws.
 */

import type { TourApi } from "../model/tour";
import type { TourCard } from "../model/tourCards";

/** Three cards: one popped out of the avatar, one about a chrome control with a link, one at the launcher with a
 *  picture and the Done label. */
export const FAKE_TOUR_CARDS: readonly TourCard[] = [
  { id: "a", text: "Hello there.", target: "avatar", chromeAnchor: null, image: null, link: null, buttonLabel: null },
  {
    id: "b",
    text: "About sharing.",
    target: null,
    chromeAnchor: "share",
    image: null,
    link: { label: "Join us", url: "https://example.com/discord" },
    buttonLabel: null,
  },
  {
    id: "c",
    text: "Devices.",
    target: "launcher",
    chromeAnchor: null,
    image: { url: "https://cdn.example/devices.png", alt: "devices" },
    link: null,
    buttonLabel: "Done",
  },
];

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
