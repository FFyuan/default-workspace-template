/**
 * The page's state: which page the path names, what the API answered for it, the polling, the schedule
 * editor, and the toasts a failed action is reported with.
 */

import m from "mithril";

import { Toasts } from "@imbue/workspace-ui/src/components/toasts";
import { ToastQueue } from "@imbue/workspace-ui/src/models/toasts";

import {
  fetchDetail,
  fetchListing,
  fetchRun,
  openFixChat,
  removeRoutine,
  runNow,
  setEnabled,
  setSchedule,
  type RoutineDetail,
  type RoutineListing,
  type RunDetail,
} from "../models/api";
import { pageOf, routinePathOf, titleOf, type Page } from "../models/routing";
import { changeOf, formOf, type ScheduleForm } from "../models/schedule";
import { ListPage } from "./ListPage";
import { RoutinePage } from "./RoutinePage";
import { RunPage } from "./RunPage";
import { ScheduleDialog } from "./ScheduleDialog";

/** How often the page re-reads: faster while a run is going, since that is when it is being watched. */
export const IDLE_REFRESH_MS = 30_000;
export const RUNNING_REFRESH_MS = 5_000;

export interface AppHost {
  /** Tell the shell where the page is and what it is called. */
  reportLocation: (path: string, title: string) => void;
  /** Start a chat with the text (the list's add field). */
  startWithText: (text: string) => void;
  /** Ask the user to confirm removing a routine. */
  confirmRemove: (title: string) => Promise<boolean>;
  navigate: (path: string) => void;
}

type Loaded =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "list"; listing: RoutineListing }
  | { kind: "routine"; detail: RoutineDetail }
  | { kind: "run"; detail: RunDetail; routineTitle: string };

export class AppModel {
  readonly page: Page;
  loaded: Loaded = { kind: "loading" };
  scheduleForm: ScheduleForm | null = null;
  isBusy = false;
  readonly toasts: ToastQueue;
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    pathname: string,
    private readonly host: AppHost,
    private readonly redraw: () => void,
  ) {
    this.page = pageOf(pathname);
    this.toasts = new ToastQueue(redraw);
  }

  async load(): Promise<void> {
    try {
      switch (this.page.kind) {
        case "list": {
          const listing = await fetchListing();
          this.loaded = { kind: "list", listing };
          this.host.reportLocation("/", titleOf(this.page, null));
          break;
        }
        case "routine": {
          const detail = await fetchDetail(this.page.routineId);
          this.loaded = { kind: "routine", detail };
          this.host.reportLocation(routinePathOf(this.page.routineId), titleOf(this.page, detail.row.title));
          break;
        }
        case "run": {
          const [detail, routine] = await Promise.all([
            fetchRun(this.page.routineId, this.page.runId),
            fetchDetail(this.page.routineId),
          ]);
          this.loaded = { kind: "run", detail, routineTitle: routine.row.title };
          this.host.reportLocation(location.pathname, titleOf(this.page, routine.row.title));
          break;
        }
      }
    } catch (error) {
      this.loaded = { kind: "error", message: error instanceof Error ? error.message : String(error) };
    }
    this.redraw();
    this.scheduleRefresh();
  }

  private scheduleRefresh(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    const isRunning =
      (this.loaded.kind === "list" && this.loaded.listing.summary.running > 0) ||
      (this.loaded.kind === "routine" && this.loaded.detail.row.is_running);
    this.timer = setTimeout(
      () => {
        // Never redraw under an open editor: that would throw away a half-made choice.
        if (this.scheduleForm !== null) this.scheduleRefresh();
        else void this.load();
      },
      isRunning ? RUNNING_REFRESH_MS : IDLE_REFRESH_MS,
    );
  }

  private async act(action: () => Promise<void>, failure: string): Promise<void> {
    this.isBusy = true;
    this.redraw();
    try {
      await action();
    } catch (error) {
      this.toasts.show(`${failure}: ${error instanceof Error ? error.message : String(error)}`);
    }
    this.isBusy = false;
    await this.load();
  }

  runNow(): void {
    if (this.page.kind !== "routine") return;
    const routineId = this.page.routineId;
    void this.act(async () => {
      await runNow(routineId);
    }, "Couldn't start it");
  }

  toggleEnabled(): void {
    if (this.page.kind !== "routine" || this.loaded.kind !== "routine") return;
    const routineId = this.page.routineId;
    const isEnabled = !this.loaded.detail.row.is_enabled;
    void this.act(async () => {
      await setEnabled(routineId, isEnabled);
    }, "Couldn't change it");
  }

  openScheduleEditor(): void {
    if (this.loaded.kind !== "routine" || this.loaded.detail.definition === null) return;
    this.scheduleForm = formOf(this.loaded.detail.definition);
  }

  closeScheduleEditor(): void {
    this.scheduleForm = null;
  }

  saveSchedule(): void {
    if (this.page.kind !== "routine" || this.scheduleForm === null) return;
    const routineId = this.page.routineId;
    const change = changeOf(this.scheduleForm);
    void this.act(async () => {
      await setSchedule(routineId, change);
      this.scheduleForm = null;
    }, "Couldn't change the schedule");
  }

  fix(): void {
    if (this.page.kind !== "routine") return;
    const routineId = this.page.routineId;
    void this.act(async () => {
      await openFixChat(routineId);
      this.toasts.show("A chat is opening with everything the agent needs to start.");
    }, "Couldn't start a chat");
  }

  remove(): void {
    if (this.page.kind !== "routine" || this.loaded.kind !== "routine") return;
    const routineId = this.page.routineId;
    const title = this.loaded.detail.row.title;
    void (async () => {
      if (!(await this.host.confirmRemove(title))) return;
      await this.act(async () => {
        await removeRoutine(routineId);
        this.host.navigate("/");
      }, "Couldn't remove it");
    })();
  }

  startWithText(text: string): void {
    this.host.startWithText(text);
  }
}

