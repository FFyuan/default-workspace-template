/**
 * A Files window on a folder: history and the shortcuts down the side, the toolbar (where you are, how the folder is
 * laid out, and what can be added to it), the folder itself, and a status line. Files dropped anywhere on it go
 * into the folder under the pointer; entries dragged onto a folder move into it.
 */

import m from "mithril";

import { Button, buttonClass } from "@imbue/workspace-ui/src/components/Button";
import { hoverTooltipAttrs } from "@imbue/workspace-ui/src/components/hoverTooltip";
import { icon, type IconName } from "@imbue/workspace-ui/src/components/icons";
import { createMenu, type Menu, type MenuRow } from "@imbue/workspace-ui/src/components/menu";

import { formatItemCount, formatSize } from "../models/format";
import type { Shortcut } from "../models/FilesModel";
import type { SortKey, ViewMode } from "../models/preferences";
import { folderPathOf, isWithin, segmentsOf } from "../models/paths";
import { isFileDrag, sourcesFromDrop } from "../models/uploads";
import { DROP_FOLDER_ATTR, ENTRY_DRAG_TYPE, FOLDER_SURFACE_ATTR } from "./entries";
import { menuRowsOf, type FilesController } from "./FilesController";
import { ColumnView, IconView, ListView } from "./FolderViews";
import { handleKeydown } from "./keyboard";

const SHORTCUT_ICONS: Record<string, IconName> = {
  workspace: "house",
  uploads: "inbox",
};

const VIEW_MODES: readonly { mode: ViewMode; label: string; icon: IconName }[] = [
  { mode: "icons", label: "Icons", icon: "layout-grid" },
  { mode: "list", label: "List", icon: "list" },
  { mode: "columns", label: "Columns", icon: "columns" },
];

const SORT_LABELS: Record<SortKey, string> = {
  name: "Name",
  modified: "Date Modified",
  size: "Size",
  kind: "Kind",
};

function iconButton(
  label: string,
  name: IconName,
  attrs: m.Attributes,
  options: { selected?: boolean; tooltip?: boolean } = {},
): m.Vnode {
  return m(
    "button",
    {
      type: "button",
      "aria-label": label,
      class: buttonClass("ghost", { icon: true, sm: true, selected: options.selected }),
      ...(options.tooltip === false ? {} : hoverTooltipAttrs(label)),
      ...attrs,
    },
    m.trust(icon(name, { size: 16 })),
  );
}

// Sidebar

function Sidebar(): m.Component<{ app: FilesController }> {
  return {
    view({ attrs: { app } }) {
      const model = app.model;
      // The shortcut the folder is under, the deepest one when shortcuts nest.
      const current = [...model.shortcuts]
        .filter((shortcut) => isWithin(model.folder, shortcut.path))
        .sort((a, b) => b.path.length - a.path.length)[0];
      // Back and forward head the sidebar, level with the toolbar, which leaves the toolbar its width for the path.
      const history = m("div.files-history", { class: "flex h-12 shrink-0 items-center gap-0.5 px-2" }, [
        iconButton("Back", "arrow-left", {
          "data-action": "back",
          disabled: !model.canGoBack,
          onclick: () => window.history.back(),
        }),
        iconButton("Forward", "arrow-right", {
          "data-action": "forward",
          disabled: !model.canGoForward,
          onclick: () => window.history.forward(),
        }),
      ]);
      return m(
        "nav.files-sidebar",
        { class: `flex shrink-0 flex-col bg-sidebar ${app.isNarrow ? "w-[136px]" : "w-[176px]"}` },
        [
          history,
          m("div", { class: "flex min-h-0 flex-col gap-0.5 overflow-y-auto px-2 pb-3" }, [
            m("div", { class: "px-2 pb-1 type-section text-faint" }, "Shortcuts"),
            model.shortcuts.map((shortcut: Shortcut) =>
              m(
                "button.files-shortcut",
                {
                  key: shortcut.key,
                  type: "button",
                  "data-shortcut": shortcut.key,
                  [DROP_FOLDER_ATTR]: shortcut.path,
                  "aria-current": current?.key === shortcut.key ? "true" : undefined,
                  class: `flex h-7 w-full cursor-pointer items-center gap-2 rounded-md px-2 text-left text-(length:--font-size-row) ${
                    model.dropTarget === shortcut.path
                      ? "bg-accent-light outline-2 -outline-offset-2 outline-accent"
                      : current?.key === shortcut.key
                        ? "bg-fill-active text-primary"
                        : "text-secondary hover:bg-fill-hover hover:text-primary"
                  }`,
                  onclick: () => model.navigate(shortcut.path),
                },
                [
                  m.trust(icon(SHORTCUT_ICONS[shortcut.key] ?? "folder", { size: 15, className: "shrink-0" })),
                  m("span", { class: "truncate" }, shortcut.label),
                ],
              ),
            ),
          ]),
        ],
      );
    },
  };
}

