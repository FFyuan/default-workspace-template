/**
 * What the user has shared with this workspace from their computers (the Files server's `/__files/api/connections`,
 * read from the latchkey gateway), and the ways each share reaches the workspace: synced both ways, synced one way
 * from the computer, or read live from the computer with no copy here.
 */

import { DufsError } from "./dufs";
import { nameOf } from "./paths";

export const CONNECTIONS_API = "/__files/api/connections";
/** Where a share with no copy here is browsed: the Files server answers it from the computer, live. */
export const REMOTE_PREFIX = "/__remote/";

export interface Device {
  id: string;
  name: string;
}

export interface Share {
  device: string;
  /** Where it is on the computer. */
  path: string;
  access: "read" | "write";
  kind: "folder" | "file" | "unknown";
  is_reachable: boolean;
  /** Where the synced copy is in the workspace, or null when there is none. */
  synced_copy: string | null;
  /** Whether the copy holds what the computer does; null for a share with no copy. */
  sync_state: "current" | "behind" | "unknown" | null;
}

export interface Connections {
  devices: Device[];
  shares: Share[];
}

/** How a share reaches the workspace. */
export type ShareMode = "two-way" | "one-way" | "live";

export function modeOf(share: Share): ShareMode {
  if (share.synced_copy === null) return "live";
  return share.access === "write" ? "two-way" : "one-way";
}

export function deviceNameOf(connections: Connections, device: string): string {
  return connections.devices.find((candidate) => candidate.id === device)?.name ?? "your computer";
}

/** Where opening a share goes: its synced copy, or the live view of it on its computer. */
export function targetOf(share: Share): string {
  if (share.synced_copy !== null) return share.synced_copy;
  const live = `${REMOTE_PREFIX}${share.device}${share.path}`;
  return share.kind === "file" ? live : `${live.replace(/\/+$/, "")}/`;
}

export function labelOf(share: Share): string {
  return nameOf(share.path) || share.path;
}

/** One line saying how a share reaches the workspace and what may be done with it. */
export function describeShare(share: Share, deviceName: string): string {
  const where = `${share.path} on ${deviceName}`;
  const changes = share.access === "write" ? "You can change it here." : "Read-only here.";
  switch (modeOf(share)) {
    case "two-way":
      return `${where}. Synced both ways: changes on either side reach the other.`;
    case "one-way":
      return `${where}. Synced one way, from your computer. ${changes}`;
    case "live":
      return `${where}. Not synced: opened live from your computer while it's awake. ${changes}`;
  }
}

/** A warning about a share, or null when there is nothing to warn of. */
export function shareProblemOf(share: Share): string | null {
  if (share.sync_state === "behind") return "This copy hasn't caught up with your computer. The sync may be stuck.";
  if (!share.is_reachable && share.synced_copy === null) return "Your computer isn't answering right now.";
  return null;
}

async function failureOf(response: Response, what: string): Promise<DufsError> {
  const detail = (await response.text().catch(() => "")).trim();
  return new DufsError(detail === "" ? `${what} (${response.status})` : detail, response.status);
}

export async function fetchConnections(signal?: AbortSignal): Promise<Connections> {
  const response = await fetch(CONNECTIONS_API, { signal });
  if (!response.ok) throw await failureOf(response, "Couldn't read your connections");
  return (await response.json()) as Connections;
}

export interface ConnectionRequest {
  device: string;
  path: string;
  access: "read" | "write";
  sync: boolean;
}

/** Ask to share something more: Imbue Studio shows its sharing dialog on the computer, where the user decides. */
export async function requestConnection(ask: ConnectionRequest): Promise<void> {
  const response = await fetch(CONNECTIONS_API, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(ask),
  });
  if (!response.ok) throw await failureOf(response, "Couldn't ask your computer");
}
