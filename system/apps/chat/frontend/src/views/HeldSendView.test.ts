// @vitest-environment jsdom
import m from "mithril";
import { describe, expect, it, vi } from "vitest";

import { chatSnapshotFixture, rebindStateFixture } from "../models/chatSnapshotFixture";
import type { ChatSnapshot } from "../models/Chats";

const mocks = vi.hoisted(() => ({ chat: undefined as ChatSnapshot | undefined }));
vi.mock("../models/Chats", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../models/Chats")>()),
  getChatById: () => mocks.chat,
}));
vi.mock("../models/Response", () => ({ isMessageCarriedBySwitch: () => false }));

import { renderHeldSends } from "./HeldSendView";

const REPORT =
  "<background-task-report>\n<summary>Wait for the worker (finished)</summary>\nExit code: 0\n</background-task-report>";

describe("the messages held while a chat switches", () => {
  it("shows a held background-task report as its one-line notice, and the user's own words as a bubble", () => {
    mocks.chat = chatSnapshotFixture("chat-1", {
      handoff: rebindStateFixture({
        held_sends: [
          { message_id: "trigger-1", text: "Carry on on the other account" },
          {
            message_id: "m-report",
            text: REPORT,
            display: "notice",
            display_label: "Background task",
            display_body: "Wait for the worker (finished)",
          },
        ],
      }),
    });
    const root = document.createElement("div");

    m.render(root, renderHeldSends("chat-1"));

    expect(root.querySelector(".held-send .message-notice")?.textContent).toBe(
      "Background task: Wait for the worker (finished)",
    );
    expect(root.textContent).not.toContain("<background-task-report>");
    expect(root.querySelector(".held-send .message-user-bubble")?.textContent).toBe("Carry on on the other account");
  });
});
