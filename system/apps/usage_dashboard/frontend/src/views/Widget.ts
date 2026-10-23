/**
 * The Usage widget's view (app-widgets plan section 7), drawn on the shell's light widget panel in the manner of a
 * system monitor: the whole widget is one link to the Usage page, opened in a window of its own
 * (``target="_blank"``, which the shell's link rule turns into raising the Usage window). What it shows is the
 * version the workspace picked (``widgetRings.ts``, ``widgetBars.ts``). Whatever the version, while the collector
 * indexes its first history the widget says so rather than show partial totals, and while the stream is down it keeps
 * the last figures, dimmed. Hover detail is each row's ``title``: a drawn tooltip would be clipped by the widget's
 * small frame.
 */

import m from "mithril";
import type { WidgetMode } from "@imbue/workspace-ui/src/app_contract";
import type { WidgetModel } from "../models/widget";
import type { WidgetVariant } from "../models/widgetVariant";
import { barsCollapsed, barsExpanded } from "./widgetBars";
import { ringsCollapsed, ringsExpanded } from "./widgetRings";

const VERSIONS: Record<WidgetVariant, Record<WidgetMode, (model: WidgetModel) => m.Children>> = {
  rings: { expanded: ringsExpanded, collapsed: ringsCollapsed },
  bars: { expanded: barsExpanded, collapsed: barsCollapsed },
};

export interface WidgetAttrs {
  readonly model: WidgetModel;
  readonly mode: WidgetMode;
  readonly variant: WidgetVariant;
}

export const Widget: m.Component<WidgetAttrs> = {
  view(vnode) {
    const { model, mode, variant } = vnode.attrs;
    const isCollapsed = mode === "collapsed";
    const content: m.Children = model.isCatchingUp
      ? m("span", { class: "text-(--widget-muted)" }, isCollapsed ? "..." : "Indexing usage...")
      : VERSIONS[variant][mode](model);
    return m(
      "a",
      {
        id: "usage-widget",
        href: "/",
        target: "_blank",
        "data-widget-mode": mode,
        "data-widget-variant": variant,
        "data-live": model.isLive ? "true" : "false",
        class:
          "usage-widget group inline-flex flex-col type-helper text-(--widget-text) no-underline " +
          (isCollapsed ? "gap-1 p-1 " : "w-56 gap-2 p-1.5 ") +
          (model.isLive ? "" : "opacity-60"),
      },
      [
        content,
        model.isLive || isCollapsed
          ? null
          : m("span", { "data-reconnecting": "", class: "flex items-center gap-1 text-(--widget-faint)" }, [
              m("span", { class: "inline-block size-1.5 rounded-full bg-(--widget-faint)" }),
              "Reconnecting",
            ]),
      ],
    );
  },
};