// Toolbar

function Breadcrumb(): m.Component<{ app: FilesController }> {
  return {
    onupdate({ dom }) {
      dom.scrollLeft = dom.scrollWidth;
    },
    oncreate({ dom }) {
      dom.scrollLeft = dom.scrollWidth;
    },
    view({ attrs: { app } }) {
      const model = app.model;
      const segments = segmentsOf(model.folder);
      const crumbs = [{ label: "Computer", path: "/" }].concat(
        segments.map((segment, index) => ({ label: segment, path: folderPathOf(segments.slice(0, index + 1)) })),
      );
      return m(
        "div.files-breadcrumb",
        { class: "flex min-w-0 flex-1 items-center overflow-x-auto [scrollbar-width:none]" },
        crumbs.map((crumb, index) => {
          const isLast = index === crumbs.length - 1;
          return m.fragment({ key: crumb.path }, [
            index === 0 ? null : m.trust(icon("chevron-right", { size: 12, className: "shrink-0 text-faint" })),
            m(
              "button.files-crumb",
              {
                type: "button",
                "data-crumb": crumb.path,
                [DROP_FOLDER_ATTR]: crumb.path,
                class: `shrink-0 cursor-pointer rounded-md px-1.5 py-1 whitespace-nowrap text-(length:--font-size-row) ${
                  model.dropTarget === crumb.path
                    ? "bg-accent-light text-primary"
                    : isLast
                      ? "font-semibold text-primary"
                      : "text-secondary hover:bg-fill-hover hover:text-primary"
                }`,
                onclick: () => {
                  if (crumb.path !== model.folder || model.search !== null) model.navigate(crumb.path);
                },
              },
              crumb.label,
            ),
          ]);
        }),
      );
    },
  };
}

function Toolbar(): m.Component<{ app: FilesController }> {
  let addMenu: Menu | null = null;
  let optionsMenu: Menu | null = null;
  return {
    oninit() {
      addMenu = createMenu({ placement: "below", align: "end", minWidth: 200, extraClass: "files-add-menu" });
      optionsMenu = createMenu({ placement: "below", align: "end", minWidth: 220, extraClass: "files-options-menu" });
    },
    onremove() {
      addMenu?.dispose();
      optionsMenu?.dispose();
    },
    view({ attrs: { app } }) {
      const model = app.model;
      if (addMenu === null || optionsMenu === null) return null;
      const sort = model.preferences.sort;
      const optionRows: MenuRow[] = [
        {
          kind: "submenu",
          key: "sort",
          label: "Sort by",
          value: `${SORT_LABELS[sort.key]}${sort.descending ? ", descending" : ""}`,
          rows: () => [
            ...(Object.keys(SORT_LABELS) as SortKey[]).map((key) => ({
              kind: "action" as const,
              key: `sort-${key}`,
              label: SORT_LABELS[key],
              trailing: sort.key === key ? m.trust(icon("check", { size: 14 })) : null,
              keepsOpen: true,
              onSelect: () => model.setSort({ key, descending: sort.key === key ? sort.descending : false }),
            })),
            { kind: "divider" as const },
            {
              kind: "check" as const,
              key: "sort-descending",
              label: "Descending",
              isChecked: sort.descending,
              onToggle: () => model.setSort({ ...sort, descending: !sort.descending }),
            },
          ],
        },
        {
          kind: "check",
          key: "show-hidden",
          label: "Show system files",
          isChecked: model.preferences.showHidden,
          onToggle: () => model.toggleHidden(),
        },
      ];
      const modes = VIEW_MODES.filter((view) => !(app.isNarrow && view.mode === "columns"));
      // A light outline around the whole switch, and the chosen view a solid grey inside it.
      const viewSwitch = m(
        "div.files-view-switch",
        {
          role: "group",
          "aria-label": "View",
          class: "flex shrink-0 items-center gap-0.5 rounded-lg border border-default p-0.5",
        },
        modes.map((view) => {
          const isChosen = app.viewMode === view.mode;
          return m(
            "button",
            {
              key: view.mode,
              type: "button",
              "aria-label": `View as ${view.label}`,
              "data-view-mode": view.mode,
              "aria-pressed": isChosen ? "true" : "false",
              class: `flex h-6 w-7 cursor-pointer items-center justify-center rounded-md transition-colors duration-(--dur-base) ${
                isChosen ? "bg-fill-active text-primary" : "text-secondary hover:bg-fill-hover hover:text-primary"
              }`,
              ...hoverTooltipAttrs(`View as ${view.label}`),
              onclick: () => model.setViewMode(view.mode),
            },
            m.trust(icon(view.icon, { size: 15 })),
          );
        }),
      );
      const add = m("div", { class: "flex shrink-0" }, [
        iconButton("Add", "plus", { "data-action": "add", ...addMenu.triggerAttrs() }, { tooltip: false }),
        addMenu.view(menuRowsOf(app.folderActions(model.folder).reverse())),
      ]);
      const options = m("div", { class: "flex shrink-0" }, [
        iconButton(
          "View options",
          "ellipsis",
          { "data-action": "options", ...optionsMenu.triggerAttrs() },
          { tooltip: false },
        ),
        optionsMenu.view(optionRows),
      ]);
      return m(
        "header.files-toolbar",
        { class: "flex h-12 shrink-0 items-center gap-1 border-b border-default bg-surface px-3" },
        [m(Breadcrumb, { app }), viewSwitch, add, options],
      );
    },
  };
}

