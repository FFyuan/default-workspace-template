/**
 * The widgets a client put in the taskbar's tray (app-widgets plan section 4.10): a slot per widget beside the
 * desktop switcher, the size its page last reported for its tray form, and above the bar the popover of the one
 * whose page was clicked, the size its page reports expanded. Each is only a box: the widget frames layer lays the
 * widget's one frame over the slot, or over the popover's content box while it is open, so the page moves between
 * them without reloading. The popover is the desktop widget's panel, with no rim to drag; a click elsewhere or
 * Escape closes it. Nothing here measures the DOM or listens for gestures.
 */

import m from "mithril";
import type { PixelSize } from "../geometry/frames";
import type { AppRecord } from "../model/records";
import { WIDGET_ATTRIBUTE, WIDGET_CONTENT_ATTRIBUTE, WIDGET_POPOVER_ATTRIBUTE } from "../pages/widgetFrames";

/** One widget in the tray: its app and the size its page reported for its tray form. */
export interface TrayWidget {
  readonly app: AppRecord;
  readonly size: PixelSize;
}

export interface TrayWidgetSlotsAttrs {
  readonly widgets: readonly TrayWidget[];
  readonly popoverApp: string | null;
  /** A right-click on a slot its page does not cover (while its popover is open): the widget's menu. */
  readonly onContextMenu: (app: string, x: number, y: number, target: Element) => void;
}

/** The slots, inside the system tray's row. */
export const TrayWidgetSlots: m.Component<TrayWidgetSlotsAttrs> = {
  view(vnode) {
    const { widgets, popoverApp, onContextMenu } = vnode.attrs;
    return widgets.map(({ app, size }) =>
      m(
        "div",
        {
          key: app.name,
          [WIDGET_ATTRIBUTE]: app.name,
          "data-tray-widget": app.name,
          "data-popover-open": popoverApp === app.name ? "true" : "false",
          class:
            "tray-widget flex max-h-(--desk-widget-tray-height) max-w-(--desk-widget-tray-max-width) shrink-0 " +
            "overflow-hidden rounded-md " +
            (popoverApp === app.name ? "bg-fill-hover" : "hover:bg-fill-hover"),
          style: { width: `${size.width}px`, height: `${size.height}px` },
          oncontextmenu: (event: MouseEvent) => {
            event.preventDefault();
            onContextMenu(app.name, event.clientX, event.clientY, event.target as Element);
          },
        },
        m("div", { [WIDGET_CONTENT_ATTRIBUTE]: "", class: "min-h-0 min-w-0 flex-1" }),
      ),
    );
  },
};

export interface TrayWidgetPopoverAttrs {
  readonly app: string;
  /** The size its page reported expanded, clamped to the theme's widget maximum. */
  readonly size: PixelSize;
}

/** The open popover, above the bar at its right end. */
export const TrayWidgetPopover: m.Component<TrayWidgetPopoverAttrs> = {
  view(vnode) {
    const { app, size } = vnode.attrs;
    return m(
      "div",
      {
        [WIDGET_POPOVER_ATTRIBUTE]: app,
        class:
          "tray-widget-popover absolute right-2 bottom-full z-(--z-sticky) mb-2 flex overflow-hidden " +
          "rounded-(--desk-widget-radius) border border-(--desk-widget-edge) bg-(--desk-widget-surface) " +
          "p-(--desk-widget-rim) shadow-raised backdrop-blur-xl",
      },
      m("div", {
        [WIDGET_CONTENT_ATTRIBUTE]: "",
        class: "min-h-0 min-w-0",
        style: { width: `${size.width}px`, height: `${size.height}px` },
      }),
    );
  },
};
