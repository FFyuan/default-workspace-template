/**
 * Renders the optimistic outgoing bubbles (see models/OutgoingMessages) at the
 * very tail of the transcript -- below the committed turns AND below the queued
 * group, so a just-sent message shows immediately as the last thing(s) until the
 * harness-sourced state catches up. Drawn exactly like the delivered turn that
 * replaces it, so a send reads as sent at once (contract A2). A send still waiting
 * for the agent to come up says so beside the model bar (ConnectingIndicator), not
 * here. A failed send is NOT rendered here -- the composer handles that (popup +
 * text restored), and the bubble is dropped.
 */
import m from "mithril";
import { getOutgoingMessages } from "../models/OutgoingMessages";
import type { DisplayDecision, OutgoingMessage } from "../models/OutgoingMessages";
import { classifyUserMessage } from "./message-classification";
import { UserMessageKind } from "./message-kinds";
import {
  NOTICE_FALLBACK_LABEL,
  NOTICE_ROW_SPACING_CLASS,
  USER_BUBBLE_CLASS,
  USER_MESSAGE_ROW_CLASS,
  renderNotice,
} from "./user-message-display";

// The user rail's own recipes; the extra classes are bare markers for tests.
const OUTGOING_ROW_CLASS = `${USER_MESSAGE_ROW_CLASS} outgoing-message outgoing-message--sending`;

// The committed user row's spacing, so consecutive not-yet-delivered bubbles stand apart and the
// real turn replaces one without a reflow.
const STANDALONE_ROW_SPACING_CLASS = "mb-5";

export interface NotYetRealBubble {
  key: string;
  /** The user's text, verbatim. */
  content: string;
  /** True inside a group whose own gap spaces its bubbles (the queued group), so the row
   *  carries no bottom margin of its own. */
  isGroupSpaced?: boolean;
  /** Marker classes added to the row, for a caller whose bubbles a test or a style picks out. */
  extraRowClass?: string;
  /** The backend's render decision for the text; a notice (a background-task report) draws as one. */
  display?: DisplayDecision;
}

/** A user message that is not yet a real turn, drawn as the row it will become: the user bubble,
 *  or the one-line notice the backend decided its text renders as. Every not-yet-delivered message
 *  renders through here (optimistic, held by a switch, re-sent by a tap), so they look the same
 *  and the handoff to the real turn is invisible. */
export function renderNotYetRealBubble(bubble: NotYetRealBubble): m.Vnode {
  const cls = classifyUserMessage({
    content: bubble.content,
    display: bubble.display?.display ?? undefined,
    display_label: bubble.display?.display_label ?? undefined,
    display_body: bubble.display?.display_body ?? undefined,
  });
  if (cls.kind === UserMessageKind.Notice) {
    const noticeRowClass = [
      "message-notice-row",
      bubble.isGroupSpaced === true ? null : NOTICE_ROW_SPACING_CLASS,
      bubble.extraRowClass ?? null,
    ]
      .filter((part) => part !== null)
      .join(" ");
    return m("div", { class: noticeRowClass, key: bubble.key }, [
      renderNotice(cls.label ?? NOTICE_FALLBACK_LABEL, cls.body),
    ]);
  }
  const rowClass = [
    OUTGOING_ROW_CLASS,
    bubble.isGroupSpaced === true ? null : STANDALONE_ROW_SPACING_CLASS,
    bubble.extraRowClass ?? null,
  ]
    .filter((part) => part !== null)
    .join(" ");
  return m("div", { class: rowClass, key: bubble.key }, [
    m("div", { class: USER_BUBBLE_CLASS }, [
      m("div", { class: "message-content whitespace-pre-wrap" }, bubble.content),
    ]),
  ]);
}

function renderOutgoingBubble(outgoing: OutgoingMessage): m.Vnode {
  return renderNotYetRealBubble({ key: outgoing.id, content: outgoing.content, display: outgoing.display });
}

/** The optimistic outgoing bubbles for a chat, in send order. Returns [] when
 *  there are none. */
export function renderOutgoingMessages(chatId: string): m.Vnode[] {
  return getOutgoingMessages(chatId).map(renderOutgoingBubble);
}
