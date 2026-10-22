Reverts the build-app plan recorder (#530).

`build-app` no longer starts by running
`system/scripts/imbue_plan_extra/write_plan.sh`, so building an app no longer
starts a second headless claude session that records a routing plan in the
background.
