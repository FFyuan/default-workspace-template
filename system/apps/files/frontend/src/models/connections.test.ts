import { describe, expect, it, vi } from "vitest";

import { type Share, describeShare, requestConnection } from "./connections";

const MAC = "Kims-Mac.local";

function share(overrides: Partial<Share>): Share {
  return {
    device: "host-mac",
    path: "/Users/kim/notes",
    access: "write",
    kind: "folder",
    is_reachable: true,
    synced_copy: null,
    sync_state: null,
    ...overrides,
  };
}

describe("describeShare", () => {
  it("says how a share reaches the workspace and how it stands, never its name", () => {
    const copy = "/home/user/synced_folders/host-mac/Users/kim/notes/";
    expect(describeShare(share({ synced_copy: copy, sync_state: "current" }), MAC)).toBe(
      "Synced with Kims-Mac. Up to date.",
    );
    expect(describeShare(share({ access: "read", synced_copy: copy, sync_state: "behind" }), MAC)).toBe(
      "Synced from Kims-Mac. Read-only. Hasn't caught up yet.",
    );
    expect(describeShare(share({ synced_copy: copy, sync_state: "unknown", is_reachable: false }), MAC)).toBe(
      "Synced with Kims-Mac. Can't check: not answering right now.",
    );
    expect(describeShare(share({}), MAC)).toBe("On Kims-Mac.");
    expect(describeShare(share({ access: "read", is_reachable: false }), MAC)).toBe(
      "On Kims-Mac. Read-only. Not answering right now.",
    );
    expect(describeShare(share({}), MAC)).not.toContain("notes");
  });
});

describe("requestConnection", () => {
  it("quotes the server's refusal, from its {detail} body or its text", async () => {
    const refusals = [
      new Response(JSON.stringify({ detail: "Imbue Studio refused the request." }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      }),
      new Response("Not Found", { status: 404, headers: { "Content-Type": "text/plain" } }),
      new Response("", { status: 502 }),
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => refusals.shift()),
    );
    try {
      const ask = { device: "host-mac", path: "~", access: "read" as const, sync: false };
      await expect(requestConnection(ask)).rejects.toThrow("Imbue Studio refused the request.");
      await expect(requestConnection(ask)).rejects.toThrow("Not Found");
      await expect(requestConnection(ask)).rejects.toThrow("Couldn't ask your computer (502)");
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
