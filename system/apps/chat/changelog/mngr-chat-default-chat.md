The workspace now has a **default chat**, where a message with no chat of its own goes. The chat the Mind app seeds is the default to begin with, and is now named "Default chat" instead of "Welcome"; that name is kept rather than replaced by one drawn from the first message, until you rename it:

- The chat list always leads with it (its helpers under it), in a medium weight and set off from the other chats by a thin rule, instead of sorting it by recency.

- With no chat selected, the chat list opens on it rather than on the most recently messaged chat; deleting the chat on screen also returns you to it.

- Pressing Enter in the desktop's launcher sends the text to the default chat ("Send to default chat"). "New Chat" moves to the second row, so Cmd+Enter (Ctrl+Enter elsewhere) starts a new chat, and "Send to chat..." stays in the list without a key.

- A draft or message sent to the "current chat" from a window that shows none (the desktop's "Design your own...") lands in it.

- Any chat you started can be made the default from its right-click menu (and the phone layout's kebab): "Make default chat". It moves to the top in place of the old default.

- The default chat can be deleted like any chat. Another chat becomes the default right away (the one messaged most recently, never a helper chat an agent started) and moves to the top; with no chat left, the new chat the list opens becomes the default.

The default is kept as a pointer in `data/.apps/chat/default_chat.json`, not as a property of any chat. `chats_updated` pushes and `GET /api/chats` carry it as `default_chat_id`.
