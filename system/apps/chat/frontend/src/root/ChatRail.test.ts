// @vitest-environment jsdom
/**
 * The rail's status marks: a chat waiting on a background task wears the dashed ring, a working one the breathing
 * dot (pending tasks or not, since the backend reports it working), and an idle one the hollow ring. And the
 * default chat: it leads in its own group, set off from the rest, and its row is marked.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

const verbs = vi.hoisted(() => ({
  stopChat: vi.fn(async (_chatId: string) => undefined),
  startChat: vi.fn(async (_chatId: string) => undefined),
  renameChat: vi.fn(async (_chatId: string, _title: string) => undefined),
  makeDefaultChat: vi.fn(async (_chatId: string) => undefined),
  destroyChat: vi.fn(async (_chatId: string) => undefined),
}));
vi.mock("./verbs", () => verbs);

import m from "mithril";
import { ChatRail, rowMenuRows } from "./ChatRail";
import { chatRailAttrsFixture } from "./chatRailAttrsFixture";
import { chatRowFixture } from "./chatRowFixture";
import type { ChatRow } from "./rows";

let root: HTMLElement | null = null;

afterEach(() => {
  if (root === null) return;
  m.mount(root, null);
  root.remove();
  root = null;
});

function mount(rows: readonly ChatRow[]): HTMLElement {
  const mounted = document.createElement("div");
  document.body.appendChild(mounted);
  root = mounted;
  m.mount(mounted, { view: () => m(ChatRail, chatRailAttrsFixture({ rows })) });
  return mounted;
}

function dotClassOf(chatId: string): string {
  const dot = root?.querySelector(`[data-chat-id="${chatId}"] .chat-rail-dot`);
  if (dot === null || dot === undefined) throw new Error(`no status mark for ${chatId}`);
  return dot.getAttribute("class") ?? "";
}

function chatIdsIn(element: Element): string[] {
  return [...element.querySelectorAll<HTMLElement>(".chat-rail-row")].map((rowElement) => rowElement.dataset.chatId!);
}

describe("ChatRail status marks", () => {
  it("draws background as the dashed ring, apart from working and idle", () => {
    const rail = mount([
      chatRowFixture("agent-wait", { status: "background" }),
      chatRowFixture("agent-turn", { status: "working" }),
      chatRowFixture("agent-idle"),
    ]);

    expect(dotClassOf("agent-wait")).toContain("chat-rail-dot--dashed");
    expect(dotClassOf("agent-wait")).not.toContain("chat-rail-dot--pulse");
    expect(dotClassOf("agent-turn")).toContain("chat-rail-dot--pulse");
    expect(dotClassOf("agent-turn")).not.toContain("chat-rail-dot--dashed");
    expect(dotClassOf("agent-idle")).not.toMatch(/chat-rail-dot--(dashed|pulse)/);
    expect(rail.querySelector('[data-chat-id="agent-wait"]')?.getAttribute("data-status")).toBe("background");
  });
});

describe("ChatRail default chat", () => {
  it("sets the default chat and its helpers apart from the rest, and marks the default row", () => {
    const helper = chatRowFixture("agent-helper", { labels: { agent_created: "true", lead_agent: "agent-welcome" } });
    const rail = mount([chatRowFixture("agent-welcome", { isDefault: true }), helper, chatRowFixture("agent-other")]);

    const group = rail.querySelector(".chat-rail-default-group");
    expect(group).not.toBeNull();
    expect(chatIdsIn(group!)).toEqual(["agent-welcome", "agent-helper"]);
    expect(chatIdsIn(rail)).toEqual(["agent-welcome", "agent-helper", "agent-other"]);
    expect(rail.querySelector('[data-chat-id="agent-welcome"]')?.getAttribute("data-default")).toBe("true");
    expect(rail.querySelector('[data-chat-id="agent-other"]')?.hasAttribute("data-default")).toBe(false);
  });

  it("draws no default group when no chat is the default", () => {
    const rail = mount([chatRowFixture("agent-a"), chatRowFixture("agent-b")]);

    expect(rail.querySelector(".chat-rail-default-group")).toBeNull();
    expect(chatIdsIn(rail)).toEqual(["agent-a", "agent-b"]);
  });

  it("offers to make a chat the default, except the default itself and a helper another agent started", () => {
    const welcome = chatRowFixture("agent-welcome", { isDefault: true });
    const other = chatRowFixture("agent-other");
    const helper = chatRowFixture("agent-helper", { labels: { agent_created: "true", lead_agent: "agent-welcome" } });
    const context = chatRailAttrsFixture({ rows: [welcome, helper, other] });
    const labelsOf = (row: ChatRow): string[] =>
      rowMenuRows(context, row).flatMap((menuRow) => (menuRow.kind === "action" ? [menuRow.label] : []));

    expect(labelsOf(welcome)).not.toContain("Make default chat");
    expect(labelsOf(helper)).not.toContain("Make default chat");
    const makeDefault = rowMenuRows(context, other).find(
      (menuRow) => menuRow.kind === "action" && menuRow.key === "make-default",
    );
    if (makeDefault?.kind !== "action") throw new Error("no Make default chat row");
    makeDefault.onSelect();

    expect(verbs.makeDefaultChat).toHaveBeenCalledWith("agent-other");
  });
});
