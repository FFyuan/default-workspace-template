The create route takes an optional `title`: the chat shows the title, and its agent is named for the requested name in canonical form, so an update chat can be `update-to-minds-v0-9-0` and read "Update to v0.9.0". Only the name is checked against the names in use, and a handoff's successor keeps the chat's true name. A create without a title behaves as before.

The note update-self sends a chat it paused for an update renders as a one-line notice labelled "Workspace updated" (or "Workspace update not applied"), on every harness.

`open=providers` in the chat root's URL opens the provider chooser once on arrival, for the Imbue Studio app's sign-in button.
