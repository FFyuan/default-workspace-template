Usage widget: the Usage app declares a `[widget]` at `/widget`, so the desktop shows subscription limits and this month's API spend on the desktop, styled like a Mac system monitor (iStat Menus): small uppercase headings, tabular figures, and rings over faint tracks, on a white panel.

- Expanded, it has a section per subscription: its ring pair beside a row per limit with the share used (each limit's reset time shows while the pointer is over the widget), then this month's API spend per provider.

- Collapsed, it shows two concentric rings per subscription (the weekly limit outside, the 5-hour limit inside) with the 5-hour percentage in the middle and the provider's name beside it, else the month's spend; under the pointer the name gives way to when each limit resets. A ring is cyan (5-hour) or violet (weekly) while comfortable, orange from 75% and red from 90%.

- The widget comes in two versions, picked for the whole workspace from a Widget menu in the Usage page's header and kept in the app's own settings (`data/.apps/usage-dashboard/settings.json`, `GET`/`POST /api/settings`): rings (the default) and bars, a row per subscription with the 5-hour bar above a thinner weekly bar and their shares used. The bars version hides which window a bar is and when it resets until the pointer is over the widget, expanded or collapsed. A pick reaches the widget in the same browser at once, and elsewhere within a minute; `/widget?variant=bars` shows a version on that page alone.

- It says when usage is still being indexed, dims while reconnecting, hides itself when there is no usage yet, opens the Usage window when clicked, and can be dragged anywhere on the desktop by a press anywhere on it.
