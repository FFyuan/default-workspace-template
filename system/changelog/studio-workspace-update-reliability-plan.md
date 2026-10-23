Bug reports now include the update flow's records from `data/.state/update-apply/` (the schedule, the run record, the last dispatch, the watchdog state, an apply marker, an emergency record, a provisioning-incomplete record, the kept rollback point, and the dispatcher log's tail) as their own secret-scanned class. The pre-apply snapshots and the dispatcher program are never included.

A pointer to the unattended workspace updates plan, which lives in the mngr repo, is at `docs/system/blueprint/unattended-workspace-updates/`.

The routines spec (`docs/system/specs/routines/spec.md`, section 12) now says the cron migration leaves the Imbue Studio app's `update-self-dispatch` entry with cron.
