/** Which page a path names: the list at ``/``, a routine at ``/<id>``, a run at ``/<id>/runs/<run id>``. */

export type Page =
  { kind: "list" } | { kind: "routine"; routineId: string } | { kind: "run"; routineId: string; runId: string };

export function pageOf(pathname: string): Page {
  const segments = pathname.split("/").filter((segment) => segment !== "");
  if (segments.length === 0) return { kind: "list" };
  if (segments.length === 1) return { kind: "routine", routineId: decodeURIComponent(segments[0]) };
  if (segments.length === 3 && segments[1] === "runs") {
    return { kind: "run", routineId: decodeURIComponent(segments[0]), runId: decodeURIComponent(segments[2]) };
  }
  return { kind: "list" };
}

export function routinePathOf(routineId: string): string {
  return `/${encodeURIComponent(routineId)}`;
}

export function runPathOf(routineId: string, runId: string): string {
  return `/${encodeURIComponent(routineId)}/runs/${encodeURIComponent(runId)}`;
}

/** The title the window shows for a page, once its data is known. */
export function titleOf(page: Page, routineTitle: string | null): string {
  switch (page.kind) {
    case "list":
      return "Routines";
    case "routine":
      return routineTitle ?? page.routineId;
    case "run":
      return `${routineTitle ?? page.routineId}: a run`;
  }
}
