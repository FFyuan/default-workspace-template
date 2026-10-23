/**
 * How the workspace's Usage widget looks (app-widgets plan section 7.8): its style, its size, and how much it shows.
 * A choice the Usage app keeps in its own settings, not a flag. The Usage page picks it; the widget reads it with its
 * figures, and hears at once of a pick made in the same browser through a broadcast channel. ``?variant=``,
 * ``?size=`` and ``?detail=`` on the widget's URL override it for that page alone, so a look can be tried without
 * changing anyone's widget.
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

export interface WidgetLook {
  readonly variant: WidgetVariant;
  readonly size: WidgetSize;
  readonly detail: WidgetDetail;
}

export const DEFAULT_WIDGET_LOOK: WidgetLook = { variant: "rings", size: "medium", detail: "standard" };

/** What each choice is called where it is picked. */
export const WIDGET_VARIANT_LABELS: Record<WidgetVariant, string> = { rings: "Rings", bars: "Bars" };
export const WIDGET_SIZE_LABELS: Record<WidgetSize, string> = { small: "Small", medium: "Medium", large: "Large" };
export const WIDGET_DETAIL_LABELS: Record<WidgetDetail, string> = { less: "Less", standard: "Standard", more: "More" };

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
  return variant === null || size === null || detail === null ? null : { variant, size, detail };
}

/** The settings as a look: a part the settings do not name, or name as an unknown choice, takes its default. */
export function lookOfSettings(settings: UsageSettings): WidgetLook {
  return {
    variant: oneOf(WIDGET_VARIANTS, settings.widget_variant) ?? DEFAULT_WIDGET_LOOK.variant,
    size: oneOf(WIDGET_SIZES, settings.widget_size) ?? DEFAULT_WIDGET_LOOK.size,
    detail: oneOf(WIDGET_DETAILS, settings.widget_detail) ?? DEFAULT_WIDGET_LOOK.detail,
  };
}

function settingsOfLook(look: WidgetLook): UsageSettings {
  return { widget_variant: look.variant, widget_size: look.size, widget_detail: look.detail };
}

/** The parts of the look a widget URL's query names, each only when it is a known choice. */
export function lookOverrides(search: string): Partial<WidgetLook> {
  const query = new URLSearchParams(search);
  const overrides: { variant?: WidgetVariant; size?: WidgetSize; detail?: WidgetDetail } = {};
  const variant = oneOf(WIDGET_VARIANTS, query.get("variant"));
  const size = oneOf(WIDGET_SIZES, query.get("size"));
  const detail = oneOf(WIDGET_DETAILS, query.get("detail"));
  if (variant !== null) overrides.variant = variant;
  if (size !== null) overrides.size = size;
  if (detail !== null) overrides.detail = detail;
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
  }
}
