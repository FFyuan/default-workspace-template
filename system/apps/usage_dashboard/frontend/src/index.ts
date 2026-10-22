/**
 * The Usage page's root. Framed by the workspace shell, it reports where it is (``shell:location``) and installs
 * the element context menu, then hands the page to the dashboard model, which reads the collector through this
 * app's server and keeps the page current from its stream.
 */

import m from "mithril";
import "./style.css";

import { connectToShell } from "@imbue/workspace-ui/src/app_contract";
import type { ShellHandshake } from "@imbue/workspace-ui/src/app_contract";
import { createContextMenuOpener } from "@imbue/workspace-ui/src/components/contextMenuOpener";
import { installElementContextMenu } from "@imbue/workspace-ui/src/context_menu";

import { DashboardModel } from "./models/dashboard";
import { App } from "./views/App";

function bootstrap(): void {
  const root = document.getElementById("app");
  if (root === null) return;
  let handshake: ShellHandshake | null = null;
  const connection = connectToShell({ onHandshake: (received) => (handshake = received) });
  window.addEventListener("focus", () => connection.focused());
  installElementContextMenu({ connection, handshake: () => handshake, open: createContextMenuOpener().open });
  connection.location("/", "Usage");

  const now = (): Date => new Date();
  const model = new DashboardModel({
    now,
    redraw: () => m.redraw(),
    openStream: (url) => new EventSource(url),
  });
  m.mount(root, { view: () => m(App, { model, now }) });
  model.start();
}

window.addEventListener("load", bootstrap);