// The folder

function FolderBody(): m.Component<{ app: FilesController }> {
  return {
    view({ attrs: { app } }) {
      const model = app.model;
      const mode = app.viewMode;
      if (mode === "columns" && model.search === null) return m(ColumnView, { app });
      const state = model.folderState(model.folder);
      const entries = model.shownEntries();
      const search = model.search;
      let empty: m.Children = null;
      if (search !== null) {
        if (search.status === "error") empty = message("Search failed", search.error ?? "");
        else if (entries.length === 0)
          empty =
            search.status === "searching"
              ? m("div", { class: "flex justify-center pt-16" }, m("div.spinner"))
              : message("No results", `Nothing in this folder matches "${search.query}".`);
      } else if (state === undefined || (state.status === "loading" && entries.length === 0)) {
        empty = m("div", { class: "flex justify-center pt-16" }, m("div.spinner"));
      } else if (state.status === "error" && entries.length === 0) {
        empty = message("Couldn't open this folder", state.error ?? "", () => void model.load(model.folder));
      } else if (!state.exists) {
        empty = message("This folder doesn't exist", "It may have been moved or deleted.");
      } else if (entries.length === 0) {
        empty = message(
          "This folder is empty",
          app.isNarrow ? "Tap + to put something here." : "Drop files here, or use + to upload or create something.",
        );
      }
      return m("div", { class: "min-h-full" }, [
        search === null
          ? null
          : m(
              "div.files-search-header",
              { class: "flex items-center gap-2 px-5 pt-3 pb-1 type-helper text-secondary" },
              [
                m("span", `Results in ${segmentsOf(search.folder).pop() ?? "Computer"}`),
                search.status === "searching" && entries.length > 0 ? m("div.spinner.spinner--sm") : null,
              ],
            ),
        // Results come from all through the folder, so they show as a list, which says where each one is.
        empty ?? (mode === "icons" && search === null ? m(IconView, { app, entries }) : m(ListView, { app, entries })),
      ]);
    },
  };
}

function message(title: string, detail: string, retry?: () => void): m.Vnode {
  return m("div.files-empty", { class: "flex flex-col items-center gap-1 px-6 pt-20 text-center" }, [
    m("div", { class: "type-label text-secondary" }, title),
    detail === "" ? null : m("div", { class: "max-w-[360px] type-helper text-faint" }, detail),
    retry === undefined ? null : m(Button, { sm: true, extra: "mt-3", onclick: retry }, "Try again"),
  ]);
}

// The status line, the uploads, the notices

function StatusBar(): m.Component<{ app: FilesController }> {
  return {
    view({ attrs: { app } }) {
      const model = app.model;
      const shown =
        model.viewMode === "columns" && model.search === null
          ? model.visibleEntries(model.folder)
          : model.shownEntries();
      const selected = model.selection.length;
      const text =
        selected > 0 ? `${selected} of ${formatItemCount(shown.length)} selected` : formatItemCount(shown.length);
      return m(
        "footer.files-status",
        {
          class: "flex h-7 shrink-0 items-center gap-3 border-t border-default bg-surface px-4 type-helper text-faint",
        },
        [m("span.files-status-text", text)],
      );
    },
  };
}

