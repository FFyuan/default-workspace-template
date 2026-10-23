Usage widget: the Usage app declares a `[widget]` at `/widget`, so the desktop shows subscription limits and this month's API spend on the desktop, styled like a Mac system monitor (iStat Menus): small uppercase headings, tabular figures, and rings or bars over faint tracks, on a white panel.

- Expanded, it has a section per subscription: its ring pair beside a row per limit with the share used, then this month's API spend per provider.

- Collapsed, it shows two concentric rings per subscription (the weekly limit outside, the 5-hour limit inside) with the 5-hour percentage in the middle and the provider's name beside it, else the month's spend. A ring is cyan (5-hour) or violet (weekly) while comfortable, orange from 75% and red from 90%.

- How the widget looks is picked for the whole workspace from three menus beside "Widget" in the Usage page's header, and kept in the app's own settings (`data/.apps/usage-dashboard/settings.json`, `GET`/`POST /api/settings`): its style (rings, the default, or bars: a row per subscription with the 5-hour bar above a thinner weekly bar), its size (small, medium or large), and how much it shows (less: the 5-hour limit alone and no spend; standard; more: reset times and the weekly figure in view). A pick reaches the widget in the same browser at once, and elsewhere within a minute; `/widget?variant=bars&size=large&detail=more` shows a look on that page alone.

- The widget draws a tray form (`tray = true` in its manifest), in one of five designs picked from a "Taskbar" menu in the Usage page's header: rings (a small ring pair beside the provider's name over its 5-hour figure), ring only, bars, numbers, or stacked 5-hour and weekly figures. Picking a design also moves your widget into the taskbar's tray; a click there opens it expanded above the bar.

- Nothing in the widget changes under the pointer: hovering a ring, bar, row or name shows a tooltip with its limit, the share used and when it resets.

- It says when usage is still being indexed, dims while reconnecting, hides itself when there is no usage yet, opens the Usage window when clicked, and can be dragged anywhere on the desktop by a press anywhere on it.
