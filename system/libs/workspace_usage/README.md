# workspace_usage

Reports the model calls a workspace app makes to the workspace's usage
collector (`system/services/usage_collector`), so every call is counted and
attributed even when it is made outside an agent.

- **Attribution** (`context`): `read_usage_context()` reads the
  `IMBUE_USAGE_CONTEXT` a starter handed down (`origin_kind=CHAT,origin_id=...`).
  Without one, a process under supervisord is attributed to its app (the app
  registry maps the program to its manifest name) or, for any other program,
  to the workspace (`SYSTEM`); anything else is `UNKNOWN`.
- **Direct LiteLLM calls** (`litellm_usage`, the `litellm` extra): call
  `install_litellm_usage_callback()` once at start; every `completion` after
  that is reported, successes and failures.
- **`claude -p` one-shots** (`claude_one_shot`): run `claude -p` with
  `claude_session_args(session_id)` instead of `--no-session-persistence`, then
  call `report_claude_one_shot(config_dir, session_id, purpose=...)`. The
  collector reads the calls from the session log and deletes it.
- **Anything else** (`events`, `emit`): build a `model_call` with
  `build_model_call(...)` and send it with `emit_model_call(...)`.

Delivery never raises and never fails the call: a report the collector cannot
take right away is spooled to `data/.apps/usage/spool/` and drained later.

The library does not import mngr, so an app's tool environment stays small;
the collector's tests hold its output to mngr_usage's `model_call` schema.