function UploadPanel(): m.Component<{ app: FilesController }> {
  return {
    view({ attrs: { app } }) {
      const uploads = app.model.uploads;
      if (uploads.items.length === 0) return null;
      const { loaded, total } = uploads.progress;
      const busy = uploads.isBusy;
      const failed = uploads.items.filter((item) => item.status === "failed").length;
      const done = uploads.items.filter((item) => item.status === "done").length;
      const summary = busy
        ? `Uploading ${uploads.items.filter((item) => item.status === "queued" || item.status === "uploading").length} of ${uploads.items.length}`
        : failed > 0
          ? `${failed} upload${failed === 1 ? "" : "s"} failed`
          : `Uploaded ${formatItemCount(done)}`;
      const percent = total === 0 ? 100 : Math.round((loaded / total) * 100);
      return m(
        "section.files-uploads",
        {
          class:
            "fixed right-4 bottom-10 z-(--z-sticky) flex w-[320px] max-w-[calc(100vw-32px)] flex-col overflow-hidden rounded-xl border border-default bg-surface shadow-overlay",
        },
        [
          m("div", { class: "flex items-center gap-2 px-3 pt-2.5 pb-2" }, [
            m("div", { class: "min-w-0 flex-1" }, [
              m("div.files-uploads-summary", { class: "type-label text-primary" }, summary),
              m("div", { class: "type-helper text-faint" }, `${formatSize(loaded)} of ${formatSize(total)}`),
            ]),
            busy
              ? m(Button, { sm: true, variant: "ghost", onclick: () => uploads.cancelAll() }, "Cancel")
              : m(
                  Button,
                  {
                    sm: true,
                    variant: "ghost",
                    "data-action": "dismiss-uploads",
                    onclick: () => uploads.clearFinished(),
                  },
                  "Done",
                ),
          ]),
          m(
            "div",
            { class: "mx-3 mb-2 h-1 overflow-hidden rounded-full bg-fill-hover" },
            m("div", {
              class: `h-full rounded-full ${failed > 0 && !busy ? "bg-danger" : "bg-accent"}`,
              style: `width:${percent}%`,
            }),
          ),
          m(
            "ul",
            { class: "m-0 max-h-[180px] list-none overflow-y-auto border-t border-subtle p-0 py-1" },
            uploads.items.map((item) =>
              m(
                "li.files-upload",
                { key: item.id, "data-status": item.status, class: "flex items-center gap-2 px-3 py-1 type-helper" },
                [
                  m(
                    "span",
                    { class: "min-w-0 flex-1 truncate text-primary", title: item.error ?? item.name },
                    item.name,
                  ),
                  m(
                    "span",
                    { class: `shrink-0 ${item.status === "failed" ? "text-danger" : "text-faint"}` },
                    item.status === "uploading"
                      ? `${Math.round((item.loaded / Math.max(item.file.size, 1)) * 100)}%`
                      : item.status === "done"
                        ? m.trust(icon("check", { size: 13, className: "text-success" }))
                        : item.status === "failed"
                          ? "Failed"
                          : item.status === "canceled"
                            ? "Canceled"
                            : "Waiting",
                  ),
                ],
              ),
            ),
          ),
        ],
      );
    },
  };
}

function Notice(): m.Component<{ app: FilesController }> {
  return {
    view({ attrs: { app } }) {
      const notice = app.model.notice;
      if (notice === null) return null;
      return m(
        "div.files-notice",
        {
          role: "alert",
          class:
            "fixed bottom-10 left-1/2 z-(--z-sticky) flex max-w-[min(480px,calc(100vw-32px))] -translate-x-1/2 items-start gap-3 rounded-lg bg-inverse px-4 py-2.5 type-body whitespace-pre-line text-on-accent shadow-overlay",
        },
        [
          m("span", { class: "min-w-0 flex-1" }, notice),
          m(
            "button",
            {
              type: "button",
              "aria-label": "Dismiss",
              class: "cursor-pointer text-white/70 hover:text-white",
              onclick: () => app.model.dismissNotice(),
            },
            m.trust(icon("close", { size: 14 })),
          ),
        ],
      );
    },
  };
}

// Dragging in

