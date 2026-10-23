Usage widget: the Usage app declares a `[widget]` at `/widget`, so the desktop shows subscription limits and this month's API spend on the desktop, styled like a Mac system monitor (iStat Menus): small uppercase headings, tabular figures, and rings over faint tracks, on a white panel.

- Expanded, it has a section per subscription: its ring pair beside a row per limit with the share used (each limit's reset time shows while the pointer is over the widget), then this month's API spend per provider.

- Collapsed, it shows two concentric rings per subscription (the weekly limit outside, the 5-hour limit inside) with the 5-hour percentage in the middle and the provider's name beneath, else the month's spend. A ring is cyan (5-hour) or violet (weekly) while comfortable, orange from 75% and red from 90%.

- It says when usage is still being indexed, dims while reconnecting, hides itself when there is no usage yet, and opens the Usage window when clicked.
