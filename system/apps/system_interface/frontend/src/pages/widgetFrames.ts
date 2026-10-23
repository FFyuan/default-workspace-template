/**
 * The widget frames (app-widgets plan sections 4 and 6): one iframe per enabled widget, at the app's widget path,
 * created when the widget is first enabled in this client and destroyed when it is disabled or withdrawn. As the
 * live pages are, a frame is never re-parented (that reloads it); the reconcile step lays each frame over its
 * widget's content box once the chrome is drawn.
 *
 * A widget is not drawn until its page reports a size, so a frame the chrome has no box for yet is kept loaded
 * but out of sight, at the largest size a widget may take, where its page can lay itself out and measure.
 *
 * The shell side of the app contract for a widget lives here: the handshake after every load and on a desktop
 * change (``surface: "widget"``, no window), the mode after every handshake and on every change, and the page's
 * own ``shell:widget-size`` and ``shell:widget-hidden``. The rest of what a widget's page may send (an open, a
 * message, a link) the live pages layer takes, asking ``appOfFrame`` whose frame it is. Messages cross through
 * ``relay.ts``.
 */

import {
  SHELL_HANDSHAKE,
  SHELL_WIDGET_HIDDEN,
  SHELL_WIDGET_MODE,
  SHELL_WIDGET_SIZE,
} from "@imbue/workspace-ui/src/app_contract";
import type { WidgetMode } from "@imbue/workspace-ui/src/app_contract";
import { windowPageUrl } from "../model/pageUrl";
import type { AppRecord } from "../model/records";
import { shownWidgets } from "../reducers/desktopState";
import { sendToChildFrame, setChildFrameMessageHandler } from "../relay";
import type { DesktopStore } from "../store/DesktopStore";
import { PAGE_FRAME_ALLOW, PAGE_FRAME_SANDBOX } from "./livePages";

export const WIDGET_FRAME_ATTRIBUTE = "data-widget-frame";
/** The element of a widget's chrome that carries its app; the layer finds the content box under it. */
export const WIDGET_ATTRIBUTE = "data-widget";
/** The element of a widget's chrome its page is laid over. */
export const WIDGET_CONTENT_ATTRIBUTE = "data-widget-content";

interface WidgetFrame {
  readonly app: string;
  readonly path: string;
  readonly wrapper: HTMLElement;
  readonly frame: HTMLIFrameElement;
  /** The desktop the page was last introduced to; null before its first load. */
  greetedDesktopId: string | null;
  /** The mode the page was last told; null until it has been told one since it loaded. */
  sentMode: WidgetMode | null;
}

export interface WidgetFramesOptions {
  /** The shell document's host and protocol, which every page URL derives from. */
  readonly host: string;
  readonly protocol: string;
}

export class WidgetFramesLayer {
  private readonly frames = new Map<string, WidgetFrame>();
  private isGestureActive = false;

  constructor(
    private readonly host: HTMLElement,
    private readonly store: DesktopStore,
    private readonly options: WidgetFramesOptions,
  ) {}

  /** Register the widget messages of the contract. */
  start(): void {
    setChildFrameMessageHandler(SHELL_WIDGET_SIZE, (frame, payload) => this.takeSize(frame, payload));
    setChildFrameMessageHandler(SHELL_WIDGET_HIDDEN, (frame, payload) => this.takeHidden(frame, payload));
  }

  /** Stop: every frame goes, and what its page said with it. */
  stop(): void {
    for (const widget of [...this.frames.values()]) this.destroy(widget);
  }

  /** Whether this layer's frames live in ``host``. */
  isOver(host: HTMLElement): boolean {
    return this.host === host;
  }

  /** The app whose widget ``frame`` shows, or null for a frame that is no widget's. */
  appOfFrame(frame: HTMLIFrameElement): string | null {
    const app = frame.getAttribute(WIDGET_FRAME_ATTRIBUTE);
    return app !== null && this.frames.get(app)?.frame === frame ? app : null;
  }

  /** Make every widget inert for the length of a press on a handle, as the live pages are. */
  setGestureActive(isActive: boolean): void {
    if (this.isGestureActive === isActive) return;
    this.isGestureActive = isActive;
    this.reconcile();
  }

  /** Lay one widget's frame over its content box as it is now: the per-move step of its drag. */
  placeFrame(app: string): void {
    const widget = this.frames.get(app);
    if (widget !== undefined) this.place(widget);
  }

  /**
   * Bring the frames in line with the widgets this client shows: a frame per enabled widget (one at a changed
   * path is made anew), each laid over its content box or kept out of sight until the chrome draws one, and
   * every page told the client's mode and active desktop. Run after each redraw.
   */
  reconcile(): void {
    const state = this.store.getState();
    const shown = new Map(shownWidgets(state).map((widget) => [widget.app.name, widget]));
    for (const widget of [...this.frames.values()]) {
      const wanted = shown.get(widget.app);
      if (wanted === undefined || wanted.app.widget?.path !== widget.path) this.destroy(widget);
    }
    for (const { app, presentation } of shown.values()) {
      const widget = this.frames.get(app.name) ?? this.create(app);
      if (widget === null) continue;
      this.place(widget);
      if (widget.greetedDesktopId === null) continue;
      if (widget.greetedDesktopId !== (state.activeDesktopId ?? "")) this.greet(widget);
      else if (widget.sentMode !== this.modeOf(presentation.mode))
        this.sendMode(widget, this.modeOf(presentation.mode));
    }
  }

