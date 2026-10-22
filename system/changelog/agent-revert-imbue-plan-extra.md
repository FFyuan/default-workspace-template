Reverts the build-app plan recorder (#530).

Removes `system/scripts/imbue_plan_extra/` (the `write_plan.sh` wrapper and its
`build-app` prompt), the tracked `data/.imbue/plans/CLAUDE.md` with its
`.gitignore` rules and `data/README.md` line, and the exemption for
`write_plan.sh` in `agent_require_steps_pretool.sh`. Plans already written
under `data/.imbue/plans/` in existing workspaces are left in place.
