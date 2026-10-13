datalib ships in every workspace, unannounced and off by default, so it can be tried without adopting the separate datalib template.

- `system/scripts/env.d/2000-datalib-binaries.sh`: installs the pinned datalib release (v0.42.0, the static musl build) into `~/.local/share/datalib/<version>/` and links every binary into `~/.local/bin`. It downloads the binaries only; datalib's Node runtime (about 100 MB) is fetched when the skill is first used.

- `system/supervisord.conf.d/datalib.conf`: the `datalib` program that runs the Datalib app (see `system/apps/datalib/`), with `autostart=false`.

- `pyproject.toml`: `system/apps/datalib` is excluded from the uv workspace, like the file viewer.
