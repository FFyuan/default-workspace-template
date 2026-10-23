/**
 * Which version of the Usage widget the workspace shows (app-widgets plan section 7.8): a choice the Usage app keeps
 * in its own settings, not a flag. The Usage page picks it; the widget reads it with its figures, and hears at once of
 * a pick made in the same browser through a broadcast channel. A ``?variant=`` on the widget's URL overrides it for
 * that page alone, so a version can be looked at without changing anyone's widget.
 */

import { fetchSettings, saveSettings } from "./api";

export const WIDGET_VARIANTS = ["rings", "bars"] as const;
export type WidgetVariant = (typeof WIDGET_VARIANTS)[number];

export const DEFAULT_WIDGET_VARIANT: WidgetVariant = "rings";

/** What each version is called where it is picked. */
export const WIDGET_VARIANT_LABELS: Record<WidgetVariant, string> = { rings: "Rings", bars: "Bars" };

/** The channel a pick is announced on, to every page of this app in the same browser. */
export const WIDGET_VARIANT_CHANNEL = "usage-widget-variant";

/** ``value`` as a version, or null for anything else. */
export function asWidgetVariant(value: unknown): WidgetVariant | null {
  return WIDGET_VARIANTS.find((variant) => variant === value) ?? null;
}

/** The version a widget URL's query asks for, or null when it names none or an unknown one. */
export function variantFromQuery(search: string): WidgetVariant | null {
  return asWidgetVariant(new URLSearchParams(search).get("variant"));
}

/** The workspace's version as stored, or null when the settings cannot be read or name an unknown version, so a
 *  reader keeps what it had rather than flip to the default on a failed read. */
export async function readWidgetVariant(): Promise<WidgetVariant | null> {
  try {
    return asWidgetVariant((await fetchSettings()).widget_variant);
  } catch {
    return null;
  }
}

export interface ChannelLike {
  postMessage(message: unknown): void;
  onmessage: ((event: MessageEvent) => void) | null;
  close(): void;
}

export interface WidgetVariantPickerDeps {
  redraw: () => void;
  openChannel: () => ChannelLike;
}

/** The Usage page's picker: the stored version, and a pick saved and announced to the widget. */
export class WidgetVariantPicker {
  variant: WidgetVariant | null = null;
  errorMessage: string | null = null;

  constructor(private readonly deps: WidgetVariantPickerDeps) {}

  async load(): Promise<void> {
    this.variant = (await readWidgetVariant()) ?? DEFAULT_WIDGET_VARIANT;
    this.deps.redraw();
  }

  async select(variant: WidgetVariant): Promise<void> {
    const previous = this.variant;
    this.variant = variant;
    this.errorMessage = null;
    this.deps.redraw();
    try {
      await saveSettings({ widget_variant: variant });
    } catch (error) {
      this.variant = previous;
      this.errorMessage = `Could not change the widget: ${error instanceof Error ? error.message : String(error)}`;
      this.deps.redraw();
      return;
    }
    const channel = this.deps.openChannel();
    channel.postMessage({ variant });
    channel.close();
  }
}
