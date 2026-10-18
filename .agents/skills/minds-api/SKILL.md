---
name: minds-api
description: "Use to act on OTHER Imbue Studio workspaces on the user's behalf -- list them, create a fresh one, SSH into one, read or export its backups, start/stop/destroy/recover it, or change its settings. The imbue-studio skill (vendored beside this one) teaches how to reach the API and read its schema; this skill adds what only applies from inside a workspace: the permission verbs, the SSH and backup-export flows, and the rules for creating a workspace from here. For bringing another workspace's content into this one, use the migrate-workspace skill, which drives these routes as part of a much larger flow."
compatibility: Requires latchkey (the standard agent gateway) and curl; ssh/ssh-keygen for the SSH capability. The vendored imbue-studio skill in `.agents/skills/imbue-studio/`.
metadata:
  author: imbue
---

# Imbue Studio API, from inside a workspace

The `imbue-studio` skill (`.agents/skills/imbue-studio/`, the published skill
vendored into every workspace) is the entry point: it says how to reach the API
from wherever you are, that `GET /api/schema` is the live contract to read
before assuming any route or field, how long operations are polled, and what
never to do with the user's credentials. Load it first. In one breath: from
inside a workspace every call is `latchkey curl
http://latchkey-self.invalid/minds-api-proxy/api/...`; you never hold a token;
the schema lists only the routes the gateway can reach; a long operation
answers `202` with an operation handle that you poll until `is_done`; and you
never ask for, read, or send the user's credentials or master password.

This skill adds the parts that exist only on this side of the gateway.

## Permissions

No grant is needed for `GET /api/schema`, `GET /api/v1/app/version`,
`GET /api/v1/timezone`, or your own agent's routes under
`/api/v1/agents/<your id>/`. Every `/api/v1/workspaces/...` call is gated by the
`minds-workspaces` detent scope, one permission per verb. The gateway's own verb
list is the authority (a `403` names the request as not permitted, never the
verb); these are its verbs today:

| Verb permission | Covers | Targeted? |
|---|---|---|
| `minds-workspaces-read` | list, detail, version, backups (read) | no (all workspaces) |
| `minds-workspaces-create` | create a new workspace | no |
| `minds-workspaces-ssh` | establish SSH access | yes |
| `minds-workspaces-backups-export` | export a backup snapshot | yes |
| `minds-workspaces-backups-manage` | enable, disable, repoint, or verify backups | yes |
| `minds-workspaces-destroy` | destroy a workspace | yes |
| `minds-workspaces-lifecycle` | start / stop the host | yes |
| `minds-workspaces-update` | update settings (color, account) | yes |
| `minds-workspaces-recover` | health check, restart, machine resize | yes |

Targeted verbs are granted per workspace, so ask for one workspace at a time.
File a `type: "workspace"` request, one per tool call with nothing else in it
and its output untouched, then end your turn and wait for the user's answer:

```bash
latchkey curl -XPOST http://latchkey-self.invalid/permission-requests \
  -H 'Content-Type: application/json' \
  -d '{"agent_id": "'"${MINDS_CHAT_ID:-$MNGR_AGENT_ID}"'", "type": "workspace",
       "payload": {"permissions": ["minds-workspaces-ssh", "minds-workspaces-backups-export"],
                   "target_workspace_id": "<TARGET_WORKSPACE_AGENT_ID>"},
       "rationale": "I need SSH and backup-export access to <name> to bring its content into this workspace."}'
```

`payload.permissions` lists verbs from the table; `payload.target_workspace_id`
names the workspace the targeted verbs act on (null for `read` and `create`, or
to ask for a verb across every workspace). Request exactly the verbs the task
needs, with a rationale that names the workspace and the goal; the user sees
them as checkboxes per workspace.

A workspace is addressed by its agent id. Your own is usually `$MNGR_AGENT_ID`;
confirm it appears in `GET /api/v1/workspaces` if you need to self-reference.

## Creating a workspace from here (`minds-workspaces-create`)

