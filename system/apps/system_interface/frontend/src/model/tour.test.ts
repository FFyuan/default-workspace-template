import { describe, expect, it } from "vitest";
import {
  IDLE_TOUR,
  TOUR_START_DELAY_MS,
  TourController,
  cardShown,
  chromeAnchorShown,
  dismissBadge,
  exitTour,
  nextCard,
  previousCard,
  startTour,
} from "./tour";
import type { TourApi } from "./tour";
import { TOUR_CARDS } from "./tourCards";
import type { TourCard } from "./tourCards";

const CARDS: readonly TourCard[] = [
  { id: "a", text: "A", target: "avatar", chromeAnchor: null, image: null, link: null, buttonLabel: null },
  { id: "b", text: "B", target: null, chromeAnchor: "share", image: null, link: null, buttonLabel: null },
  { id: "c", text: "C", target: "launcher", chromeAnchor: null, image: null, link: null, buttonLabel: "Done" },
];

describe("the tour's state machine", () => {
  it("walks the cards forward and back, ends on Done with no badge, and leaves a badge on an early exit", () => {
    let state = startTour();
    expect(cardShown(state, CARDS)?.id).toBe("a");
    expect(previousCard(state)).toBe(state);
    state = nextCard(state, CARDS);
    expect(cardShown(state, CARDS)?.id).toBe("b");
    expect(chromeAnchorShown(state, CARDS)).toBe("share");
    state = previousCard(state);
    expect(cardShown(state, CARDS)?.id).toBe("a");
    expect(chromeAnchorShown(state, CARDS)).toBeNull();
    state = nextCard(nextCard(state, CARDS), CARDS);
    expect(cardShown(state, CARDS)?.id).toBe("c");
    expect(nextCard(state, CARDS)).toEqual(IDLE_TOUR);
    expect(exitTour(state)).toEqual({ phase: "exit-badge" });
    expect(cardShown(exitTour(state), CARDS)).toBeNull();
    expect(dismissBadge(exitTour(state))).toEqual(IDLE_TOUR);
    expect(exitTour(IDLE_TOUR)).toEqual(IDLE_TOUR);
    expect(nextCard(IDLE_TOUR, CARDS)).toEqual(IDLE_TOUR);
  });

  it("ships thirteen cards, each with words, ending on a Done card at the launcher", () => {
    expect(TOUR_CARDS).toHaveLength(13);
    expect(new Set(TOUR_CARDS.map((card) => card.id)).size).toBe(TOUR_CARDS.length);
    for (const card of TOUR_CARDS) expect(card.text.length).toBeGreaterThan(0);
    const last = TOUR_CARDS[TOUR_CARDS.length - 1];
    expect(last.target).toBe("launcher");
    expect(last.buttonLabel).toBe("Done");
    expect(TOUR_CARDS.filter((card) => card.image !== null).map((card) => card.id)).toEqual(["devices", "providers"]);
  });
});

/** A fake of the tour's two routes, remembering what was written. */
class FakeTourApi implements TourApi {
  isSeen = false;
  isFetchFailing = false;
  readonly writes: boolean[] = [];

  async fetchIsSeen(): Promise<boolean> {
    if (this.isFetchFailing) throw new Error("down");
    return this.isSeen;
  }

  async markSeen(): Promise<void> {
    this.writes.push(true);
    this.isSeen = true;
  }
}

function controller(api: FakeTourApi, isAllowed = true) {
  const highlights: (string | null)[] = [];
  const scheduled: { callback: () => void; delayMs: number }[] = [];
  let redraws = 0;
  const tour = new TourController({
    api,
    highlightChrome: (anchor) => highlights.push(anchor),
    isAutoStartAllowed: () => isAllowed,
    redraw: () => {
      redraws += 1;
    },
    schedule: (callback, delayMs) => scheduled.push({ callback, delayMs }),
    cards: CARDS,
  });
  return { tour, highlights, scheduled, redraws: () => redraws };
}

describe("TourController", () => {
  it("starts by itself after the pause on a fresh workspace, and records that it ran", async () => {
    const api = new FakeTourApi();
    const { tour, scheduled } = controller(api);
    await tour.maybeAutoStart();
    expect(scheduled.map((entry) => entry.delayMs)).toEqual([TOUR_START_DELAY_MS]);
    expect(tour.getState()).toEqual(IDLE_TOUR);
    scheduled[0].callback();
    expect(tour.shownCard()?.id).toBe("a");
    await Promise.resolve();
    expect(api.writes).toEqual([true]);
  });

  it("starts nothing by itself once the tour has run, when the read fails, or when the moment is wrong", async () => {
    const seen = new FakeTourApi();
    seen.isSeen = true;
    const { tour: seenTour, scheduled: seenScheduled } = controller(seen);
    await seenTour.maybeAutoStart();
    expect(seenScheduled).toEqual([]);

    const failing = new FakeTourApi();
    failing.isFetchFailing = true;
    const { tour: failingTour, scheduled: failingScheduled } = controller(failing);
    await failingTour.maybeAutoStart();
    expect(failingScheduled).toEqual([]);

    const { tour: phoneTour, scheduled: phoneScheduled } = controller(new FakeTourApi(), false);
    await phoneTour.maybeAutoStart();
    phoneScheduled[0].callback();
    expect(phoneTour.getState()).toEqual(IDLE_TOUR);
  });

  it("runs again from the launcher whatever the flag says, and rings the chrome only while a card is about it", async () => {
    const api = new FakeTourApi();
    api.isSeen = true;
    const { tour, highlights, redraws } = controller(api);
    tour.start();
    expect(tour.shownCard()?.id).toBe("a");
    expect(highlights).toEqual([]);
    tour.next();
    expect(highlights).toEqual(["share"]);
    tour.next();
    expect(highlights).toEqual(["share", null]);
    tour.back();
    expect(highlights).toEqual(["share", null, "share"]);
    tour.exit();
    expect(tour.getState()).toEqual({ phase: "exit-badge" });
    expect(highlights).toEqual(["share", null, "share", null]);
    tour.dismissBadge();
    expect(tour.getState()).toEqual(IDLE_TOUR);
    expect(redraws()).toBe(6);
    await Promise.resolve();
    expect(api.writes).toEqual([true]);
  });
});
