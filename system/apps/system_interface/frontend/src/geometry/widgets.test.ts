import { describe, expect, it } from "vitest";
import { themeMetricsRecord } from "../testing/records";
import { clampedWidgetSize, cornerAt, widgetRects } from "./widgets";

const METRICS = themeMetricsRecord();
const BACKDROP = { width: 1200, height: 800 };

describe("widget geometry", () => {
  it("clamps a reported size to the theme's minimum and maximum", () => {
    expect(clampedWidgetSize({ width: 180, height: 64 }, METRICS)).toEqual({ width: 180, height: 64 });
    expect(clampedWidgetSize({ width: 2000, height: 2000 }, METRICS)).toEqual({ width: 320, height: 240 });
    expect(clampedWidgetSize({ width: 0, height: 5 }, METRICS)).toEqual({ width: 24, height: 24 });
  });

  it("stacks each corner's widgets away from it, grip above the page, inset and gapped, a top one below a title bar", () => {
    const rects = widgetRects(
      [
        { app: "gauge", corner: "top-right", size: { width: 180, height: 64 } },
        { app: "meter", corner: "top-right", size: { width: 100, height: 40 } },
        { app: "clock", corner: "bottom-left", size: { width: 120, height: 30 } },
        { app: "dial", corner: "bottom-left", size: { width: 60, height: 10 } },
      ],
      BACKDROP,
      METRICS,
    );

    expect(rects.get("gauge")).toEqual({ x: 1200 - 16 - 180, y: 36 + 16, width: 180, height: 76 });
    expect(rects.get("meter")).toEqual({ x: 1200 - 16 - 100, y: 36 + 16 + 76 + 8, width: 100, height: 52 });
    expect(rects.get("clock")).toEqual({ x: 16, y: 800 - 16 - 42, width: 120, height: 42 });
    // Below the minimum, a page's report is raised to it.
    expect(rects.get("dial")).toEqual({ x: 16, y: 800 - 16 - 42 - 8 - 36, width: 60, height: 36 });
  });

  it("snaps a drop to the corner of the quadrant it lands in", () => {
    expect(cornerAt({ x: 10, y: 10 }, BACKDROP)).toBe("top-left");
    expect(cornerAt({ x: 1100, y: 10 }, BACKDROP)).toBe("top-right");
    expect(cornerAt({ x: 10, y: 700 }, BACKDROP)).toBe("bottom-left");
    expect(cornerAt({ x: 600, y: 400 }, BACKDROP)).toBe("bottom-right");
  });
});
