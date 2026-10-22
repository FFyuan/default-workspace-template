Every chat's agent now records the chat as the origin of its model calls (`IMBUE_USAGE_CONTEXT`), so its usage, and that of any background worker it launches, is attributed to the chat. Antigravity chats, whose harness reports no usage, now record each finished turn in the workspace's usage as one model call with unknown tokens and cost.

Chat titles and antigravity turns are recorded in the workspace's usage event files rather than posted to the usage collector.
