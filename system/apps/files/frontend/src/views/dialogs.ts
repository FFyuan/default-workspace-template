/**
 * The questions the app stops to ask: whether to delete, what to do about names already taken by an upload, and
 * what to call a file renamed from its own page. Each is a promise its caller awaits; one dialog shows at a time.
 */

import m from "mithril";

import { Button } from "@imbue/workspace-ui/src/components/Button";
import { inputClass } from "@imbue/workspace-ui/src/components/Input";
import { MODAL_MESSAGE_CLASS, Modal } from "@imbue/workspace-ui/src/components/Modal";

import type { Entry } from "../models/dufs";
import type { ConflictChoice } from "../models/FilesModel";
import { invalidNameReason, stemLength } from "../models/paths";

type Dialog =
  | { kind: "delete"; entries: readonly Entry[]; resolve: (confirmed: boolean) => void }
  | { kind: "replace"; names: readonly string[]; resolve: (choice: ConflictChoice) => void }
  | {
      kind: "rename";
      name: string;
      draft: string;
      error: string | null;
      resolve: (name: string | null) => void;
    };

/** How many names a dialog lists before it says "and N more". */
const LISTED_NAMES = 5;

function listedNames(names: readonly string[]): m.Children {
  const shown = names.slice(0, LISTED_NAMES);
  const more = names.length - shown.length;
  return m("ul.files-dialog-names.mb-4.list-none.p-0.type-body.text-secondary", [
    shown.map((name) => m("li.truncate", { key: name }, name)),
    more > 0 ? m("li", `and ${more} more`) : null,
  ]);
}

export class Dialogs {
  current: Dialog | null = null;

  confirmDelete(entries: readonly Entry[]): Promise<boolean> {
    return new Promise((resolve) => this.show({ kind: "delete", entries, resolve }));
  }

  confirmReplace(names: readonly string[]): Promise<ConflictChoice> {
    return new Promise((resolve) => this.show({ kind: "replace", names, resolve }));
  }

  /** Ask for a new name for `name`; null when the user backs out. */
  askName(name: string): Promise<string | null> {
    return new Promise((resolve) => this.show({ kind: "rename", name, draft: name, error: null, resolve }));
  }

  private show(dialog: Dialog): void {
    this.dismiss();
    this.current = dialog;
    m.redraw();
  }

  /** Close whatever is open, answering it as a cancel. */
  dismiss(): void {
    const dialog = this.current;
    if (dialog === null) return;
    this.current = null;
    if (dialog.kind === "delete") dialog.resolve(false);
    else if (dialog.kind === "replace") dialog.resolve("cancel");
    else dialog.resolve(null);
  }

  private answer(settle: () => void): void {
    this.current = null;
    settle();
  }

  view(): m.Children {
    const dialog = this.current;
    if (dialog === null) return null;
    const dismiss = (): void => this.dismiss();
    if (dialog.kind === "delete") {
      const names = dialog.entries.map((entry) => entry.name);
      const title = names.length === 1 ? `Delete "${names[0]}"?` : `Delete ${names.length} items?`;
      return m(
        Modal,
        {
          title,
          onDismiss: dismiss,
          onEscape: dismiss,
          card: { "data-dialog": "delete", role: "alertdialog" },
          actions: [
            m(Button, { onclick: dismiss }, "Cancel"),
            m(
              Button,
              {
                variant: "destructive",
                "data-dialog-action": "confirm",
                oncreate: ({ dom }: { dom: Element }) => (dom as HTMLElement).focus(),
                onclick: () => this.answer(() => dialog.resolve(true)),
              },
              "Delete",
            ),
          ],
        },
        [
          names.length > 1 ? listedNames(names) : null,
          m("p", { class: MODAL_MESSAGE_CLASS }, "This can't be undone."),
        ],
      );
    }
    if (dialog.kind === "replace") {
      const title =
        dialog.names.length === 1
          ? `"${dialog.names[0]}" already exists here`
          : `${dialog.names.length} items already exist here`;
      return m(
        Modal,
        {
          title,
          onDismiss: dismiss,
          onEscape: dismiss,
          width: 460,
          card: { "data-dialog": "replace", role: "alertdialog" },
          actions: [
            m(Button, { onclick: dismiss }, "Cancel"),
            m(
              Button,
              { "data-dialog-action": "keep-both", onclick: () => this.answer(() => dialog.resolve("keep-both")) },
              "Keep both",
            ),
            m(
              Button,
              {
                variant: "primary",
                "data-dialog-action": "replace",
                oncreate: ({ dom }: { dom: Element }) => (dom as HTMLElement).focus(),
                onclick: () => this.answer(() => dialog.resolve("replace")),
              },
              "Replace",
            ),
          ],
        },
        [
          dialog.names.length > 1 ? listedNames(dialog.names) : null,
          m(
            "p",
            { class: MODAL_MESSAGE_CLASS },
            "Replace what's there with what you're adding, or keep both by giving the new ones a number.",
          ),
        ],
      );
    }
    const submit = (): void => {
      const name = dialog.draft.trim();
      const problem = invalidNameReason(name);
      if (problem !== null) {
        dialog.error = problem;
        return;
      }
      this.answer(() => dialog.resolve(name === dialog.name ? null : name));
    };
    return m(
      Modal,
      {
        title: "Rename",
        onDismiss: dismiss,
        onEscape: dismiss,
        card: { "data-dialog": "rename" },
        actions: [
          m(Button, { onclick: dismiss }, "Cancel"),
          m(Button, { variant: "primary", "data-dialog-action": "rename", onclick: submit }, "Rename"),
        ],
      },
      [
        m("input", {
          class: inputClass({ extra: "mb-2" }),
          value: dialog.draft,
          "aria-label": "New name",
          oncreate: ({ dom }: { dom: Element }) => {
            const input = dom as HTMLInputElement;
            input.focus();
            input.setSelectionRange(0, stemLength(dialog.name));
          },
          oninput: (event: InputEvent) => {
            dialog.draft = (event.target as HTMLInputElement).value;
            dialog.error = null;
          },
          onkeydown: (event: KeyboardEvent) => {
            if (event.key === "Enter") submit();
          },
        }),
        m("p.type-helper.mb-2.min-h-4.text-danger", dialog.error ?? ""),
      ],
    );
  }
}
