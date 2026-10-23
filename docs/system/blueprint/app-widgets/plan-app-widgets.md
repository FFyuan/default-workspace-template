# App widgets and the usage widget

This is the spec for app widgets: a small, always-on-top view an app declares in its manifest and the shell draws in a corner of the desktop, above every window, for every client of the workspace.
It ships with one widget, the Usage app's, which shows at a glance how much of each subscription limit is used and what pay-as-you-go spend has reached this month, the way a system-stats menu shows CPU and memory.
It is written for the people and agents implementing it, and it is the reference the implementation is judged against.
It builds on the desktop interface V1 ([plan-desktop-interface.md](../desktop-interface/plan-desktop-interface.md), [concepts.md](../desktop-interface/concepts.md), [contracts.md](../desktop-interface/contracts.md)), borrows its floating layer and per-client presentation from the pinned taskbar entries ([plan-pinned-taskbar-entries.md](../pinned-taskbar-entries/plan-pinned-taskbar-entries.md)), and amends those documents and the stop-when-no-windows spec where section 9 says.

## 1. Purpose and principles

A window is the wrong shape for a number you want to see without asking for it: it has a title bar, takes a place in the stack, and is buried as soon as you work in another window.
A widget is a page of an app that the shell keeps visible in a corner, small, translucent until hovered, and collapsible to a one-line pill.
It shows; it is not worked in. A click on it opens the app's window.

The five principles of the workspace app model hold: one owner per fact; the shell is generic and names no app; truth is shared while arrangement is scoped; minimal shell state; no two-phase commits.
Applied here:

- **The shell names no app.** An app opts in with a `[widget]` table; the shell draws whatever page it names and knows nothing of usage. The shell's ratchets (`test_project_ratchets.py`) hold unchanged.
- **The app owns the content, the shell owns the frame.** The page draws both its expanded and collapsed forms and says how big it is; the shell decides where the frame is, whether it is collapsed, how translucent it is, and how it moves.
- **Whether a widget is on is shared truth; where it sits is the client's arrangement.** One workspace-wide switch per widget, like the avatar selection; corner and collapsed state per client, like a pinned entry's presentation.
- **A widget that is on keeps its app up**, as a window does (section 3.5).

## 2. Glossary

| Term | Meaning |
|---|---|
| Widget | An app's manifest declaration of a page the shell shows in a corner, and the frame the shell draws it in |
| Widget page | The page at the widget's path under the app's origin; an ordinary page of the app that speaks the app contract |
| Enabled | Whether the workspace shows a widget at all; shared, one value per widget |
| Corner | Where one client draws a widget: `top-left`, `top-right`, `bottom-left`, `bottom-right`; per client |
| Mode | How one client draws a widget: `expanded` or `collapsed`; per client |
| Rest opacity | The translucency of a widget the pointer is not over |

## 3. The model

### 3.1 The declaration

A widget is declared in an app's manifest as a `[widget]` table and copied onto the app's registry row by `forward_port.py`, the way `pin` is.
The set of apps with a widget is exactly the registered, non-internal apps whose row carries one; nothing stores the set.

| Field | Type | Required | Default | Rule |
|---|---|---|---|---|
| `path` | string | yes | | The widget page: a path under the app's origin obeying the launch-path rule (one leading slash, no query string, path characters only) |
| `default_enabled` | bool | no | `true` | Whether the widget shows in a workspace that has made no choice about it |

### 3.2 Enabled, shared

