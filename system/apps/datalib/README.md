# datalib

The Datalib app: datalib's own web UI -- the Manage screen and the Add/Edit
source wizard served by `datalib-http` -- over the store the `datalib` skill
writes, so a source added through the wizard is what the agent searches and a
sync the agent runs is what the UI shows. Supervised as the `datalib` program,
declared in `system/supervisord.conf.d/datalib.conf`, whose program line runs
`launch_datalib_http.py` under a plain `python3`.

datalib is not announced to users yet, so that program has `autostart=false`:
an app is listed only once its program has registered it, and nothing starts
this one until the `datalib` skill does, for a user who asked for datalib by
name. Once started it is registered, and it stays listed from then on.

The app is a manifest, an icon, and that launcher; like the file viewer it is
not a Python package, and it is excluded from the uv workspace in the root
`pyproject.toml`. The launcher uses only the standard library, so the app does
not depend on the root venv being intact.

The server is `datalib-http` from the datalib release pinned in
`.agents/skills/datalib/scripts/install_datalib.sh` (the same pin as the
skill; `test_datalib_pin.py` checks the two agree). That script installs the
release into `~/.local/share/datalib/<version>/` and links it into
`~/.local/bin`. Nothing runs it at boot: the skill runs it the first time it
is used, so a workspace that never uses datalib downloads nothing. The launcher does three things, in order:

1. Reads the API token (see below).
2. Registers the app and the datalib-http port 8731 through
   `system/scripts/forward_port.py`.
3. Replaces itself with `~/.local/bin/datalib-http --no-open
   data/.skills/datalib`, with `DATALIB_BIND=127.0.0.1:8731` and the token in
   `DATALIB_TOKEN`. From then on supervisord supervises datalib-http directly.

If it is started before that script has installed the binary, the launcher
exits without registering anything and supervisord retries it with its
backoff, so the app never appears with nothing behind it.

## The token

`datalib-http` requires its per-process API token on every route: loopback
does not keep a web page out, and `PUT /api/config` runs shell commands. A
browser gets in by loading `/?token=<token>` once, which sets a session cookie
and redirects to `/`.

A window opens at a launch path's `path` with the launch path's `presets` as
the query string. `app.toml` declares one launch path, `ui`, at `/`. The
launcher writes a copy of `app.toml` to `data/.state/datalib-app/` with
`presets = { token = "<token>" }` appended to that launch path, and registers
the copy, so a window opens at `/?token=<token>`. `app.toml` must keep its
`[[launch_paths]]` table last for the append to land in it; the launcher
checks this and refuses to start otherwise.

The token itself is `data/.skills/datalib/system/api-token`: the launcher reads
it at start and hands it to `datalib-http` through `DATALIB_TOKEN`, so it stays
the same across restarts (a browser already holding the cookie stays signed
in) and the skill can read the same file for its bearer token. When the file
is missing or unusable the launcher mints one, and `datalib-http` writes it
there.

## Staying up with no window

`app.toml` sets `stop_when_no_windows = false`: a sync started from the Manage
screen runs inside `datalib-http` and has to finish after the window closes.

## Tests

`uv run pytest system/apps/datalib` from the repo root.
`launch_datalib_http_test.py` pins the token handling and the registered
manifest copy; `test_datalib_app.py` runs the launcher as a process, through
the real `forward_port.py` and around a fake `datalib-http`
(`datalib_launcher_testing.py`); `test_datalib_pin.py` holds the skill to the
version the install script installs, and the program to `autostart=false`.
