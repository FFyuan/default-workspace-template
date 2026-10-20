- `classifyLink` now calls a custom-scheme link (`slack:`, `vscode:`: any scheme a browser does not load itself) external, and `externalLinkMessageType` names its message `open:<scheme>` (`open:slack`). A custom scheme whose message would be another one (`web:`, `url:`) is unroutable. The app contract's new `isCustomSchemeUrl` is held to the Imbue Studio desktop app's rule by the shared link vectors.

- A framed page's click on a custom-scheme link now goes to the shell (`shell:open-link`) like a `mailto:` link, instead of being left to the browser.

- `announceReadyToEmbedder` takes `opensCustomSchemeLinks` and sends it with `minds:workspace-ready`.
