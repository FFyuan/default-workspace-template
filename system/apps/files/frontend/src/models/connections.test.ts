import { describe, expect, it } from "vitest";

import { type Share, describeShare } from "./connections";

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
      "Synced both ways. Up to date.",
    );
    expect(describeShare(share({ access: "read", synced_copy: copy, sync_state: "behind" }), MAC)).toBe(
      "Synced from Kims-Mac, read-only. Hasn't caught up yet.",
    );
    expect(describeShare(share({ synced_copy: copy, sync_state: "unknown", is_reachable: false }), MAC)).toBe(
      "Synced both ways. Can't check: Kims-Mac isn't answering.",
    );
    expect(describeShare(share({}), MAC)).toBe("Live from Kims-Mac, not copied.");
    expect(describeShare(share({ access: "read", is_reachable: false }), MAC)).toBe(
      "Live from Kims-Mac, not copied, read-only. Kims-Mac isn't answering.",
    );
    expect(describeShare(share({}), MAC)).not.toContain("notes");
  });
});
