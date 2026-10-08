/**
 * Folders on the user's own computer that Imbue Studio keeps a synced copy of in this workspace. Each lands at
 * `~/synced_folders/<device id>/<its path on that computer>` (see the file-sharing skill), and nothing records which
 * folder along that path is the one shared, so it is read off the tree: the path runs down through folders that each
 * hold a single folder and nothing else, and the shared folder is where that stops -- a folder holding files, several
 * folders, or nothing. Where the path branches, each branch is followed, since two shared folders can share a parent.
 */

import type { Listing } from "./dufs";
import { nameOf } from "./paths";

export const SYNCED_FOLDERS = "/home/user/synced_folders/";

export interface ConnectedFolder {
  /** Where the copy is in the workspace. */
  path: string;
  label: string;
  /** Where the folder is on the user's computer. */
  sourcePath: string;
}

/** How far down a device's folder a shared folder is looked for. */
const MAX_DEPTH = 16;

type ListFolder = (folder: string) => Promise<Listing>;

async function sharedFoldersUnder(folder: string, list: ListFolder, depth: number): Promise<string[]> {
  const { entries } = await list(folder);
  const folders = entries.filter((entry) => entry.isFolder);
  const holdsFiles = folders.length !== entries.length;
  if (holdsFiles || folders.length === 0 || depth >= MAX_DEPTH) return [folder];
  if (folders.length === 1) return sharedFoldersUnder(folders[0].path, list, depth + 1);
  const branches = await Promise.all(folders.map((child) => sharedFoldersUnder(child.path, list, depth + 1)));
  return branches.flat();
}

/** Every connected folder, from every device, in the order the server lists them. */
export async function findConnectedFolders(list: ListFolder): Promise<ConnectedFolder[]> {
  const root = await list(SYNCED_FOLDERS);
  if (!root.exists) return [];
  const devices = root.entries.filter((entry) => entry.isFolder);
  const perDevice = await Promise.all(
    devices.map(async (device) => {
      // A device's own folder holding nothing has no shared folder in it, rather than being one.
      const top = await list(device.path);
      if (top.entries.length === 0) return [];
      const paths = await sharedFoldersUnder(device.path, list, 0);
      return paths.map((path) => ({ path, label: nameOf(path), sourcePath: `/${path.slice(device.path.length)}` }));
    }),
  );
  return perDevice.flat();
}