  private create(app: AppRecord): WidgetFrame | null {
    if (app.widget === null) return null;
    const wrapper = document.createElement("div");
    wrapper.className = "widget-frame absolute overflow-hidden";
    const frame = document.createElement("iframe");
    frame.setAttribute(WIDGET_FRAME_ATTRIBUTE, app.name);
    frame.setAttribute("sandbox", PAGE_FRAME_SANDBOX);
    frame.setAttribute("allow", PAGE_FRAME_ALLOW);
    frame.title = `${app.display_name} widget`;
    frame.className = "block h-full w-full border-0 bg-transparent";
    wrapper.appendChild(frame);
    const widget: WidgetFrame = {
      app: app.name,
      path: app.widget.path,
      wrapper,
      frame,
      greetedDesktopId: null,
      sentMode: null,
    };
    // Every load, not just the first: a reload is a fresh page that has said nothing and been told nothing.
    frame.addEventListener("load", () => {
      widget.sentMode = null;
      this.store.resetWidgetReport(widget.app);
      this.greet(widget);
    });
    this.frames.set(app.name, widget);
    this.host.appendChild(wrapper);
    frame.setAttribute("src", windowPageUrl(app, app.widget.path, this.options.host, this.options.protocol));
    return widget;
  }

  private destroy(widget: WidgetFrame): void {
    this.frames.delete(widget.app);
    widget.wrapper.remove();
    this.store.resetWidgetReport(widget.app);
  }

  /** Over the widget's content box when the chrome draws one; else loaded but out of sight, at the largest size a
   *  widget may take, so its page lays itself out and reports. */
  private place(widget: WidgetFrame): void {
    const style = widget.wrapper.style;
    const box = this.contentBox(widget.app);
    if (box === null) {
      const metrics = this.store.getMetrics();
      Object.assign(style, {
        left: "0px",
        top: "0px",
        width: `${metrics.widgetMaxWidth}px`,
        height: `${metrics.widgetMaxHeight}px`,
        visibility: "hidden",
        pointerEvents: "none",
      });
      return;
    }
    Object.assign(style, {
      left: `${box.left}px`,
      top: `${box.top}px`,
      width: `${box.width}px`,
      height: `${box.height}px`,
      visibility: "",
      pointerEvents: this.isGestureActive ? "none" : "auto",
    });
  }

  private contentBox(app: string): { left: number; top: number; width: number; height: number } | null {
    const content = this.host.parentElement?.querySelector<HTMLElement>(
      `[${WIDGET_ATTRIBUTE}="${CSS.escape(app)}"] [${WIDGET_CONTENT_ATTRIBUTE}]`,
    );
    if (content === undefined || content === null) return null;
    const box = content.getBoundingClientRect();
    if (box.width <= 0 || box.height <= 0) return null;
    const origin = this.host.getBoundingClientRect();
    return { left: box.left - origin.left, top: box.top - origin.top, width: box.width, height: box.height };
  }

  /** The handshake names the client's active desktop, where anything the widget opens lands; the mode follows. */
  private greet(widget: WidgetFrame): void {
    const state = this.store.getState();
    const desktopId = state.activeDesktopId ?? "";
    sendToChildFrame(widget.frame, SHELL_HANDSHAKE, {
      clientId: state.clientId,
      windowId: null,
      desktopId,
      app: widget.app,
      path: widget.path,
      surface: "widget",
    });
    widget.greetedDesktopId = desktopId;
    const shown = shownWidgets(state).find((candidate) => candidate.app.name === widget.app);
    if (shown !== undefined) this.sendMode(widget, this.modeOf(shown.presentation.mode));
  }

  /** The mode a widget is drawn in: the client's, except on a phone, which draws every widget collapsed. */
  private modeOf(chosen: WidgetMode): WidgetMode {
    return this.store.isPhoneLayout() ? "collapsed" : chosen;
  }

  private sendMode(widget: WidgetFrame, mode: WidgetMode): void {
    widget.sentMode = mode;
    sendToChildFrame(widget.frame, SHELL_WIDGET_MODE, { mode });
  }

  private takeSize(frame: HTMLIFrameElement, payload: Record<string, unknown>): void {
    const app = this.appOfFrame(frame);
    const { width, height } = payload;
    if (app === null || typeof width !== "number" || typeof height !== "number") return;
    if (!Number.isFinite(width) || !Number.isFinite(height)) return;
    this.store.reportWidgetSize(app, { width, height });
  }

  private takeHidden(frame: HTMLIFrameElement, payload: Record<string, unknown>): void {
    const app = this.appOfFrame(frame);
    if (app === null || typeof payload.isHidden !== "boolean") return;
    this.store.reportWidgetHidden(app, payload.isHidden);
  }
}
