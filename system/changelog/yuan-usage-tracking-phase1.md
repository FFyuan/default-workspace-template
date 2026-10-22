Registered the `usage-collector` service (supervisord program, root dependency) and the `workspace-usage` library, and the `imbue-mngr-usage` plugin in `mngr_plugins.toml` and the root dev group. `usage` is now reserved in `forward_port.py`.

The usage collector needs mngr_usage's `model_call` schema and Claude session-log reader, which land in mngr first; the mngr pin has to move to a commit that has them before this ships.
