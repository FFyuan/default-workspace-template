A chat whose agent ended its turn to wait on a background task no longer reads as done. The chat is busy: its agent will resume on its own when the task's report arrives.

- Chats have a new status, `background`: the agent is between turns, no permission request is waiting, and a background task it started is still pending. A chat reads stopped, attention, working, background or idle, the first that holds. The chat list draws it as a dashed accent ring that turns slowly (held still under reduced motion); a chat with a turn running keeps the working dot, tasks or not.

- The chat list's green check now waits for the wait to end: a chat that ends its turn to wait on a background task is not marked done, and is marked once it goes idle with nothing pending while you are looking at another chat.

- Above the message box, below the activity line, a wait line appears whenever background tasks are pending: "Waiting on 2 background tasks · 4m 05s", timed from the oldest. Pressing it lists each task with its description and how long it has run.

- Switching a chat to another provider, or to another account, now says what happens to the background tasks it is waiting on: the agent's own background tasks stop with the switch, and commands started through `run_in_background.py` keep running and their results arrive in the chat. The agent that takes the chat over is told which tasks were stopped and which will still report.

- A Claude background task that has finished stops counting as soon as Claude's transcript records its end, even when you stop the turn that the task's completion started or that turn fails. Before, such a task kept its chat reading busy until a later turn ended normally.

- The chat app reads each chat's pending tasks from `data/.apps/chat/background_tasks/<chat-id>/` (the markers `run_in_background.py` and Claude's Stop hook write) on the same once-a-second poll that reads model changes (it creates that directory's root when it starts), and rechecks every waiting chat's task processes on each pass, so a task killed for memory returns its chat to idle within a second. A turn that ends to wait shows the wait at once. The tasks belong to the chat, so after a switch to another agent the new agent shows the same wait.

- Each chat snapshot's `active_agent` carries `is_busy` and `background_tasks`. `GET /api/agents` items carry `chat_id`, `is_busy` (a turn in flight, or the chat's pending tasks) and `background_tasks` (the chat's tasks, on its active agent only), which `background_tasks.py list` and `is-busy` read. `GET /api/agents?tracked=true` answers from the agent list the chat app already follows, without asking mngr to discover agents.

- The memory prioritizer treats a busy chat like one with a turn running, so a chat waiting on a background task is not aged toward being shed.