/** The folder a drag over `target` would drop into: a folder under the pointer, else the folder on show. */
function dropFolderAt(app: FilesController, target: EventTarget | null): string {
  const element = target instanceof Element ? target.closest(`[${DROP_FOLDER_ATTR}]`) : null;
  return element?.getAttribute(DROP_FOLDER_ATTR) ?? app.model.folder;
}

function installDropHandling(app: FilesController, root: HTMLElement): () => void {
  const model = app.model;
  const isEntryDrag = (event: DragEvent): boolean =>
    event.dataTransfer !== null && Array.from(event.dataTransfer.types).includes(ENTRY_DRAG_TYPE);
  const setTarget = (folder: string | null): void => {
    if (model.dropTarget === folder) return;
    model.dropTarget = folder;
    m.redraw();
  };
  const onDragOver = (event: DragEvent): void => {
    const fromOutside = isFileDrag(event.dataTransfer);
    if (!fromOutside && !isEntryDrag(event)) return;
    event.preventDefault();
    const folder = dropFolderAt(app, event.target);
    if (event.dataTransfer !== null) event.dataTransfer.dropEffect = fromOutside ? "copy" : "move";
    setTarget(folder);
  };
  const onDragLeave = (event: DragEvent): void => {
    if (event.relatedTarget === null || !root.contains(event.relatedTarget as Node)) setTarget(null);
  };
  const onDrop = (event: DragEvent): void => {
    const transfer = event.dataTransfer;
    if (transfer === null) return;
    const folder = dropFolderAt(app, event.target);
    setTarget(null);
    if (isFileDrag(transfer)) {
      event.preventDefault();
      void sourcesFromDrop(transfer).then((sources) => model.uploadInto(folder, sources));
      return;
    }
    if (isEntryDrag(event)) {
      event.preventDefault();
      const paths = JSON.parse(transfer.getData(ENTRY_DRAG_TYPE)) as string[];
      void model.moveInto(paths, folder);
    }
  };
  const onDragEnd = (): void => setTarget(null);
  root.addEventListener("dragover", onDragOver);
  root.addEventListener("dragleave", onDragLeave);
  root.addEventListener("drop", onDrop);
  root.addEventListener("dragend", onDragEnd);
  return () => {
    root.removeEventListener("dragover", onDragOver);
    root.removeEventListener("dragleave", onDragLeave);
    root.removeEventListener("drop", onDrop);
    root.removeEventListener("dragend", onDragEnd);
  };
}

// The window

export function FilesApp(): m.Component<{ app: FilesController }> {
  let uninstall: (() => void) | null = null;
  let onKeydown: ((event: KeyboardEvent) => void) | null = null;
  return {
    oncreate({ dom, attrs: { app } }) {
      uninstall = installDropHandling(app, dom as HTMLElement);
      onKeydown = (event) => handleKeydown(app, event);
      document.addEventListener("keydown", onKeydown);
    },
    onupdate({ dom, attrs: { app } }) {
      if (!app.revealSelection) return;
      app.revealSelection = false;
      const last = app.model.selection[app.model.selection.length - 1];
      if (last === undefined) return;
      const element = dom.querySelector(`[data-entry-path="${CSS.escape(last)}"]`);
      element?.scrollIntoView({ block: "nearest", inline: "nearest" });
    },
    onremove() {
      uninstall?.();
      if (onKeydown !== null) document.removeEventListener("keydown", onKeydown);
    },
    view({ attrs: { app } }) {
      const model = app.model;
      const fileDropOnFolder = model.dropTarget !== null && model.dropTarget === model.folder;
      return m("div.files-app", { class: "flex h-screen min-h-0 bg-surface text-primary" }, [
        m(Sidebar, { app }),
        m("div", { class: "flex min-w-0 flex-1 flex-col border-l border-default" }, [
          m(Toolbar, { app }),
          m(
            "main.files-folder",
            {
              [FOLDER_SURFACE_ATTR]: model.folder,
              class: `relative min-h-0 flex-1 ${app.viewMode === "columns" && model.search === null ? "overflow-hidden" : "overflow-y-auto"} ${
                fileDropOnFolder ? "bg-accent-light/50 outline-2 -outline-offset-4 outline-accent outline-dashed" : ""
              }`,
              onclick: () => {
                if (model.selection.length > 0) model.clearSelection();
              },
            },
            m(FolderBody, { app }),
          ),
          m(StatusBar, { app }),
        ]),
        m(UploadPanel, { app }),
        m(Notice, { app }),
        app.dialogs.view(),
      ]);
    },
  };
}
