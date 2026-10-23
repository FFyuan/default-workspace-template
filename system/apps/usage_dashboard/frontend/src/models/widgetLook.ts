/**
 * How the workspace's Usage widget looks (app-widgets plan section 7.8): its style, its size, how much it shows, where
 * in the taskbar it goes (the bar's row, called the toolbar, or the tray), and its design in each.
 * A choice the Usage app keeps in its own settings, not a flag. The Usage page picks it; the widget reads it with its
 * figures, and hears at once of a pick made in the same browser through a broadcast channel. ``?variant=``,
 * ``?size=``, ``?detail=``, ``?tray=`` and ``?toolbar=`` on the widget's URL override it for that page alone, so a
 * look can be tried without changing anyone's widget. Picking where in the taskbar, or a design for there, also asks
 * the shell to put this client's widget there.
 */

import { fetchSettings, saveSettings } from "./api";
import type { UsageSettings } from "./api";

export const WIDGET_VARIANTS = ["rings", "bars"] as const;
export type WidgetVariant = (typeof WIDGET_VARIANTS)[number];

export const WIDGET_SIZES = ["small", "medium", "large"] as const;
export type WidgetSize = (typeof WIDGET_SIZES)[number];

/** Less: the 5-hour limit alone and no spend. Standard: both limits and the spend. More: also each limit's figure and
 *  reset time in view. */
export const WIDGET_DETAILS = ["less", "standard", "more"] as const;
export type WidgetDetail = (typeof WIDGET_DETAILS)[number];

/** How the widget is drawn in the taskbar's tray: a ring pair with the name over the 5-hour figure; the ring pair
 *  alone; the name over two bars; the name and the 5-hour figure as text; the 5-hour figure over the weekly one. */
export const WIDGET_TRAYS = ["rings", "ring", "bars", "numbers", "stacked"] as const;
export type WidgetTray = (typeof WIDGET_TRAYS)[number];

/** Where in the taskbar the widget goes: the bar's row, among the windows' entries, or the tray at its right end. */
export const WIDGET_TASKBAR_SPOTS = ["toolbar", "tray"] as const;
export type WidgetTaskbarSpot = (typeof WIDGET_TASKBAR_SPOTS)[number];

/** How the widget is drawn in the bar's row: a chip like a window's entry; upright meters; one line of text; the
 *  name and figure over thin lines. */
export const WIDGET_TOOLBARS = ["chip", "meters", "inline", "line"] as const;
export type WidgetToolbar = (typeof WIDGET_TOOLBARS)[number];

export interface WidgetLook {
  readonly variant: WidgetVariant;
  readonly size: WidgetSize;
  readonly detail: WidgetDetail;
  readonly tray: WidgetTray;
  readonly taskbar: WidgetTaskbarSpot;
  readonly toolbar: WidgetToolbar;
}

export const DEFAULT_WIDGET_LOOK: WidgetLook = {
  variant: "rings",
  size: "medium",
  detail: "standard",
  tray: "rings",
  taskbar: "tray",
  toolbar: "chip",
};

/** What each choice is called where it is picked. */
export const WIDGET_VARIANT_LABELS: Record<WidgetVariant, string> = { rings: "Rings", bars: "Bars" };
export const WIDGET_SIZE_LABELS: Record<WidgetSize, string> = { small: "Small", medium: "Medium", large: "Large" };
export const WIDGET_DETAIL_LABELS: Record<WidgetDetail, string> = { less: "Less", standard: "Standard", more: "More" };
export const WIDGET_TRAY_LABELS: Record<WidgetTray, string> = {
  rings: "Rings",
  ring: "Ring only",
  bars: "Bars",
  numbers: "Numbers",
  stacked: "Stacked",
};
export const WIDGET_TASKBAR_SPOT_LABELS: Record<WidgetTaskbarSpot, string> = { toolbar: "Toolbar", tray: "Tray" };
export const WIDGET_TOOLBAR_LABELS: Record<WidgetToolbar, string> = {
  chip: "Chip",
  meters: "Meters",
  inline: "Inline",
  line: "Line",
};

/** The channel a pick is announced on, to every page of this app in the same browser. */
export const WIDGET_LOOK_CHANNEL = "usage-widget-look";

function oneOf<T extends string>(choices: readonly T[], value: unknown): T | null {
  return choices.find((choice) => choice === value) ?? null;
}

