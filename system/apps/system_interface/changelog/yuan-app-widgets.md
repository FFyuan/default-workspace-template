App widgets: an app can declare a `[widget]` page that the desktop keeps in a corner, above every window.

- Each enabled widget is drawn top right by default as a dark panel with no title bar, at the size its page reports. Dragging the panel's thin rim snaps the widget to another corner, double-clicking the rim collapses or expands it, and right-clicking the rim opens a menu that collapses it, opens the app, or hides the widget for everyone on the workspace. Widgets in one corner stack, and a top corner starts below a title bar so a maximized window's controls stay clear.

- Each client's corner and collapsed state are kept on its client record (`POST /api/clients/<id>/widgets/<app>`). Whether a widget shows is one switch for the whole workspace (`widgets.json`, `GET`/`POST /api/widgets`), also offered as Show/Hide widget in an app's shortcut and launcher menus. Both are listed in the inventory and pushed as `client_widgets_changed` and `widgets_updated`.

- Clicking a widget raises any open window of its app, whatever page that window is on, and opens one only when the app has none.

- On a phone, widgets are drawn collapsed in a strip above the bar.

- An enabled widget keeps its app running, as an open window does, even when the app declares `stop_when_no_windows`.
