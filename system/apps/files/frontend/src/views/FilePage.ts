/**
 * A file's own page: `?view` shows it (a picture, a player, a PDF, or its text), `?edit` opens its text in an editor
 * that saves back with Cmd/Ctrl+S. The header leads back to the folder and carries what can be done to the file.
 */

import m from "mithril";

import { Button, buttonClass } from "@imbue/workspace-ui/src/components/Button";
import { hoverTooltipAttrs } from "@imbue/workspace-ui/src/components/hoverTooltip";
import { icon } from "@imbue/workspace-ui/src/components/icons";
import { createMenu, type Menu } from "@imbue/workspace-ui/src/components/menu";

import * as dufs from "../models/dufs";
import { isTextLike, previewKindOf } from "../models/fileKinds";
import { formatSize } from "../models/format";
import { childPath, nameOf, parentOf, titleOf } from "../models/paths";
import { Dialogs } from "./dialogs";
import { FileIcon } from "./FileIcon";

export interface FilePageOptions {
  path: string;
  page: "view" | "edit";
  /** dufs's word that the file is small and decodes as text. */
  isText: boolean;
}

type TextState = { status: "loading" } | { status: "ready"; saved: string } | { status: "error"; error: string };

export class FilePageModel {
  text: TextState = { status: "loading" };
  draft = "";
  isSaving = false;
  notice: string | null = null;
  size: number | null = null;
  readonly dialogs = new Dialogs();

  constructor(readonly options: FilePageOptions) {}

  get isDirty(): boolean {
    return this.text.status === "ready" && this.draft !== this.text.saved;
  }

  get showsText(): boolean {
    return previewKindOf(nameOf(this.options.path), this.options.isText) === "text";
  }

  async load(): Promise<void> {
    void fetch(dufs.urlOf(this.options.path), { method: "HEAD" })
      .then((response) => {
        const length = response.headers.get("content-length");
        this.size = length === null ? null : Number(length);
        m.redraw();
      })
      .catch(() => undefined);
    if (!this.showsText) return;
    try {
      const text = await dufs.readText(this.options.path);
      this.text = { status: "ready", saved: text };
      this.draft = text;
    } catch (error) {
      this.text = { status: "error", error: error instanceof Error ? error.message : String(error) };
    }
    m.redraw();
  }

  async save(): Promise<void> {
    if (!this.isDirty || this.isSaving) return;
    const content = this.draft;
    this.isSaving = true;
    m.redraw();
    try {
      await dufs.writeFile(this.options.path, content);
      this.text = { status: "ready", saved: content };
      this.size = new Blob([content]).size;
    } catch (error) {
      this.notice = error instanceof Error ? error.message : String(error);
    }
    this.isSaving = false;
    m.redraw();
  }

  async rename(): Promise<void> {
    const path = this.options.path;
    const name = await this.dialogs.askName(nameOf(path));
    const parent = parentOf(path);
    if (name === null || parent === null) return;
    const target = childPath(parent, name, false);
    try {
      if (await dufs.exists(target)) throw new Error(`"${name}" is already taken.`);
      await dufs.movePath(path, target);
    } catch (error) {
      this.notice = error instanceof Error ? error.message : String(error);
      m.redraw();
      return;
    }
    window.location.replace(dufs.pageUrlOf(target, this.options.page));
  }

  async delete(): Promise<void> {
    const path = this.options.path;
    const entry: dufs.Entry = { name: nameOf(path), path, isFolder: false, isSymlink: false, size: 0, mtime: 0 };
    if (!(await this.dialogs.confirmDelete([entry]))) return;
    try {
      await dufs.deletePath(path);
    } catch (error) {
      this.notice = error instanceof Error ? error.message : String(error);
      m.redraw();
      return;
    }
    window.location.replace(dufs.urlOf(parentOf(path) ?? "/"));
  }
}

