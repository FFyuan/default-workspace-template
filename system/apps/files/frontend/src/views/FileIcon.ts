/**
 * The icon an entry wears: a folder, or a page with a folded corner and a coloured tag naming its type. An image
 * can stand in a thumbnail of itself instead. Drawn as SVG on a 64-unit grid and scaled to the size asked; below 32px
 * the tag loses its letters, which would not read.
 */

import m from "mithril";

import { urlOf, type Entry } from "../models/dufs";
import { badgeOf, familyOf, hasImageThumbnail, type FileFamily } from "../models/fileKinds";

const FOLDER_SVG =
  '<path d="M6 14a4 4 0 0 1 4-4h14.3a4 4 0 0 1 2.8 1.2L31 15h23a4 4 0 0 1 4 4v29a4 4 0 0 1-4 4H10a4 4 0 0 1-4-4z" style="fill:var(--files-folder-back)"/>' +
  '<path d="M6 22a4 4 0 0 1 4-4h44a4 4 0 0 1 4 4v28a4 4 0 0 1-4 4H10a4 4 0 0 1-4-4z" style="fill:var(--files-folder)"/>';

const PAGE_SVG =
  '<path d="M15 4h23l15 15v39a3 3 0 0 1-3 3H15a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3z" style="fill:var(--c-surface);stroke:var(--c-border-strong)" stroke-width="1.5"/>' +
  '<path d="M38 4v12a3 3 0 0 0 3 3h12" style="fill:var(--c-surface-secondary);stroke:var(--c-border-strong)" stroke-width="1.5" stroke-linejoin="round"/>';

/** The ruled lines on a page with no tag. */
const PAGE_LINES_SVG =
  '<path d="M20 30h24M20 37h24M20 44h17" style="stroke:var(--c-border-strong)" stroke-width="2.5" stroke-linecap="round"/>';

const SYMLINK_SVG =
  '<circle cx="14" cy="52" r="9" style="fill:var(--c-surface);stroke:var(--c-border-strong)" stroke-width="1.5"/>' +
  '<path d="M10.5 55.5 17 49M12 48.5h5.5V54" style="stroke:var(--c-text-primary)" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>';

function escapeText(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function tagSvg(family: FileFamily, badge: string, withLetters: boolean): string {
  if (!withLetters) {
    // Too small for letters: a broader band of the colour, which still tells one family from another.
    return `<rect x="17" y="33" width="30" height="20" rx="3" style="fill:var(--files-family-${family})"/>`;
  }
  const rect = `<rect x="16" y="38" width="32" height="13" rx="3" style="fill:var(--files-family-${family})"/>`;
  if (badge === "") return rect;
  const fontSize = badge.length > 3 ? 7.5 : 8.5;
  return (
    rect +
    `<text x="32" y="47.4" text-anchor="middle" font-family="system-ui, sans-serif" font-weight="700" ` +
    `font-size="${fontSize}" letter-spacing="0.3" fill="#fff">${escapeText(badge)}</text>`
  );
}

/** The SVG markup of an entry's icon at `size` pixels. */
export function fileIconSvg(name: string, isFolder: boolean, isSymlink: boolean, size: number): string {
  let body: string;
  if (isFolder) {
    body = FOLDER_SVG;
  } else {
    const family = familyOf(name, false);
    const badge = badgeOf(name);
    body = PAGE_SVG + (family === "other" && badge === "" ? PAGE_LINES_SVG : tagSvg(family, badge, size >= 32));
  }
  if (isSymlink) body += SYMLINK_SVG;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 64 64" aria-hidden="true">${body}</svg>`;
}

/** Images whose thumbnail failed to load, so they fall back to the icon instead of a broken image. */
const brokenThumbnails = new Set<string>();

/** Thumbnails are drawn from the image itself; past this size the bytes are not worth it for an icon. */
const MAX_THUMBNAIL_BYTES = 25_000_000;

export interface FileIconAttrs {
  entry: Entry;
  size: number;
  /** Draw an image as a thumbnail of itself. */
  thumbnail?: boolean;
}

export const FileIcon: m.Component<FileIconAttrs> = {
  view({ attrs: { entry, size, thumbnail = false } }) {
    const useThumbnail =
      thumbnail &&
      !entry.isFolder &&
      entry.size <= MAX_THUMBNAIL_BYTES &&
      hasImageThumbnail(entry.name) &&
      !brokenThumbnails.has(entry.path);
    if (useThumbnail) {
      return m(
        "span.file-icon.flex.items-center.justify-center.shrink-0",
        { style: `width:${size}px;height:${size}px` },
        m("img.files-thumbnail", {
          class: "max-h-full max-w-full rounded-[3px] object-contain shadow-raised",
          src: `${urlOf(entry.path)}?t=${entry.mtime}`,
          alt: "",
          loading: "lazy",
          draggable: false,
          onerror: () => brokenThumbnails.add(entry.path),
        }),
      );
    }
    return m(
      "span.file-icon.flex.items-center.justify-center.shrink-0",
      { style: `width:${size}px;height:${size}px` },
      m.trust(fileIconSvg(entry.name, entry.isFolder, entry.isSymlink, size)),
    );
  },
};
