/**
 * The widgets' chrome (app-widgets plan section 4): a layer above every window and live page, beside the floating
 * entries' at the theme's sticky level, drawing for each widget its page reported a size for a box at its place in
 * its corner: a grip along its top, which drags it to another corner and carries the collapse/expand chevron and
 * the menu, over the content box the widget frames layer lays the page on. At rest a widget is see-through; under
 * the pointer, or with its menu open, it is not. The layer is inert; only each widget's box takes a press. Nothing
 * here measures the DOM or listens for gestures.
 */

import m from "mithril";
import { icon } from "@imbue/workspace-ui/src/components/icons";
import { targetElementOf } from "@imbue/workspace-ui/src/context_menu_rows";
import type { PixelRect } from "../geometry/frames";
import type { ShownWidget } from "../reducers/desktopState";
import { WIDGET_GRIP_ATTRIBUTE } from "../gestures/pointerGestures";
import { WIDGET_ATTRIBUTE, WIDGET_CONTENT_ATTRIBUTE } from "../pages/widgetFrames";
import { rectStyle } from "./pixelStyle";

export interface WidgetsAttrs {
  readonly widgets: readonly ShownWidget[];
  /** Where each drawn widget's box is, in backdrop pixels; a widget with none is not drawn. */
  readonly rects: ReadonlyMap<string, PixelRect>;
  readonly openMenuApp: string | null;
  readonly onToggleMode: (app: string) => void;
  readonly onContextMenu: (app: string, x: number, y: number, target: Element) => void;
}

export const Widgets: m.Component<WidgetsAttrs> = {
  view(vnode) {
    const attrs = vnode.attrs;
    return m(
      "div",
      { "data-widgets": "", class: "widgets pointer-events-none absolute inset-0 z-(--z-sticky)" },
      attrs.widgets.flatMap(({ app, presentation }): m.Children[] => {
        const rect = attrs.rects.get(app.name);
        if (rect === undefined) return [];
        const isCollapsed = presentation.mode === "collapsed";
        const isMenuOpen = attrs.openMenuApp === app.name;
        const toggleLabel = `${isCollapsed ? "Expand" : "Collapse"} the ${app.display_name} widget`;
        return [
          m(
            "div",
            {
              key: app.name,
              [WIDGET_ATTRIBUTE]: app.name,
              "data-widget-corner": presentation.corner,
              "data-widget-mode": presentation.mode,
              class:
                "widget pointer-events-auto absolute flex flex-col overflow-hidden rounded-lg border border-default " +
                "bg-surface shadow-raised transition-opacity hover:opacity-100 " +
                (isMenuOpen ? "opacity-100 ring-2 ring-accent" : "opacity-(--desk-widget-rest-opacity)"),
              style: rectStyle(rect),
              oncontextmenu: (event: MouseEvent) => {
                event.preventDefault();
                attrs.onContextMenu(app.name, event.clientX, event.clientY, targetElementOf(event));
              },
            },
            [
              m(
                "div",
                {
                  [WIDGET_GRIP_ATTRIBUTE]: app.name,
                  "aria-label": `Move the ${app.display_name} widget`,
                  class:
                    "widget-grip flex h-(--desk-widget-grip-size) shrink-0 cursor-grab touch-none select-none " +
                    "items-center justify-end bg-hover px-1 text-secondary",
                },
                m(
                  "button",
                  {
                    type: "button",
                    "data-widget-control": isCollapsed ? "expand" : "collapse",
                    "data-no-drag": "",
                    "aria-label": toggleLabel,
                    title: toggleLabel,
                    class:
                      "flex h-full cursor-pointer items-center border-0 bg-transparent p-0 text-secondary " +
                      "hover:text-primary [&>svg]:h-full [&>svg]:w-auto " +
                      (isCollapsed ? "" : "[&>svg]:rotate-180"),
                    onclick: () => attrs.onToggleMode(app.name),
                  },
                  m.trust(icon("chevron-down")),
                ),
              ),
              m("div", { [WIDGET_CONTENT_ATTRIBUTE]: "", class: "widget-content min-h-0 flex-1" }),
            ],
          ),
        ];
      }),
    );
  },
};