function headerButton(label: string, name: Parameters<typeof icon>[0], attrs: m.Attributes): m.Vnode {
  return m(
    "button",
    {
      type: "button",
      "aria-label": label,
      class: buttonClass("ghost", { icon: true, sm: true }),
      ...hoverTooltipAttrs(label),
      ...attrs,
    },
    m.trust(icon(name, { size: 16 })),
  );
}

function body(page: FilePageModel): m.Children {
  const { path, page: kind } = page.options;
  const name = nameOf(path);
  const url = dufs.urlOf(path);
  const preview = previewKindOf(name, page.options.isText);
  const centred = "flex h-full items-center justify-center overflow-auto bg-page p-6";
  switch (preview) {
    case "image":
      return m(
        "div",
        { class: centred },
        m("img.files-file-image", {
          src: url,
          alt: name,
          class: "max-h-full max-w-full object-contain shadow-raised",
        }),
      );
    case "video":
      return m("div", { class: centred }, m("video", { src: url, controls: true, class: "max-h-full max-w-full" }));
    case "audio":
      return m("div", { class: `${centred} flex-col gap-6` }, [
        m(FileIcon, { entry: { name, path, isFolder: false, isSymlink: false, size: 0, mtime: 0 }, size: 128 }),
        m("audio", { src: url, controls: true, class: "w-[min(480px,100%)]" }),
      ]);
    case "pdf":
      return m("iframe.files-file-frame", { src: url, title: name, class: "h-full w-full border-0" });
    case "text": {
      const text = page.text;
      if (text.status === "loading") return m("div", { class: centred }, m("div.spinner"));
      if (text.status === "error") return m("div", { class: `${centred} type-body text-danger` }, text.error);
      return m("textarea.files-editor", {
        value: page.draft,
        readOnly: kind === "view",
        spellcheck: false,
        "aria-label": kind === "edit" ? `Editing ${name}` : name,
        class:
          "block h-full w-full resize-none border-0 bg-surface px-6 py-4 font-mono text-[13px] leading-relaxed text-primary outline-none",
        oninput: (event: InputEvent) => {
          page.draft = (event.target as HTMLTextAreaElement).value;
        },
      });
    }
    case "none":
      return m("div", { class: `${centred} flex-col gap-3 text-center` }, [
        m(FileIcon, { entry: { name, path, isFolder: false, isSymlink: false, size: 0, mtime: 0 }, size: 128 }),
        m("div", { class: "type-label text-secondary" }, "No preview available"),
        m("div", { class: "type-helper text-faint" }, "This file is too large to show, or isn't text."),
        m(Button, { sm: true, extra: "mt-2", onclick: () => downloadFile(path) }, "Download"),
      ]);
  }
}

