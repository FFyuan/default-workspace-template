Reverts the build-app plan recorder (#530).

Removes `system/scripts/imbue_plan_extra/` (the `write_plan.sh` wrapper and its
`build-app` prompt) and the exemption for `write_plan.sh` in
`agent_require_steps_pretool.sh`.

Keeps `data/.imbue/plans/CLAUDE.md` (shortened to the instruction alone), its
`.gitignore` rules and its `data/README.md` line. Workspaces that ran the recorder still hold plans under
`data/.imbue/plans/`, and the `CLAUDE.md` is what tells agents not to read or
act on them; only each `plan.md` carries its own warning, not the `brief.md`
beside it.
