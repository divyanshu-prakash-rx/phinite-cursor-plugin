---
name: phinite-ship
description: How to take a tested Phinite graph live — publish tools and flow, create and assign an agent build, create triggers (autonomous) or a Chat API channel (conversational), workspace API keys, and calling them from outside. Use when publishing, building, deploying to an environment, or exposing a graph.
---
# Shipping a Phinite graph

Checklist: `references/05_BUILD_CHECKLIST.md`. API details: the `phinite-api` skill. The checklist comes from the
playbook: where it runs a `kit/` script, use the matching `phinite` MCP tool, and skip the `set_auth.py` sign-in
step (the plugin signs in with OAuth).

**Every trigger and channel runs a flow only through a build assigned to the environment it is called in.**
Without one, Phinite answers "We don't have any build for this trigger in this env" (the plugin's `call_trigger`
and `chat_api` check this first). After changing a graph, publish and build again: a build is a snapshot.

**Order (each step depends on the previous)**
1. **Tools published.** Flow tests and builds use the latest *published* tool version (draft 0 only if never
   published). `deploy_project` / `upsert_tool` publish changed tools; `create_build` refuses unpublished tools.
2. **`publish_flow`** → flow version N (copies the draft). Triggers and builds need a published version.
3. **`create_build`** → pins flow version N + the latest published version of each tool, and assigns the build to an
   environment (development → uat → production; production needs an earlier dev/uat assignment). Assigning is
   exclusive: other builds of the same flow lose that environment.
   - **Env variables per environment.** Each env variable has a separate value per environment, and
     `set_env_vars` fills only `development` unless told otherwise; a new variable starts **empty** in uat and
     production. Before the first run in uat or production, set that environment's values: `env-check` with that
     environment's file (`--env-file`), then `set_env_vars(names=[...], environments=["uat"])` (or
     `["production"]`). Values already stored for other environments are kept.
4. **Expose it**
   - Autonomous: **`create_trigger`** — kind `api` (sync), `background` (start + poll) or `cron`. URL:
     `https://app.phinite.ai/api/v1/ai/trigger/<workspace>/<trigger_id>/<env>` (background: `/trigger/start/...`,
     then `/trigger/status/<workspace>/<workflow_id>`). Body `{"message", "user_variables": {...}}`;
     `user_variables` become session variables of the run. (`ai-core.phinite.ai` is internal-only.)
   - Conversational: **`create_chat_api`** — `POST https://app.phinite.ai/api/v1/ai/chat_api/<integration_id>/<env>`
     (first turn opens with "hi"; no user_variables), then `POST .../api/v1/ai/chat_api/<session_id>` with
     `{"message"}`. Integrations must carry `type`/`subType`/`category` like the UI's (the tools send them) — a
     trigger without `category: "trigger"` can never run.
   - Teams/Slack/WhatsApp channels and conversational triggers (`trigger_conv`, hand-off to a channel) are set up in
     the UI for now; `list_integrations` shows them.
5. **`create_api_key`** — callers authenticate with `Authorization: Bearer <workspace API key>`. The key stays in
   Phinite and is never shown: `call_trigger` / `chat_api` read it per call, and people copy it from the Phinite UI
   (API keys) for their own apps. A tool that triggers another graph reads it from a workspace env variable (e.g.
   `PHINITE_TRIGGER_API_KEY`, set with `set_env_vars(names=["PHINITE_TRIGGER_API_KEY"])`).
6. **Prove it from outside**: `call_trigger` / `chat_api`, then `get_logs` on the workflow id.

Use full environment names (`development`, `uat`, `production`) in URLs. Re-run steps 2–3 after every change you
want live: a build is a snapshot. Callers can send files: multipart `files` to a trigger, and
`image`/`audio`/`video`/`document` URL lists to the Chat API. `call_trigger` sends no files (the hosted server can't
read local files), so test a run with files through `run_autonomous` with file URLs.
