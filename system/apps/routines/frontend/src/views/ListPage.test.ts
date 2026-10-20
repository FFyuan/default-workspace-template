// @vitest-environment jsdom
import "@imbue/workspace-ui/src/testing/dom";
import { mountView, unmountViews } from "@imbue/workspace-ui/src/testing/mount";
import m from "mithril";
import { afterEach, describe, expect, it } from "vitest";

import type { RoutineListing, RoutineRow } from "../models/api";
import { ADD_PREFIX, ListPage, groupRows } from "./ListPage";

afterEach(() => unmountViews());

function row(patch: Partial<RoutineRow>): RoutineRow {
  return {
    routine_id: "news-sync",
    title: "News sync",
    what: "Pulls the headlines.",
    health: "WORKING",
    health_text: "Working",
    health_detail: "",
    is_running: false,
    is_enabled: true,
    kind: "COMMAND",
    app: null,
    schedule_text: "Every hour",
    next_due_at: null,
    next_run_text: "today 8:00 am",
    last_run: null,
    last_run_text: "Worked 10 minutes ago, automatic",
    error: null,
    skill: null,
    command: ["python3", "sync.py"],
    chat_id: null,
    ...patch,
  };
}

function listing(rows: RoutineRow[], appNames: Record<string, string> = {}): RoutineListing {
  return {
    routines: rows,
    summary: {
      total: rows.length,
      needs_attention: rows.filter((r) => r.health === "FAILING").length,
      running: 0,
      next_run_text: "today 8:00 am",
    },
    app_names: appNames,
    generated_at: "2026-10-20T15:00:00+00:00",
  };
}

describe("groupRows", () => {
  it("groups by the app's display name, with the workspace's own last", () => {
    const rows = [
      row({ routine_id: "a", app: null }),
      row({ routine_id: "b", app: "news" }),
      row({ routine_id: "c", app: "other" }),
    ];
    const groups = groupRows(rows, { news: "Daily News" });
    expect(groups.map(([heading, members]) => [heading, members.map((r) => r.routine_id)])).toEqual([
      ["Daily News", ["b"]],
      ["other", ["c"]],
      ["Workspace", ["a"]],
    ]);
  });
});

describe("ListPage", () => {
  it("draws one linked row per routine with its health, schedule and last run", () => {
    const rows = [
      row({
        routine_id: "digest",
        title: "Inbox digest",
        health: "FAILING",
        health_text: "Failing",
        health_detail: "Last worked 2 hours ago; 3 failed tries in a row.",
      }),
      row({}),
    ];
    const root = mountView(() =>
      m(ListPage, { listing: listing(rows), onStartWithText: () => undefined }),
    );

    const links = [...root.querySelectorAll<HTMLAnchorElement>("a.routine-row")];
    expect(links.map((link) => link.getAttribute("href"))).toEqual(["/digest", "/news-sync"]);
    expect(links[0].querySelector("[data-health]")?.getAttribute("data-health")).toBe("FAILING");
    expect(links[0].textContent).toContain("Last worked 2 hours ago; 3 failed tries in a row.");
    expect(links[1].textContent).toContain("Every hour");
    expect(links[1].textContent).toContain("Worked 10 minutes ago, automatic");
    expect(root.querySelector("[data-summary]")?.textContent).toContain("1");
  });

  it("shows a running routine as running", () => {
    const root = mountView(() =>
      m(ListPage, { listing: listing([row({ is_running: true })]), onStartWithText: () => undefined }),
    );
    expect(root.querySelector("[data-health]")?.getAttribute("data-health")).toBe("RUNNING");
  });

  it("groups the rows under the apps' display names from the listing", () => {
    const rows = [row({ routine_id: "a", app: null }), row({ routine_id: "b", app: "news" })];
    const root = mountView(() =>
      m(ListPage, { listing: listing(rows, { news: "Daily News" }), onStartWithText: () => undefined }),
    );
    expect([...root.querySelectorAll("[data-group]")].map((group) => group.getAttribute("data-group"))).toEqual([
      "Daily News",
      "Workspace",
    ]);
  });

  it("hands the add field's text to the shell with the add prefix, keeping it across a redraw", () => {
    const started: string[] = [];
    const root = mountView(() =>
      m(ListPage, { listing: listing([]), onStartWithText: (text) => started.push(text) }),
    );
    const input = root.querySelector<HTMLInputElement>("[data-add-input]")!;
    input.value = "every weekday at 8, summarize my inbox";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    // A poll redraws the page between the typing and the submit.
    m.redraw.sync();
    root
      .querySelector<HTMLFormElement>("[data-add-form]")!
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    expect(started).toEqual([`${ADD_PREFIX}every weekday at 8, summarize my inbox`]);
    m.redraw.sync();
    expect(root.querySelector<HTMLInputElement>("[data-add-input]")!.value).toBe("");
    expect(root.querySelector("[data-empty]")).not.toBeNull();
  });
});
