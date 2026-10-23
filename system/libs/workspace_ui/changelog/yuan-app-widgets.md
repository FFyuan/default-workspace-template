The app contract gains a widget surface: a handshake says whether it frames a window or a widget, and a widget page takes `shell:widget-mode` and sends `shell:widget-size` and `shell:widget-hidden` (`onWidgetMode`, `widgetSize`, `widgetHidden`, `surface()`). A widget sends no location or focus report.

A widget's page gives an element a tooltip with `data-widget-tooltip`: `connectToShell` reports it to the shell as `shell:widget-tooltip`, which shows the workspace's tooltip outside the widget's frame. The shared tooltip gains `showTooltipAtRect` and `hideTooltipAtRect` for such a trigger, whose pointer the document cannot hear.

A press anywhere on a widget's page drags the widget: once it travels a few pixels, `connectToShell` reports it to the shell as `shell:widget-drag` and swallows the click that ends it, with no code in the page. A short press stays the page's click, and a press on a button, a field, or an element marked `data-no-drag` never drags.