Whether each widget shows is one shared value for the workspace, held in a small state file (section 5.1) and broadcast when it changes, so every window of every client changes together.
A widget with no stored value takes its manifest's `default_enabled`.
A stored value naming an app that no longer declares a widget is kept (so a widget withdrawn and restored keeps the user's choice) and ignored.

### 3.3 Presentation, per client

How one client shows a widget is two values on the client record, keyed by app: its corner and its mode.
They are global to the client rather than per desktop, for the reason the pinned entries give: an always-on-top thing that jumped when the desktop switched would read as broken.
A client with no presentation for an app draws it `top-right`, `expanded`.

`top-right` rather than `bottom-right` because the chat's floating avatar defaults to the bottom-right corner, and the taskbar's tray sits under it.

### 3.4 Stacking

Widgets sharing a corner stack away from it (downward from a top corner, upward from a bottom one) in registry `priority` order, then by app name, separated by the theme's widget gap.
The first is nearest the corner. Nothing overlaps; a stack taller than the backdrop is clipped, which with the size cap of section 4.2 needs five widgets in one corner.

### 3.5 Lifecycle

A widget that is enabled keeps its app's program running: the no-window rule of the stop-when-no-windows spec (section 6.1) counts it as it counts a window, and clears the app's idle mark.
This follows that spec's own principle (section 6.2: "the rule is the user's arrangement, not the browser's"): the widget counts because it is on, not because some browser is drawing it, so a workspace no one is looking at keeps an enabled widget's app up exactly as it keeps a minimized window's.
A disabled widget counts for nothing.
Quit (spec section 7) still stops the program at once; an enabled widget's frame then wakes it on its next request, through the port parker, as any request does. The widget's menu says so: Quit is not offered there, and "Hide widget" is.

### 3.6 Who sees it

Every client of the shell draws every enabled widget.
No per-visitor gating is needed: the share gateway admits a visitor holding only a per-app grant to that app's origin and not to the shell (`shell/share_grants.py`), so every client the shell has holds the workspace grant, which reaches every app's origin.

### 3.7 Ownership

| Fact or verb | Owner |
|---|---|
| Whether an app has a widget; its path and default | The app's manifest, through the registry |
| Whether a widget is enabled | Shell, shared |
| A widget's corner and mode | Shell, per client, on the client record |
| The widget's size | The widget page, reported per frame; never stored |
| What the widget shows | The app |
| Where each widget is drawn | Derived in the browser |

### 3.8 Invariants

- Nothing in the shell package names an app, imports mngr, or runs mngr.
- A client draws at most one frame per enabled widget, in exactly one corner.
- No widget frame is larger than the theme's widget maximum, whatever its page reports.
- An enabled widget's app is never stopped by the no-window rule.

## 4. Behaviour

### 4.1 The layer

Widgets are drawn in their own layer, a sibling of the floating entries' layer inside the backdrop's stacking context, at the same sticky level: above every window and live page (a maximized window goes under them), below the launcher overlay, menus, and modals.
The layer is inert; only each widget's own box takes a press.
Each corner's stack is inset from the backdrop's edges by the theme's widget inset, so a bottom corner sits above the taskbar.

### 4.2 The frame

A widget's frame is an iframe of the app's `url` plus the widget's `path`, with the shell's chrome around it: a grip strip along the edge facing away from the corner, shown on hover, and a collapse/expand chevron on it.
The frame is not drawn until its page first reports a size, so a page that is loading or fails to load leaves no empty box in the corner; a page that never reports is logged once and never drawn.
The frame's size is the last size its page reported for the current mode, clamped to the theme's widget maximum (320 by 240) and minimum (24 by 24).
At rest the frame is drawn at the rest opacity; while the pointer is over it, or a menu of it is open, fully opaque.

### 4.3 Collapse and expand

The chevron toggles the client's mode for that widget and writes it to the client record.
The shell tells the page its mode after every handshake and on every change; the page draws the matching form and reports its size again.
The page decides what each form shows; the shell never draws a pill of its own.

### 4.4 Moving between corners

Dragging the grip moves the widget, with the gesture layer's threshold, pointer capture, and click suppression, as a floating entry drags.
During the drag the frame follows the pointer; on release it snaps to the corner of the backdrop quadrant the pointer is in, and the corner is written to the client record once.
A press that never travels the threshold is a click on the grip, which does nothing.

### 4.5 Clicking

A click inside the frame is the page's.
The widget page opens its app by a link to its own origin with `target="_blank"`: under the app contract's link rule (contracts section 7) that is a new-window click on the page's own origin, which sends `shell:open` with `ifPresent: "focus"`, so it raises the app's window at that path on the client's active desktop, opening one only when there is none.

### 4.6 Menus

The grip's context menu (right click, or long press on touch):

1. Collapse or Expand
2. Open <display name>, as the page's own link does
3. divider
4. Hide widget, which disables it for the whole workspace, saying so: "Hide the <display name> widget for everyone on this workspace"

A hidden widget is shown again from its app's shortcut menu and its launcher row's menu, which gain "Show widget" when the app declares a widget that is disabled, and "Hide widget" when it is enabled.

### 4.7 Hidden by its page

A page may say it has nothing to show (the Usage widget before any usage exists).
The shell then draws nothing for it on that client and keeps the frame loaded, so the page can say otherwise; the widget still counts as enabled for the lifecycle rule.

### 4.8 Phone

The phone layout has no floating layer.
In its bar, beside the pill, it draws each enabled widget not hidden by its page, always collapsed, clamped to the phone's widget height.
A tap is the page's, as a click is on the desktop; its link opens the app's window, which the phone shows.
There is no grip, menu, or corner on a phone.

### 4.9 Touch

Touch mode uses long press on the grip for the menu, as elsewhere; the grip and chevron have the theme's touch target size at minimum, and the frame is fully opaque while touched.

## 5. The shell backend

### 5.1 State files

- `widgets.json`, new: `{"version": 1, "apps": {"<app>": {"is_enabled": bool}}}`; absent means every widget takes its manifest default.
- `clients.json` (version 2, unchanged): each client gains `widgets`, a map from app name to `{"corner", "mode"}`; absent means the defaults.

### 5.2 The manifest and the registry

`app_manifest` gains the `[widget]` table of section 3.1, and `RegistryRow` gains `widget`.
`forward_port.py` copies it onto the row as it copies `pin`, refusing a malformed one with the same shape of error.
The inventory's and `apps_updated`'s `app` object carries `widget` (the table, or `null`).

### 5.3 Routes and messages

| Route | Change |
|---|---|
| `GET /api/widgets` | new: `{"widgets": [{"app", "is_enabled"}]}`, one per app declaring a widget, the effective value |
| `POST /api/widgets/<app>` | new: `{"is_enabled"}`; writes `widgets.json`, broadcasts `widgets_updated`, answers as `GET`; `404` for an app declaring no widget |
| `POST /api/clients/<client_id>/widgets/<app>` | new: `{"corner", "mode"}`; answers the client record and announces `client_widgets_changed` to that client's windows |
| `GET /api/inventory` | gains `widgets`, as `GET /api/widgets` answers it |

New socket messages:

| Type | Payload | When |
|---|---|---|
| `widgets_updated` | `{"widgets": [{"app", "is_enabled"}]}` | on connect, and after `widgets.json` is written or the registry's widget declarations change |
| `client_widgets_changed` | `{"client_id", "widgets"}` | to that client's windows, after its widget presentation was written |

### 5.4 The lifecycle rule

`AppLifecycleManager` gains an enabled-widgets reader beside its window counts and granted apps: a running app that declares `stop_when_no_windows`, is not `internal`, and has an enabled widget clears its idle mark, as one with a window does.
The reader reads `widgets.json` and the registry once per sweep pass, and only when the pass finds a running, windowless app that declares the field.

### 5.5 Agent ops

None in this version: no op enables, disables, or moves a widget, and `desktops`/`list` do not list them.
Whether a widget is on is the user's choice and the manifest's default.

## 6. The app contract

The app contract evolves by adding types (contracts section 7); nothing shipped changes meaning.

| Direction | Type | Payload |
|---|---|---|
| shell to page | `shell:handshake` | gains `surface`: `"window"` (the existing case; a handshake without it reads as a window) or `"widget"`; a widget's handshake carries `windowId: null` and the client's active desktop as `desktopId`, sent again when it changes |
| shell to page | `shell:widget-mode` | `{"mode": "expanded" \| "collapsed"}`; to a widget page only, after every handshake and on every change |
| page to shell | `shell:widget-size` | `{"width", "height"}`, CSS pixels of the page's content in its current mode; the shell clamps it (section 4.2) |
| page to shell | `shell:widget-hidden` | `{"isHidden": bool}`; section 4.7 |

From a widget page the shell ignores `shell:location`, `shell:focused`, and `shell:capabilities`, and takes `shell:open`, `shell:open-link`, `shell:message`, `shell:start-with-text`, and `shell:draft-text` as from a window, on the client's active desktop.
`connectToShell` gains `onWidgetMode(mode)` among its handlers and `widgetSize(width, height)` and `widgetHidden(isHidden)` on the connection, plus `surface()`, so one page module serves both a window and a widget.

## 7. The Usage widget

### 7.1 The manifest

```toml
[widget]
path = "/widget"
default_enabled = true
```

### 7.2 The page

`/widget` is a second Vite entry of the Usage app (`frontend/widget.html`, `src/widget.ts`), a small bundle beside the dashboard's, served by the Flask server like the dashboard's page.
It reads what the dashboard reads, through the same server's `/api/usage/*` relay and its stream, and reuses the dashboard's models (`models/api.ts`, `models/providers.ts`, `models/format.ts`) so the two can never disagree: limit levels come from the same `limitLevel()` (75% high, 90% critical) and a window reset since its reading is recognised by the same rule.

### 7.3 Expanded

One row per provider with data, in the dashboard's card order, about 180 pixels wide:

- A subscription provider: its name, a bar for its shortest window (the 5-hour limit) coloured by level, that window's percentage, and its longest window's (weekly) percentage after a dot.
- A pay-as-you-go provider: its name and this month's spend, with `~` when any of it is estimated.
- A provider with no data is not drawn.

Each row's `title` gives the detail a hover asks for (each window's reset time, the reading's "as of" time, the call count), as a native tooltip, since a drawn tooltip would be clipped by the frame.

### 7.4 Collapsed

One pill: the highest percentage among the subscription windows not reset since their reading, coloured by its level, with its provider's initial (`C 61%`); with no subscription windows, this month's total spend (`$165`).

### 7.5 States

| State | Expanded | Collapsed |
|---|---|---|
| A window reset since its reading | `—` and a faint "reset" in place of its percentage | the window is left out of the highest |
| An old reading not yet reset | drawn as usual; the time is in the tooltip | as usual |
| Stream disconnected | every row dimmed, last values kept, a small "Reconnecting" dot | the pill dimmed |
| Collector catching up | one row, "Indexing usage..." | `...` |
| No usage data at all | `shell:widget-hidden {isHidden: true}`, sent again with `false` on the first event | the same |

### 7.6 Opening the dashboard

The whole widget is one link, `<a href="/" target="_blank">`, so a click raises the Usage window (section 4.5).

## 8. Theme tokens and selectors

Tokens, read into the metrics record with the others: `--desk-widget-inset: 16px`, `--desk-widget-gap: 8px`, `--desk-widget-max-width: 320px`, `--desk-widget-max-height: 240px`, `--desk-widget-min-size: 24px`, `--desk-widget-rest-opacity: 0.72`, `--desk-widget-grip-size: 12px` (touch: the touch target), `--desk-phone-widget-height: 32px`.

| Attribute | On |
|---|---|
| `data-widgets` | the widget layer |
| `data-widget="<app>"`, `data-widget-corner="top-left\|top-right\|bottom-left\|bottom-right"`, `data-widget-mode="expanded\|collapsed"` | each widget's frame |
| `data-widget-grip`, `data-widget-control="collapse\|expand"` | the grip and its chevron |
| `data-menu-item="widget-collapse\|widget-expand\|widget-open\|widget-hide\|widget-show"` | the widget rows of the grip, shortcut, and launcher menus |
| `data-phone-widget="<app>"` | each widget in the phone's bar |

## 9. Amendments to other documents

Landed with this plan:

- contracts.md 2, 3, 4, 5, 6, 7, 11, 12, 13: the manifest table, the row field, the files, the routes, the messages, the contract types, the tokens, and the selectors above.
- `docs/system/specs/stop-when-no-windows.md` 6.1 and 6.2: an enabled widget clears the idle mark.

Landed with the implementation:

- plan-pinned-taskbar-entries.md 4.2: the floating layer has a sibling widget layer at the same level.
- plan-phone-interface.md: the bar draws collapsed widgets.
- The `build-app` skill's manifest notes: the `[widget]` table, and that an app declaring one must answer its page cheaply, since it is loaded by every client.
- The Usage app's README: the widget page.

## 10. Testing

Unit tests, beside the code:

- The manifest table and its refusals; the registry copy; the inventory field.
- `widgets.json`: defaults, a stored value, a withdrawn widget's value kept and ignored.
- The lifecycle rule: an enabled widget clears the idle mark; a disabled one does not; an internal app's widget is never drawn.
- The client record's `widgets` and its route.
- Reducers: corner stacks and their order, size clamping, the effective presentation, the hidden-by-page state.
- `app_contract.ts`: the `surface` field, the three new types, and that a widget's `shell:location` is not sent.
- Usage widget models: rows from fixture limits and totals, the collapsed choice, each state of 7.5.

End to end, in `test_e2e.py`, with a stub app declaring a widget whose page reports a size:

- The widget appears top-right; it is not drawn before its page reports; a maximized window goes under it.
- Collapse changes the frame to the collapsed size; the mode survives a reload.
- A drag to the bottom-left snaps there and survives a reload; a second stub widget in that corner stacks.
- A click on its `_blank` link raises the stub app's window, and a second click opens no second window.
- Hide widget removes it from a second client too; Show widget from the shortcut menu brings it back.
- A phone viewport draws it in the bar.
- The stub app, with `stop_when_no_windows`, is not stopped with its widget enabled and no window, and is stopped once it is disabled.

A browser test in the Usage app drives `/widget` against a fixture collector.

## 11. Delivery

This is one pull request on `yuan/app-widgets`, stacked on `yuan/usage-dashboard`, merged after it.
A suggested commit order, each commit leaving the repository green:

1. The manifest table, the registry and inventory fields, `widgets.json`, and its routes.
2. The app contract's types.
3. The widget layer, frame, collapse, corners, stacking, and menus, with the stub-app end-to-end tests.
4. The lifecycle rule.
5. The phone bar.
6. The Usage widget page and its manifest table.
7. The remaining document amendments of section 9 and the changelog entries for `system_interface`, `workspace_ui`, and `usage_dashboard`.

## 12. Deferred

- A native, always-on-top widget outside the workspace (a macOS menubar item or panel from Imbue Studio); this design keeps all usage data inside the workspace, and a native host would load the same widget page.
- Per-user enablement; this version has the shared switch only.
- Agent ops for widgets.
- Free positioning; corners only.
- Alerts (toasts, sounds) at a limit's level.
- A System Monitor widget, which this contract makes a manifest table and a page.