/** ``value`` as a whole look, or null unless every part of it is a known choice. */
export function asWidgetLook(value: unknown): WidgetLook | null {
  if (value === null || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const variant = oneOf(WIDGET_VARIANTS, record.variant);
  const size = oneOf(WIDGET_SIZES, record.size);
  const detail = oneOf(WIDGET_DETAILS, record.detail);
  const tray = oneOf(WIDGET_TRAYS, record.tray);
  const taskbar = oneOf(WIDGET_TASKBAR_SPOTS, record.taskbar);
  const toolbar = oneOf(WIDGET_TOOLBARS, record.toolbar);
  return variant === null || size === null || detail === null || tray === null || taskbar === null || toolbar === null
    ? null
    : { variant, size, detail, tray, taskbar, toolbar };
}

/** The settings as a look: a part the settings do not name, or name as an unknown choice, takes its default. */
export function lookOfSettings(settings: UsageSettings): WidgetLook {
  return {
    variant: oneOf(WIDGET_VARIANTS, settings.widget_variant) ?? DEFAULT_WIDGET_LOOK.variant,
    size: oneOf(WIDGET_SIZES, settings.widget_size) ?? DEFAULT_WIDGET_LOOK.size,
    detail: oneOf(WIDGET_DETAILS, settings.widget_detail) ?? DEFAULT_WIDGET_LOOK.detail,
    tray: oneOf(WIDGET_TRAYS, settings.widget_tray) ?? DEFAULT_WIDGET_LOOK.tray,
    taskbar: oneOf(WIDGET_TASKBAR_SPOTS, settings.widget_taskbar) ?? DEFAULT_WIDGET_LOOK.taskbar,
    toolbar: oneOf(WIDGET_TOOLBARS, settings.widget_toolbar) ?? DEFAULT_WIDGET_LOOK.toolbar,
  };
}

function settingsOfLook(look: WidgetLook): UsageSettings {
  return {
    widget_variant: look.variant,
    widget_size: look.size,
    widget_detail: look.detail,
    widget_tray: look.tray,
    widget_taskbar: look.taskbar,
    widget_toolbar: look.toolbar,
  };
}

/** The parts of the look a widget URL's query names, each only when it is a known choice. */
export function lookOverrides(search: string): Partial<WidgetLook> {
  const query = new URLSearchParams(search);
  const overrides: {
    variant?: WidgetVariant;
    size?: WidgetSize;
    detail?: WidgetDetail;
    tray?: WidgetTray;
    toolbar?: WidgetToolbar;
  } = {};
  const variant = oneOf(WIDGET_VARIANTS, query.get("variant"));
  const size = oneOf(WIDGET_SIZES, query.get("size"));
  const detail = oneOf(WIDGET_DETAILS, query.get("detail"));
  if (variant !== null) overrides.variant = variant;
  if (size !== null) overrides.size = size;
  if (detail !== null) overrides.detail = detail;
  const tray = oneOf(WIDGET_TRAYS, query.get("tray"));
  if (tray !== null) overrides.tray = tray;
  const toolbar = oneOf(WIDGET_TOOLBARS, query.get("toolbar"));
  if (toolbar !== null) overrides.toolbar = toolbar;
  return overrides;
}

/** The workspace's look as stored, or null when the settings cannot be read, so a reader keeps what it had rather
 *  than flip to the default on a failed read. */
export async function readWidgetLook(): Promise<WidgetLook | null> {
  try {
    return lookOfSettings(await fetchSettings());
  } catch {
    return null;
  }
}

export interface ChannelLike {
  postMessage(message: unknown): void;
  onmessage: ((event: MessageEvent) => void) | null;
  close(): void;
}

export interface WidgetLookPickerDeps {
  redraw: () => void;
  openChannel: () => ChannelLike;
  /** Ask the shell to put this client's Usage widget at ``spot`` in the taskbar. */
  placeInTaskbar: (spot: WidgetTaskbarSpot) => void;
}

/** The Usage page's picker: the stored look, and a change to one part of it saved and announced to the widget. */
export class WidgetLookPicker {
  look: WidgetLook | null = null;
  errorMessage: string | null = null;

  constructor(private readonly deps: WidgetLookPickerDeps) {}

  async load(): Promise<void> {
    this.look = (await readWidgetLook()) ?? DEFAULT_WIDGET_LOOK;
    this.deps.redraw();
  }

  async select(change: Partial<WidgetLook>): Promise<void> {
    const previous = this.look ?? DEFAULT_WIDGET_LOOK;
    const next = { ...previous, ...change };
    this.look = next;
    this.errorMessage = null;
    this.deps.redraw();
    try {
      await saveSettings(settingsOfLook(next));
    } catch (error) {
      this.look = previous;
      this.errorMessage = `Could not change the widget: ${error instanceof Error ? error.message : String(error)}`;
      this.deps.redraw();
      return;
    }
    const channel = this.deps.openChannel();
    channel.postMessage(next);
    channel.close();
    // A taskbar design is seen only in the taskbar, so picking where there, or a design for there, puts this client's
    // widget there.
    if (change.taskbar !== undefined || change.tray !== undefined || change.toolbar !== undefined) {
      this.deps.placeInTaskbar(next.taskbar);
    }
  }
}