function downloadFile(path: string): void {
  const anchor = document.createElement("a");
  anchor.href = dufs.urlOf(path);
  anchor.download = nameOf(path);
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

export function FilePage(): m.Component<{ page: FilePageModel }> {
  let menu: Menu | null = null;
  let onKeydown: ((event: KeyboardEvent) => void) | null = null;
  let onBeforeUnload: ((event: BeforeUnloadEvent) => void) | null = null;
  return {
    oninit({ attrs: { page } }) {
      menu = createMenu({ placement: "below", align: "end", minWidth: 200, extraClass: "files-file-menu" });
      onKeydown = (event) => {
        if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
          event.preventDefault();
          void page.save();
        }
      };
      onBeforeUnload = (event) => {
        if (page.isDirty) event.preventDefault();
      };
      document.addEventListener("keydown", onKeydown);
      window.addEventListener("beforeunload", onBeforeUnload);
    },
    onremove() {
      menu?.dispose();
      if (onKeydown !== null) document.removeEventListener("keydown", onKeydown);
      if (onBeforeUnload !== null) window.removeEventListener("beforeunload", onBeforeUnload);
    },
    view({ attrs: { page } }) {
      if (menu === null) return null;
      const { path, page: kind } = page.options;
      const name = nameOf(path);
      const folder = parentOf(path) ?? "/";
      // dufs calls any small file that decodes as text editable; Edit is offered only on one that reads as text.
      const canEdit = page.showsText && page.text.status === "ready" && isTextLike(name);
      return m("div.files-file-page", { class: "flex h-screen min-h-0 flex-col bg-surface text-primary" }, [
        m("header.files-toolbar", { class: "flex h-12 shrink-0 items-center gap-2 border-b border-default px-3" }, [
          m(
            "a.files-file-folder",
            {
              href: dufs.urlOf(folder),
              class:
                "flex shrink-0 items-center gap-1 rounded-md px-1.5 py-1 text-(length:--font-size-row) text-secondary hover:bg-fill-hover hover:text-primary",
              ...hoverTooltipAttrs("Show in folder"),
            },
            [m.trust(icon("chevron-left", { size: 14 })), titleOf(folder)],
          ),
          m.trust(icon("chevron-right", { size: 12, className: "shrink-0 text-faint" })),
          m("div", { class: "flex min-w-0 flex-1 items-center gap-2" }, [
            m(FileIcon, { entry: { name, path, isFolder: false, isSymlink: false, size: 0, mtime: 0 }, size: 20 }),
            m("span.files-file-name", { class: "truncate text-(length:--font-size-row) font-semibold" }, name),
            page.isDirty ? m("span.files-file-dirty", { class: "type-helper text-faint" }, "Edited") : null,
            page.size === null ? null : m("span", { class: "shrink-0 type-helper text-faint" }, formatSize(page.size)),
          ]),
          kind === "edit"
            ? [
                m(
                  "a",
                  {
                    href: dufs.pageUrlOf(path, "view"),
                    class: buttonClass("ghost", { sm: true }),
                    "data-action": "done",
                  },
                  "Done",
                ),
                m(
                  Button,
                  {
                    variant: "primary",
                    sm: true,
                    "data-action": "save",
                    disabled: !page.isDirty || page.isSaving,
                    onclick: () => void page.save(),
                  },
                  page.isSaving ? "Saving..." : "Save",
                ),
              ]
            : canEdit
              ? m(
                  "a.edit-file",
                  {
                    href: dufs.pageUrlOf(path, "edit"),
                    class: buttonClass("secondary", { sm: true }),
                    "data-action": "edit",
                  },
                  [m.trust(icon("edit", { size: 14 })), "Edit"],
                )
              : null,
          headerButton("Download", "download", { "data-action": "download", onclick: () => downloadFile(path) }),
          m("div", { class: "flex shrink-0" }, [
            headerButton("More", "ellipsis", { "data-action": "more", ...menu.triggerAttrs() }),
            menu.view([
              { kind: "action", key: "rename", label: "Rename", icon: "edit", onSelect: () => void page.rename() },
              {
                kind: "action",
                key: "copy-path",
                label: "Copy Path",
                icon: "copy",
                onSelect: () => void navigator.clipboard.writeText(path).catch(() => undefined),
              },
              { kind: "divider" },
              {
                kind: "action",
                key: "delete",
                label: "Delete",
                icon: "trash",
                tone: "danger",
                onSelect: () => void page.delete(),
              },
            ]),
          ]),
        ]),
        m("main", { class: "min-h-0 flex-1" }, body(page)),
        page.notice === null
          ? null
          : m(
              "div.files-notice",
              {
                role: "alert",
                class:
                  "fixed bottom-6 left-1/2 z-(--z-sticky) flex max-w-[min(480px,calc(100vw-32px))] -translate-x-1/2 items-start gap-3 rounded-lg bg-inverse px-4 py-2.5 type-body text-on-accent shadow-overlay",
              },
              [
                m("span", { class: "min-w-0 flex-1" }, page.notice),
                m(
                  "button",
                  {
                    type: "button",
                    "aria-label": "Dismiss",
                    class: "cursor-pointer text-white/70 hover:text-white",
                    onclick: () => (page.notice = null),
                  },
                  m.trust(icon("close", { size: 14 })),
                ),
              ],
            ),
        page.dialogs.view(),
      ]);
    },
  };
}
