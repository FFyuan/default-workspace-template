An update-self pass can now run to the end with nobody watching. The lead has the user's licence to clear the way without asking: it may pause other chats and background agents, stop the browser and windowless apps, prune dead workers' worktrees, unused apply snapshots and tool caches, and save a dirty tree as one work-in-progress commit instead of refusing the update. An abandoned "updating workspace" lease is taken over by rule. The results message names every such action with its undo.

When the Imbue Studio app's message pins the target and ceiling, Step 2 (and Step 3a's re-check) use them and never ask the app for its version, so a pass runs while the app is closed.

A customization the update cannot keep now ends the pass with a new `NEEDS_DECISION` verdict instead of waiting: the worker is stopped with its branch kept, the leases are released, and the user's answer in the chat, whenever it comes, re-lands the kept pass ("Resuming after a decision").

Chats are no longer waited on before the apply. Right before it, `run-status stop-chats` pauses the busy chats and background workers and records them, their uncommitted work is saved, and after the apply `run-status resume-chats` starts each again and sends it a note, shown in the chat as a "Workspace updated" notice. A rolled-back apply is retried only by the lead's judgment of its cause, and the pass opens its chat's window once the results are ready.

The run record gains `started_by` (taken from the app's last dispatch when it made this chat) and `stopped_agents`.
