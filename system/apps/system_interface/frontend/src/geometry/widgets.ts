/**
 * Where widgets are drawn (app-widgets plan sections 3.4, 4.2 and 4.4): each in the corner its client chose,
 * stacked away from that corner in the order the shell lists them, inset from the backdrop's edges (which end
 * above the taskbar) and separated by the theme's gap. A top corner's stack starts below a window title bar's
 * height too, so a maximized window's controls stay clear of it. A widget's box is its grip above the size its
 * page last reported, clamped to the theme's widget minimum and maximum. Nothing here reads the DOM.
 */

import type { WidgetCorner } from "../model/records";
import type { PixelPoint, PixelRect, PixelSize } from "./frames";

/** The theme metrics a widget's geometry reads. */
export interface WidgetMetrics {
  readonly titleBarHeight: number;
  readonly widgetInset: number;
  readonly widgetGap: number;
  readonly widgetMaxWidth: number;
  readonly widgetMaxHeight: number;
  readonly widgetMinSize: number;
  readonly widgetGripSize: number;
}

/** One widget to place: its app, its corner, and the size its page reported. */
export interface WidgetToPlace {
  readonly app: string;
  readonly corner: WidgetCorner;
  readonly size: PixelSize;
}

function clampNumber(value: number, low: number, high: number): number {
  return Math.min(Math.max(value, low), Math.max(low, high));
}

/** The size a page's report is drawn at: clamped to the theme's minimum and maximum. */
export function clampedWidgetSize(reported: PixelSize, metrics: WidgetMetrics): PixelSize {
  return {
    width: clampNumber(reported.width, metrics.widgetMinSize, metrics.widgetMaxWidth),
    height: clampNumber(reported.height, metrics.widgetMinSize, metrics.widgetMaxHeight),
  };
}

function isTop(corner: WidgetCorner): boolean {
  return corner === "top-left" || corner === "top-right";
}

function isLeft(corner: WidgetCorner): boolean {
  return corner === "top-left" || corner === "bottom-left";
}

/** Every widget's box, in backdrop pixels: each corner's widgets stacked away from it in the order given. */
export function widgetRects(
  widgets: readonly WidgetToPlace[],
  backdrop: PixelSize,
  metrics: WidgetMetrics,
): Map<string, PixelRect> {
  const rects = new Map<string, PixelRect>();
  const reached: Record<WidgetCorner, number> = { "top-left": 0, "top-right": 0, "bottom-left": 0, "bottom-right": 0 };
  for (const widget of widgets) {
    const content = clampedWidgetSize(widget.size, metrics);
    const width = content.width;
    const height = content.height + metrics.widgetGripSize;
    const x = isLeft(widget.corner) ? metrics.widgetInset : backdrop.width - metrics.widgetInset - width;
    const y = isTop(widget.corner)
      ? metrics.titleBarHeight + metrics.widgetInset + reached[widget.corner]
      : backdrop.height - metrics.widgetInset - reached[widget.corner] - height;
    rects.set(widget.app, { x, y, width, height });
    reached[widget.corner] += height + metrics.widgetGap;
  }
  return rects;
}

/** The corner a widget dropped at ``point`` snaps to: the corner of the backdrop quadrant the point is in. */
export function cornerAt(point: PixelPoint, backdrop: PixelSize): WidgetCorner {
  const isUpper = point.y < backdrop.height / 2;
  const isLeftHalf = point.x < backdrop.width / 2;
  if (isUpper) return isLeftHalf ? "top-left" : "top-right";
  return isLeftHalf ? "bottom-left" : "bottom-right";
}
