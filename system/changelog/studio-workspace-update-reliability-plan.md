Bug reports now include the update flow's records from `data/.state/update-apply/` (the schedule, the run record, the last dispatch, the watchdog state, an apply marker, an emergency record, a provisioning-incomplete record, the kept rollback point, and the dispatcher log's tail) as their own secret-scanned class. The pre-apply snapshots and the dispatcher program are never included.

`message_chat.py --create` takes `--title`, the chat's display name apart from its agent's name, and falls back gracefully on a chat app or mngr from before it.

A pointer to the unattended workspace updates plan, which lives in the mngr repo, is at `docs/system/blueprint/unattended-workspace-updates/`.
