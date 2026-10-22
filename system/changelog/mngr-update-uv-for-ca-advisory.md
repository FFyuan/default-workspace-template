Workspaces stop trusting the compromised emSign/eMudhra CA chain (`emSign ECC Root CA - G3`, eight intermediates whose private keys are trivially recoverable), and `uv.lock` stops churning.

- The provisioner installs uv 0.13.4 (was 0.11.7), Node 24.22.1 (was 22.23.2), Claude Code 2.1.307 (was 2.1.293) and modal 1.6.2 (was 1.4.2). The venv's certifi is 2026.10.19. The apt snapshot moves to `20261021T180000Z` with a matching base image, which brings `ca-certificates` 20250419+deb13u1. Existing workspaces get all of this from a normal update: the changed provisioner and apt timestamp re-run it, and the changed lock re-syncs the venv.

- Workspaces, CI and mngr's pin bump now all write `uv.lock` with the same uv. Before, a workspace's uv 0.11.7 rewrote the lock's header and markers on every re-resolve, so agents threw the diff away, and real new entries went with it. `system/toolchain_pins_test.py` fails when CI's setup-uv or setup-node version differs from the provisioner's, or when setup-uv is referenced at more than one commit SHA.

- When the provisioner changes uv's version it runs `uv cache prune`, which drops the old uv's cache buckets (36 MB on a small test cache; workspaces carry much more). If a running `uv run` holds the cache lock for over 60 seconds, the prune is skipped with a message.

- uv tool installs and the venv stay on Python 3.12 (`UV_PYTHON=3.12` in the provisioner and build scripts), even though uv 0.13 defaults open-ended requests to 3.15. The runtime environment is unchanged.

- Fortress (the workspace browser) gets a managed `CADistrustedCertificates` policy listing the eight intermediates, written on every boot. Its bundled Chromium still trusts the bad root and never receives Chrome's CRLSet, because Playwright disables component updates. The policy path and format are verified from Chromium 151's source and the Fortress binary, but not yet by running Fortress.