`POST /api/v1/workspaces` answers `202` with an operation handle; poll
`/api/v1/workspaces/operations/create/<op>` until `is_done` (its `/logs` route
streams the create log). Two rules apply only when creating from a workspace:

- **Always send `branch`, read from `GET /api/v1/app/version`** (its
  `workspace_template_ref`): the release this app was built against. Omitted,
  the new workspace takes the template's default branch, unreleased code. Never
  send the newest upstream tag, which may be a release this app does not
  support. If the read fails, say so and create nothing.
- **Leave every `backup_*` field unset** (the default is
  `backup_provider=CONFIGURE_LATER`). Configuring backups can involve the user's
  storage credentials, which you never ask for or send; the user enables backups
  from the desktop app afterwards.

```bash
REF=$(latchkey curl http://latchkey-self.invalid/minds-api-proxy/api/v1/app/version | jq -er .workspace_template_ref) || exit 1
latchkey curl -XPOST http://latchkey-self.invalid/minds-api-proxy/api/v1/workspaces \
  -H 'Content-Type: application/json' \
  -d '{"git_url": "<template-repo-url>", "branch": "'"$REF"'"}'
```

## SSH into another workspace (`minds-workspaces-ssh`)

Generate a keypair locally; only the public key leaves you, and the grant is
time-limited. Pass your own workspace id as `requester_workspace_id`: the hub
needs it to dedupe your grant and, for a *local* target, to broker a tunnel
back into your container.

```bash
ssh-keygen -t ed25519 -N '' -f /tmp/mind_key
CONN=$(latchkey curl -XPOST http://latchkey-self.invalid/minds-api-proxy/api/v1/workspaces/<TARGET_ID>/ssh \
  -H 'Content-Type: application/json' \
  -d '{"public_key": "'"$(cat /tmp/mind_key.pub)"'", "requester_workspace_id": "'"$MNGR_AGENT_ID"'"}')
ssh -i /tmp/mind_key -p "$(echo "$CONN" | jq -r .port)" \
    "$(echo "$CONN" | jq -r .user)@$(echo "$CONN" | jq -r .host)"
```

- A **remote** target answers with its real address. A **local** (Docker/Lima)
  target answers `host="127.0.0.1"` and a port reachable from inside *your own*
  workspace (the hub reverse-tunnels into your container), so run the `ssh`
  from here.
- The grant expires at `expires_at`; re-request to refresh (it does not stack).
- `502` usually means the target (or your own container) is offline; `404`
  means the workspace id is unknown.

## Exporting a backup (`minds-workspaces-backups-export`)

`GET /api/v1/workspaces/<id>/backups` lists snapshots, even for an offline or
destroyed workspace. An export is a binary stream; save it under `/var/tmp`,
which is disk: an export can run to many GB, and `/tmp` is memory.

```bash
latchkey curl -o /var/tmp/restore.zip \
  -XPOST http://latchkey-self.invalid/minds-api-proxy/api/v1/workspaces/<id>/backups/<snapshot_id>/export
```

## Migrating an old workspace into a fresh one

That is **the `migrate-workspace` skill's job, not this one's.** Do not
improvise a migration out of these routes: the real flow resolves what the
user actually authored, maps paths across the tree reorganization, re-registers
apps and scheduled jobs, recreates every past chat, and re-audits credential and
permission call sites. This skill only supplies the plumbing it uses.

- **In the NEW workspace** (the user asks you to bring their old stuff over):
  load `migrate-workspace` and follow it.
- **In the OLD workspace** (the user wants to move to a new one): create the
  fresh workspace as above, then tell the user to open it and ask its agent to
  migrate. Copy nothing yourself.
- If the old workspace cannot be started at all, export its newest snapshot and
  work through the contents with the user by hand.

## Notes

- A connection error (curl exit 7) usually means the user's computer is offline.
- Do not expose the proxy or gateway mechanics to the user unless they ask; talk
  in terms of "your workspaces".
- General latchkey usage and the predefined-service permission flow are in
  `.agents/skills/connect-external-service/references/latchkey.md`.