export interface AppAttrs {
  model: AppModel;
  appNames: Record<string, string>;
}

export const App: m.Component<AppAttrs> = {
  view({ attrs: { model, appNames } }) {
    const { loaded } = model;
    let body: m.Children;
    switch (loaded.kind) {
      case "loading":
        body = m("p", { class: "type-body p-6 text-faint", "data-loading": "" }, "Loading.");
        break;
      case "error":
        body = m(
          "p",
          { class: "type-body p-6 text-danger", "data-error": "" },
          `Couldn't read your routines: ${loaded.message}`,
        );
        break;
      case "list":
        body = m(ListPage, {
          listing: loaded.listing,
          appNames,
          onStartWithText: (text) => model.startWithText(text),
        });
        break;
      case "routine":
        body = m(RoutinePage, {
          detail: loaded.detail,
          isBusy: model.isBusy,
          onRunNow: () => model.runNow(),
          onToggleEnabled: () => model.toggleEnabled(),
          onChangeSchedule: () => model.openScheduleEditor(),
          onFix: () => model.fix(),
          onRemove: () => model.remove(),
        });
        break;
      case "run":
        body = m(RunPage, { detail: loaded.detail, routineTitle: loaded.routineTitle });
        break;
    }
    return [
      body,
      model.scheduleForm === null
        ? null
        : m(ScheduleDialog, {
            form: model.scheduleForm,
            isSaving: model.isBusy,
            onChange: (form) => {
              model.scheduleForm = form;
            },
            onSave: () => model.saveSchedule(),
            onCancel: () => model.closeScheduleEditor(),
          }),
      m(Toasts, {
        toasts: model.toasts.current(),
        placementClass: "fixed bottom-4",
        onDismiss: (id) => model.toasts.dismiss(id),
      }),
    ];
  },
};
