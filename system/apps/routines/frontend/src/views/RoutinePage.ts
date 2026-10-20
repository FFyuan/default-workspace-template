/** A routine: its definition in plain words, the controls, and its run history. */

import m from "mithril";

import { Button, buttonClass } from "@imbue/workspace-ui/src/components/Button";

import type { Outcome, RoutineDetail, RunRecord } from "../models/api";
import { chatUrlOf } from "../models/chatLink";
import { runPathOf } from "../models/routing";
import { healthPill } from "./healthPill";

export interface RoutinePageAttrs {
  detail: RoutineDetail;
  isBusy: boolean;
  onRunNow: () => void;
  onToggleEnabled: () => void;
  onChangeSchedule: () => void;
  onFix: () => void;
  onRemove: () => void;
}

const OUTCOME_CLASS: Record<Outcome, string> = {
  SUCCEEDED: "text-success",
  FAILED: "text-danger",
  TIMED_OUT: "text-danger",
  INTERRUPTED: "text-warning",
};

function runRow(run: RunRecord): m.Vnode {
  const outcomeClass = run.outcome === null ? "text-accent" : OUTCOME_CLASS[run.outcome];
  return m("tr", { class: "border-t border-subtle align-top", "data-run": run.run_id }, [
    m(
      "td",
      { class: "py-1.5 pr-3 whitespace-nowrap" },
      m("a", { href: runPathOf(run.routine_id, run.run_id), class: "text-primary hover:underline" }, run.when_text),
    ),
    m(
      "td",
      { class: "py-1.5 pr-3 whitespace-nowrap text-secondary" },
      run.trigger === "MANUAL" ? "manual" : "automatic",
    ),
    m("td", { class: `py-1.5 pr-3 font-semibold whitespace-nowrap ${outcomeClass}` }, run.outcome_text),
    m("td", { class: "py-1.5 pr-3 whitespace-nowrap text-secondary" }, run.duration_text),
    m("td", { class: "py-1.5 pr-3 text-secondary" }, [
      run.summary,
      run.warnings.includes("RESTARTED_PREVIOUS_RUN")
        ? m("span", { class: "ml-2 text-warning" }, "The previous run was still going and was cut off.")
        : null,
      run.chat_id === null
        ? null
        : m(
            "span",
            { class: "ml-2" },
            m("a", { href: chatUrlOf(run.chat_id), class: "text-accent hover:underline" }, "Open chat"),
          ),
    ]),
  ]);
}

export const RoutinePage: m.Component<RoutinePageAttrs> = {
  view({ attrs: { detail, isBusy, onRunNow, onToggleEnabled, onChangeSchedule, onFix, onRemove } }) {
    const { row, definition } = detail;
    const chatId = row.chat_id;
    const isBroken = definition === null;
    const needsFixing =
      row.health === "FAILING" || row.health === "OVERDUE" || row.health === "BROKEN" || row.health === "NEEDS_USER";
    return m("div", { class: "mx-auto flex max-w-[1040px] flex-col gap-5 px-4 py-6 sm:px-7" }, [
      m(
        "nav",
        { class: "type-helper" },
        m("a", { href: "/", class: "text-secondary hover:underline" }, "All routines"),
      ),
      m("header", { class: "flex flex-col gap-2" }, [
        m("div", { class: "flex flex-wrap items-center gap-3" }, [
          m("h1", { class: "type-heading-lg text-primary" }, row.title),
          healthPill(row),
        ]),
        m("p", { class: "type-body text-secondary" }, row.what),
        row.health_detail === ""
          ? null
          : m("p", { class: "type-helper text-secondary", "data-health-detail": "" }, row.health_detail),
      ]),
      m("dl", { class: "grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 type-helper" }, [
        m("dt", { class: "text-faint" }, "Schedule"),
        m("dd", { class: "text-primary" }, [
          row.schedule_text,
          row.next_run_text === "" ? "" : ` (next: ${row.next_run_text})`,
        ]),
        m("dt", { class: "text-faint" }, "Last run"),
        m("dd", { class: "text-primary" }, row.last_run_text),
        m("dt", { class: "text-faint" }, isBroken ? "Problem" : row.kind === "SKILL" ? "Runs the skill" : "Runs"),
        m(
          "dd",
          { class: "font-mono text-primary" },
          isBroken ? row.error : row.kind === "SKILL" ? `/${row.skill}` : row.command.join(" "),
        ),
        row.app === null ? null : m("dt", { class: "text-faint" }, "App"),
        row.app === null ? null : m("dd", { class: "text-primary" }, row.app),
        m("dt", { class: "text-faint" }, "Definition"),
        m("dd", { class: "font-mono text-primary" }, detail.definition_path),
      ]),
      m("div", { class: "flex flex-wrap gap-2", "data-controls": "" }, [
        needsFixing
          ? m(Button, { variant: "primary", disabled: isBusy, onclick: onFix, "data-fix": "" }, "Fix it")
          : null,
        m(
          Button,
          { disabled: isBusy || isBroken || row.is_running, onclick: onRunNow, "data-run-now": "" },
          row.is_running ? "Running" : "Run now",
        ),
        m(
          Button,
          { disabled: isBusy || isBroken, onclick: onToggleEnabled, "data-toggle": "" },
          row.is_enabled ? "Turn off" : "Turn on",
        ),
        m(
          Button,
          { disabled: isBusy || isBroken, onclick: onChangeSchedule, "data-change-schedule": "" },
          "Change schedule",
        ),
        chatId === null
          ? null
          : m("a", { href: chatUrlOf(chatId), class: buttonClass(), "data-open-chat": "" }, "Open its chat"),
        m(Button, { variant: "ghost-destructive", disabled: isBusy, onclick: onRemove, "data-remove": "" }, "Remove"),
      ]),
      m("section", [
        m("h2", { class: "type-section mb-1 text-faint" }, "Runs"),
        detail.runs.length === 0
          ? m("p", { class: "type-helper text-faint", "data-no-runs": "" }, "No runs yet.")
          : m("table", { class: "w-full type-helper" }, [
              m(
                "thead",
                m("tr", { class: "text-left type-tag uppercase tracking-wide text-faint" }, [
                  m("th", { class: "pr-3 font-semibold" }, "When"),
                  m("th", { class: "pr-3 font-semibold" }, "Started"),
                  m("th", { class: "pr-3 font-semibold" }, "Result"),
                  m("th", { class: "pr-3 font-semibold" }, "Took"),
                  m("th", { class: "pr-3 font-semibold" }, "Summary"),
                ]),
              ),
              m("tbody", detail.runs.map(runRow)),
            ]),
      ]),
    ]);
  },
};
