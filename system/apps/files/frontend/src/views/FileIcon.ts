/**
 * The icon an entry wears: a folder, or a page with a folded corner and a coloured tag naming its type. An image
 * can stand in a thumbnail of itself instead. Drawn as SVG on a 64-unit grid and scaled to the size asked; below 32px
 * the tag loses its letters, which would not read.
 */

import m from "mithril";

import { urlOf, type Entry } from "../models/dufs";
import { badgeOf, familyOf, hasImageThumbnail, type FileFamily } from "../models/fileKinds";

// The folder is the Files app icon's own hand-drawn shape (system/apps/files/icon.svg), drawn on that icon's grid
// and fitted to 64 units. Its back shows above a wavy line, its front below it, each clipped from the one outline so
// the edges match exactly and the darker back never bleeds through the front's rim.
const FOLDER_OUTLINE =
  "M21.34 15.75C24.52 15.67 26.57 15.75 27.93 15.9C29.52 16.05 30.35 16.89 31.26 18.25C32.17 19.61 32.7 20.29 34.14 20.37C37.16 20.52 41.15 20.22 44.26 20.37C46.83 20.52 48.14 22.49 47.99 24.98C47.76 29.07 47.16 34.22 46.47 38.23C46.02 40.8 44.43 42.09 41.55 42.17C34.89 42.32 26.19 42.32 20.36 42.09C17.56 41.94 16.37 41.03 16.17 38.23C15.67 31.23 16.42 24.53 16.8 20.29C17.03 17.34 18.47 15.83 21.34 15.75Z";

let folderClipCount = 0;

function folderSvg(): string {
  const id = `files-folder-${(folderClipCount += 1)}`;
  return (
    '<g transform="translate(-24 -18.8) scale(1.75)">' +
    `<clipPath id="${id}-back"><path d="M14 10H50V22.95C33 23.3 22 23 14 23.45Z"/></clipPath>` +
    `<clipPath id="${id}-front"><path d="M14 22.75C22 22.35 33 22.65 50 22.3V44H14Z"/></clipPath>` +
    `<path d="${FOLDER_OUTLINE}" clip-path="url(#${id}-back)" style="fill:var(--files-folder-back)"/>` +
    `<path d="${FOLDER_OUTLINE}" clip-path="url(#${id}-front)" style="fill:var(--files-folder)"/></g>`
  );
}

// A page in the same hand: no edge quite straight, corners a little uneven, the fold drawn rather than ruled.
const PAGE_SVG =
  '<path d="M17.2 4.7C24.1 4.25 31.2 4.35 37.5 4.55C39 4.6 40 5.05 41.05 6.1L51.1 16.3C52.05 17.3 52.45 18.35 52.45 19.85C52.65 30.2 52.35 44.1 51.65 55.3C51.45 58.3 49.85 59.55 47.05 59.7C37.1 60.15 27.05 60.1 17.5 59.75C14.5 59.6 12.95 58.25 12.75 55.25C12.25 44.2 12.3 26.1 12.85 9.35C12.95 6.2 14.35 4.85 17.2 4.7Z" style="fill:var(--c-surface);stroke:var(--c-border-strong)" stroke-width="1.5" stroke-linejoin="round"/>' +
  '<path d="M37.75 4.75C38.35 8.9 38.25 12.5 38.5 15.35C38.7 17.55 39.8 18.6 42.05 18.75C45.4 18.95 49.05 18.8 52.3 18.95C49 19 40.6 9.6 37.75 4.75Z" style="fill:var(--c-surface-secondary)"/>' +
  '<path d="M37.75 4.75C38.35 8.9 38.25 12.5 38.5 15.35C38.7 17.55 39.8 18.6 42.05 18.75C45.4 18.95 49.05 18.8 52.3 18.95" fill="none" style="stroke:var(--c-border-strong)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>';

/** The ruled lines on a page with no tag, drawn by hand like the page. */
const PAGE_LINES_SVG =
  '<path d="M20.2 30.3C27 29.9 37 30.1 43.8 29.9M20.1 37.2C27.5 36.9 36.5 37.1 43.9 36.8M20.2 44.1C25.5 43.9 31.5 44.2 37 43.9" fill="none" style="stroke:var(--c-border-strong)" stroke-width="2.5" stroke-linecap="round"/>';

/** The corner an icon's badge sits in: a white disc with a hairline edge at the bottom right, the glyph 60% of
 *  its width. */
function cornerBadgeSvg(glyph: string): string {
  return (
    '<circle cx="50" cy="52" r="9.5" style="fill:var(--c-surface);stroke:var(--c-border-strong)" stroke-width="1"/>' +
    `<g transform="translate(44.3 46.3) scale(0.475)" fill="none" style="stroke:var(--c-text-secondary)" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">${glyph}</g>`
  );
}

/** What a badge in an icon's corner says: a symbolic link, or a share read live (linked) or kept as a copy (synced). */
export type IconBadge = "symlink" | "linked" | "synced";

const BADGE_GLYPHS: Record<IconBadge, string> = {
  symlink: '<path d="M7 17 17 7"/><path d="M8 7h9v9"/>',
  linked:
    '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
  synced:
    '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
};

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
export function fileIconSvg(name: string, isFolder: boolean, badge: IconBadge | null, size: number): string {
  let body: string;
  if (isFolder) {
    body = folderSvg();
  } else {
    const family = familyOf(name, false);
    const tagText = badgeOf(name);
    body = PAGE_SVG + (family === "other" && tagText === "" ? PAGE_LINES_SVG : tagSvg(family, tagText, size >= 32));
  }
  if (badge !== null) body += cornerBadgeSvg(BADGE_GLYPHS[badge]);
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
  /** A shared item's own entry: how it reaches the workspace, worn in the corner in place of a symlink's arrow. */
  shareBadge?: IconBadge;
}

export const FileIcon: m.Component<FileIconAttrs> = {
  view({ attrs: { entry, size, thumbnail = false, shareBadge } }) {
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
    const badge = shareBadge ?? (entry.isSymlink ? "symlink" : null);
    return m(
      "span.file-icon.flex.items-center.justify-center.shrink-0",
      { style: `width:${size}px;height:${size}px`, "data-icon-badge": badge ?? undefined },
      m.trust(fileIconSvg(entry.name, entry.isFolder, badge, size)),
    );
  },
};
