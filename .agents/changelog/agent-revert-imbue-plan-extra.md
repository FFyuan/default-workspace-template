Removes the build-app plan recorder added in #530. If your workspace had it,
building an app no longer starts a second headless claude session that records
a routing plan in the background. Workspaces that never had it see no change.
