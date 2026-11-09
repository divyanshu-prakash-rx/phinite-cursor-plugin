---
name: phinite-api
description: Phinite platform API reference — auth (Bearer token), tools, flows, versions, builds, triggers, Chat API, autonomous tests, logs, env variables, BYOM models, files, with verified payloads. Use when a plugin tool doesn't cover something, or to understand exactly what a plugin tool calls.
---
# Phinite API reference

Full reference with verified payloads: `references/01_PHINITE_API.md`. It comes from the playbook, so it mentions
the playbook's `kit/` scripts; the plugin doesn't ship them, and the `phinite` MCP tools do the same work.

- Base `https://app.phinite.ai/api/v1` (dev `https://app.dev.phinite.ai/api/v1`); ai-core (triggers, Chat API)
  through the gateway at `https://app.phinite.ai/api/v1/ai` (dev `https://webhook.dev.phinite.ai/api/v1/ai`) —
  `ai-core.phinite.ai` is internal only.
- Auth: `Authorization: Bearer <user token>`. Triggers and the Chat API take a **workspace API key** as Bearer
  instead. Send a non-`python-requests` User-Agent.
- List endpoints return one record per version (draft + published); collapse by id.
- Prod serves flows under `/flow_V2` (create, list, update, details) but publish/latestVersion under `/flow`.
- Knowledge bases: `/datasource` (list `GET /datasource/{ws}/live`, details `?datasourceid=`, create `POST`) and
  `/dataSourceItem` (upload-url → PUT → register, `status/{id}`); agents reference them in `datasource_ids`.
  Spelling matters on prod's gateway.
- Model catalog: `GET /models_V2?modelType=<text|image|video|audio|document>&operation=<analysis|generate>` (prod);
  each model lists inputType, outputType, toolCallSupport. Media go in `image`/`audio`/`video`/`document` URL lists
  (test chat: not on the first turn) or as multipart files (triggers).

Use the `phinite` MCP tools. They wrap these calls, keep secrets out of the chat and apply the rules (publish
changed tools, collapse versions, resolve BYOM ids). The plugin signs in with OAuth through the hosted MCP server,
so this machine holds no Phinite token. Use this reference to understand what a tool does, not to call the API
directly: never ask the user for a token, cookie or API key, and never put one in a script, file or the chat. If no
tool covers a need, say so and point the user to the Phinite UI.
