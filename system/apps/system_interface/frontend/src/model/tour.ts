/**
 * The show-around tour (the new-onboarding spec, sections 2.5 and 3.4): a pure state machine over the cards, and
 * the controller that runs it in the shell. The controller reads and writes the workspace's one tour flag through
 * ``/api/tour``, starts the tour by itself on a fresh workspace (after a pause, for the owner, on the desktop
 * layout), runs it again from the launcher's "Show me around" row, and tells the Imbue Studio chrome which of its
 * controls to ring while a card is about one.
 */

import { apiUrl } from "@imbue/workspace-ui/src/base-path";
import { errorDetailFromResponse, postJson } from "@imbue/workspace-ui/src/models/http";
import type { ChromeAnchor, TourCard } from "./tourCards";
import { TOUR_CARDS } from "./tourCards";

export type TourState =
  { readonly phase: "idle" } | { readonly phase: "card"; readonly index: number } | { readonly phase: "exit-badge" };

export const IDLE_TOUR: TourState = { phase: "idle" };

/** How long after the desktop first renders the tour begins on a fresh workspace. */
export const TOUR_START_DELAY_MS = 3000;

export function startTour(): TourState {
  return { phase: "card", index: 0 };
}

export function nextCard(state: TourState, cards: readonly TourCard[] = TOUR_CARDS): TourState {
  if (state.phase !== "card") return state;
  return state.index + 1 < cards.length ? { phase: "card", index: state.index + 1 } : IDLE_TOUR;
}

export function previousCard(state: TourState): TourState {
  if (state.phase !== "card" || state.index === 0) return state;
  return { phase: "card", index: state.index - 1 };
}

/** Leaving early shows the exit badge; "Done" on the last card goes through ``nextCard`` and shows none. */
export function exitTour(state: TourState): TourState {
  return state.phase === "card" ? { phase: "exit-badge" } : IDLE_TOUR;
}

export function dismissBadge(state: TourState): TourState {
  return state.phase === "exit-badge" ? IDLE_TOUR : state;
}

export function cardShown(state: TourState, cards: readonly TourCard[] = TOUR_CARDS): TourCard | null {
  return state.phase === "card" ? cards[state.index] : null;
}

/** The chrome control the shown card is about, or null (no card, or a card about the shell's own things). */
export function chromeAnchorShown(state: TourState, cards: readonly TourCard[] = TOUR_CARDS): ChromeAnchor | null {
  return cardShown(state, cards)?.chromeAnchor ?? null;
}

/** The routes the controller calls, injectable so it is tested against a fake. */
export interface TourApi {
  /** Whether the tour has run in this workspace. */
  fetchIsSeen(): Promise<boolean>;
  /** Record that it has. */
  markSeen(): Promise<void>;
}

export async function fetchTourIsSeen(): Promise<boolean> {
  const response = await fetch(apiUrl("/api/tour"));
  if (!response.ok) throw new Error(await errorDetailFromResponse(response));
  const body = (await response.json()) as { is_seen?: unknown };
  return body.is_seen === true;
}

export async function markTourSeen(): Promise<void> {
  await postJson<unknown>(apiUrl("/api/tour"), { is_seen: true });
}

export const TOUR_API: TourApi = { fetchIsSeen: fetchTourIsSeen, markSeen: markTourSeen };

export interface TourControllerDependencies {
  readonly api: TourApi;
  /** Ask the Imbue Studio chrome to ring one of its controls, or clear the ring. */
  readonly highlightChrome: (anchor: ChromeAnchor | null) => void;
  /** Whether the tour may begin by itself right now: the desktop layout, no solo window, the owner looking. */
  readonly isAutoStartAllowed: () => boolean;
  readonly redraw: () => void;
  readonly schedule?: (callback: () => void, delayMs: number) => void;
  readonly cards?: readonly TourCard[];
}

export class TourController {
  private state: TourState = IDLE_TOUR;
  private lastAnchor: ChromeAnchor | null = null;
  private readonly cards: readonly TourCard[];
  private readonly schedule: (callback: () => void, delayMs: number) => void;

  constructor(private readonly deps: TourControllerDependencies) {
    this.cards = deps.cards ?? TOUR_CARDS;
    this.schedule = deps.schedule ?? ((callback, delayMs) => setTimeout(callback, delayMs));
  }

  getState(): TourState {
    return this.state;
  }

  getCards(): readonly TourCard[] {
    return this.cards;
  }

  /** The card on screen, or null. */
  shownCard(): TourCard | null {
    return cardShown(this.state, this.cards);
  }

  /** Begin the tour by itself on a fresh workspace: once, after the pause, when nothing says not to. A read that
   *  fails starts nothing; the launcher row still works. */
  async maybeAutoStart(): Promise<void> {
    let isSeen: boolean;
    try {
      isSeen = await this.deps.api.fetchIsSeen();
    } catch (error) {
      console.warn("[si-tour] could not read whether the tour has run", error);
      return;
    }
    if (isSeen) return;
    this.schedule(() => {
      if (this.state.phase !== "idle" || !this.deps.isAutoStartAllowed()) return;
      this.start();
    }, TOUR_START_DELAY_MS);
  }

  /** Start from the first card, whether or not the tour has run before; the flag is written as it starts. */
  start(): void {
    this.apply(startTour());
    void this.deps.api.markSeen().catch((error: unknown) => {
      console.warn("[si-tour] could not record that the tour ran", error);
    });
  }

  next(): void {
    this.apply(nextCard(this.state, this.cards));
  }

  back(): void {
    this.apply(previousCard(this.state));
  }

  exit(): void {
    this.apply(exitTour(this.state));
  }

  dismissBadge(): void {
    this.apply(dismissBadge(this.state));
  }

  private apply(next: TourState): void {
    this.state = next;
    const anchor = chromeAnchorShown(next, this.cards);
    if (anchor !== this.lastAnchor) {
      this.lastAnchor = anchor;
      this.deps.highlightChrome(anchor);
    }
    this.deps.redraw();
  }
}
