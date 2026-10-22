/**
 * The show-around tour's cards (the new-onboarding spec, section 2.5): what each says, what it points at, and the
 * picture, link, or action it carries. A card points at something the shell draws itself (``target``), names a
 * control of the Imbue Studio chrome for the chrome to ring (``chromeAnchor``), or neither, in which case it pops
 * out of the agent's avatar. A card with an action does it as Next is pressed. The pictures are hosted under
 * content-addressed names; nothing is bundled.
 */

/** What the shell draws that a card can sit beside: the agent's avatar, the desktop's shortcuts, or the launcher. */
export type TourTarget = "avatar" | "shortcuts" | "launcher";

/** A control of the Imbue Studio chrome a card talks about, as the embed contract names it (minds:highlight-chrome). */
export type ChromeAnchor = "workspace-switcher" | "permissions" | "settings" | "share" | "help";

/** What the shell does as a card's Next is pressed: snap the pinned chat window to the right half of the desktop. */
export type TourAction = "snap-chat-right";

/** The app whose pinned window the chat card's action snaps. */
export const CHAT_APP_NAME = "chat";

export interface TourImage {
  readonly url: string;
  readonly alt: string;
}

export interface TourLink {
  readonly label: string;
  readonly url: string;
}

export interface TourCard {
  readonly id: string;
  readonly text: string;
  /** Lines listed under the text, when the card has them. */
  readonly bullets: readonly string[] | null;
  readonly target: TourTarget | null;
  readonly chromeAnchor: ChromeAnchor | null;
  readonly image: TourImage | null;
  readonly link: TourLink | null;
  readonly action: TourAction | null;
  /** The label of the card's forward button; "Next" when null, "Done" on the last card. */
  readonly buttonLabel: string | null;
}

const ONBOARDING_MEDIA_BASE_URL = "https://onboarding-media.imbueminds.com";

function card(fields: Partial<TourCard> & Pick<TourCard, "id" | "text">): TourCard {
  return {
    bullets: null,
    target: null,
    chromeAnchor: null,
    image: null,
    link: null,
    action: null,
    buttonLabel: null,
    ...fields,
  };
}

export const TOUR_CARDS: readonly TourCard[] = [
  card({ id: "intro", text: "Let me show you around. It only takes a minute.", target: "avatar" }),
  card({ id: "agent", text: "I’m your Studio agent. Click me any time to open our chat.", target: "avatar" }),
  card({
    id: "workspace",
    text:
      "This is your workspace: a virtual computer where everything is customizable, from the apps you build to " +
      "the interface itself.",
    chromeAnchor: "workspace-switcher",
  }),
  card({
    id: "chat-window",
    text: "Our chat is a window like any other. Let’s make it smaller so you can see the rest of your desktop.",
    target: "avatar",
    action: "snap-chat-right",
  }),
  card({
    id: "apps",
    text: "Your apps live here. Use them inside the workspace, or drag them onto your own desktop.",
    target: "shortcuts",
  }),
  card({
    id: "connect",
    text: "Securely connect your data:",
    bullets: [
      "Services like Gmail, Slack, and 100’s more",
      "Sync folders on your computer, or in Google Drive, Dropbox, etc",
    ],
    chromeAnchor: "permissions",
  }),
  card({
    id: "security",
    text:
      "Your workspace is encrypted and backed up automatically, so your data is safe and only reachable by the " +
      "people you share it with.",
    chromeAnchor: "settings",
  }),
  card({
    id: "share",
    text: "Share your whole workspace, or any app you build, with your team, friends, or family.",
    chromeAnchor: "share",
  }),
  card({
    id: "devices",
    text: "Everything you make works across devices.",
    target: "avatar",
    image: {
      url: `${ONBOARDING_MEDIA_BASE_URL}/688427f2d430397eaba2072c7089bc4e94e5ed6f81e8dff00ed7f4f1579e8bcd.png`,
      alt: "The same workspace on a computer and on a phone",
    },
  }),
  card({
    id: "feedback",
    text: "I can report issues to the Imbue team for you. You can also share feedback with us on Discord.",
    chromeAnchor: "help",
    link: { label: "Join our Discord", url: "https://discord.com/invite/GvK8MsCVgk" },
  }),
  card({
    id: "providers",
    text: "You can switch AI providers, even mid-chat.",
    target: "avatar",
    image: {
      url: `${ONBOARDING_MEDIA_BASE_URL}/343b56057e673a194cd4fa7271e3562c121ff0ae1fda10e528ec5e83d735cd9d.png`,
      alt: "The chat's provider menu",
    },
  }),
  card({
    id: "durable",
    text: "Apps built in Studio are made to last, with tests that keep them working over time.",
    target: "avatar",
  }),
  card({
    id: "done",
    text: "That’s the tour. Ask me anything in the chat, and you can take this tour again from the launcher.",
    target: "launcher",
    buttonLabel: "Done",
  }),
];

/** What the exit badge says, pointing at the launcher, when the tour is left early. */
export const TOUR_EXIT_BADGE_TEXT =
  "You can take the tour again any time: open the launcher and choose Show me around.";
export const TOUR_EXIT_BADGE_BUTTON_LABEL = "Got it";

/** What the card after an interrupted one says: the agent answered while the tour was on, so it waits. */
export const TOUR_PAUSED_TEXT = "The agent is waiting for you. We’ll resume the tour later.";
export const TOUR_PAUSED_BUTTON_LABEL = "OK";

/** The launcher row that runs the tour, and the words it matches. */
export const TOUR_LAUNCHER_LABEL = "Show me around";
export const TOUR_LAUNCHER_SEARCH_WORDS: readonly string[] = ["tour", "walkthrough"];

/** The selectors, in order of preference, of the shell's own markers a target is found at (contracts.md section 12). */
export function tourTargetSelectors(target: TourTarget): readonly string[] {
  switch (target) {
    case "avatar":
      return ['[data-floating-entries] [data-pinned-entry][data-entry-style="avatar"]', "[data-pinned-entry]"];
    case "shortcuts":
      return ["[data-shortcut]"];
    case "launcher":
      return ["[data-launcher-field]"];
  }
}
