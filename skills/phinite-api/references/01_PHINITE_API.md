# 01 · Phinite API reference (as used and verified)

- **Base:** `https://app.phinite.ai/api/v1` (dev: `https://app.dev.phinite.ai/api/v1`, Swagger at `/api/v1/api-docs`).
- **Auth, simplest (verified 2026-10-22):** `Authorization: Bearer <phinite_access_token>`, the JWT from your browser cookie. It works on every route, reads and writes, with **no cookie and no `x-csrf-token`**. CSRF is only checked when a session cookie is sent without a Bearer header. The Claude plugin (`CIQ-UCS/phinite-claude-plugin`) signs in this way.
- **Auth, kit scripts:** `Cookie`, `x-csrf-token`, `content-type: application/json`, `origin`, `referer: https://app.phinite.ai/<ORG>/workspace/<WS>`. `kit/phinite.py` wraps all of this.
- **User-Agent:** the edge firewall answers **HTML 403** to User-Agents containing `python-requests` on some routes (seen on `/testing/tool/conversations`). Send your own, e.g. `phinite-claude-plugin/0.1`. `curl` and browser UAs pass. The kit sends a browser UA, which is why it never hit this.
- **List endpoints return one record per version.** `GET /tool` and `GET /flow_V2` list the draft (`version: 0`) **and** every published version of the same id. Collapse them by id, keep the draft, and take the highest `version` as the latest published.
- Most calls need `workspaceid` (query string or body).

## Tools

| Action | Call |
|---|---|
| List | `GET /tool?workspaceid=WS` → **plain array** of `{toolid, name, api_code, params, capture_variables, description, …}` |
| Create | `POST /tool {"workspaceid": WS, "projectid": [], "name": "my_tool", "description": "…"}` → `{toolid, …}` |
| Update | `PUT /tool/{toolid} {"workspaceid": WS, "description": "…", "api_code": "<base64 of the code>", "is_encoded": true, "params": [], "capture_variables": [{"name": "case_id", "type": "String", "llmDescription": "…"}]}` |
| Publish | `PUT /tool/publish/{toolid} {"versionDetails": "notes"}` → 201 `{version: N}`. It copies the current draft to a new version N (highest + 1). |
| Read a version | `GET /tool/versions/{toolid}/{N}` → the version, with `api_code` stored as **plain text**. 404 if it doesn't exist. There is no "list versions" route; use the list endpoint above. |
| Delete | **Not possible on prod (Oct 2026).** `DELETE /tool/{id}` returned 500, a foreign key to `tool_versions`; dev code fixed it on 2026-10-07. Reuse names and update in place. |
| Test (run one tool) | `POST /testing/tool/conversations {"toolid", "version": "0", "inputs": {...}, "env": "development", "workspaceid": WS}` → `{"result": {"output", "capture_variables"}}`. See [Testing one tool](#testing-one-tool). |

- **Tool names are workspace-unique.** They are also the function name the LLM sees, so use `snake_case` verbs.
- `params: [{"name", "type", "description"}]` is accepted, but **keep it `[]`**. Why: [02 § Variables](02_GRAPH_DESIGN.md).
- **Tool code contract:** `def main(inputs, env_variables) -> {"output": {...}, "capture_variables": {...}}`. `capture_variables` returned by a tool become session variables available to later tools and agents.

### Which tool version a run uses (verified live 2026-10-22)

**Flow tests (chat, autonomous test) run each tool's latest *published* version, or draft 0 if it was never published.** A flow publish does not pin tool versions; only an agent build does.

The probe that proved it:
1. Publish the tool as v1, which returns `MARK_A`.
2. Edit the draft so it returns `MARK_B`. Both the published flow and the draft flow still ran `MARK_A`.
3. Publish v2. The next run returned `MARK_B`.

So once a tool has been published, **every change must be published again**, or tests silently run the old code. `deploy_project` in the plugin does this. It compares the new code, params, captures and description with the latest published version, and publishes only when they differ.

## Testing one tool

`POST /testing/tool/conversations` runs one deployed tool once, the same call Studio's tool test panel makes. In the kit, use `kit/test_tool.py` or `Phinite().test_tool(...)`.

```json
{"toolid": "<toolid>", "version": "0", "inputs": {"caller_number": "+19028292029"}, "env": "development", "workspaceid": "<WS>"}
```
returns
```json
{"result": {"output": {"found": true, "account_id": "AC1001", "customer_name": "Shashank", "...": "..."},
            "capture_variables": {"verified_account_id": "AC1001", "customer_name": "Shashank"}}}
```

- **`inputs`** is exactly what the tool's `main(inputs, env_variables)` receives. Nothing is added: no capture variables, no `conversation_history`, no `workflow_id`. Send every value the tool reads, as strings, the way captures arrive.
- **`env`** is `development` (the default), `uat` or `production`. Don't send env variables: Phinite fills `env_variables` from the workspace environment you name. Verified 2026-10-20: `collect_github_activity` read `GITHUB_TOKEN` this way under both `development` and `production` (that workspace has it set in both).
- **`version`:** `"0"` is the current draft, which is what `kit/deploy.py` updates.
- **The response** is the tool's return value under `result`. In a graph run, `output` goes back to the agent that called the tool, and each `capture_variables` key and value is stored as a session variable that later tools and agents receive.
- **It really runs.** DB writes, SMS, Slack posts and other side effects happen, so give tools with side effects a dry-run input.
- **Speed:** calls took 1.6–3.2 s for the GitHub/Slack tools (verified on `app.phinite.ai`).

## Graphs (flows)

| Action | Call |
|---|---|
| List | `GET /flow_V2?workspaceid=WS&page=N&limit=50` → `{data: [...], pagination: {hasNextPage}}`. One record **per version** (draft + published), each with `blocks_content`, `edges` and `totalVersions`. |
| Create | `POST /flow_V2 {"name", "description", "graphType": "conversational" \| "autonomous", "workspaceid": WS}` → `{flowid}` |
| Update | `PUT /flow_V2/update/{flowid}` with what Studio sends on save (captured 2026-10-23): `{"edges", "blocks_content", "isSaved": true, "isPublished": false, "workspaceid"}` (the route also accepts `name`, `description`). **No `nodes`**; each block carries its own `position`, `width`, `height` and `label`. **Send the complete graph every time; it replaces draft 0.** Edges whose ends aren't block ids are dropped, as are unknown keys inside `details`; empty `tools: []` and `provider: null` are stored as absent. |
| Publish | `PUT /flow/publish/{flowid} {"versionDetails": "notes"}` → 201 `{version: N}` (note: `/flow`, not `/flow_V2`). It copies draft 0 to version N, and fails with 400 if the draft has no blocks. |
| Read | Draft or latest: `GET /flow_V2?flowid=ID`. A version: `GET /flow_V2/details/{flowid}?version=N` (`/flow/details` is 404 on prod). Count: `GET /flow/latestVersion/{flowid}` → `{totalVersions}`. |
| Duplicate | `POST /flow/duplicate/{flowid} {"name"}` (Swagger; not exercised yet) |
| Delete | **Not possible** (500, foreign key to `flow_versions`). |

**Route families:** the dev code (2026-10-19) folded `/flow_V2`, `/tool_V2` and the other `_V2` routes into the plain ones (`/flow`, …); prod still serves `/flow_V2`. The plugin client tries `/flow_V2` first and falls back to `/flow` when a route is missing (an HTML or plain-text 404, as opposed to a JSON "not found").

`graphType` can't be changed after creation, so create a new graph to switch it.

### `blocks_content` (what Studio saves, 2026-10-23; the plugin's graph builder sends the same)

```jsonc
[
 {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "width": 74, "height": 32, "label": "Start", "details": {}},
 {"id": "my-master", "type": "task", "position": {"x": 495, "y": 255}, "width": 230, "height": 211,
  "selected": false, "dragging": false, "label": "My Master", "details": {
    "name": "My Master", "type": "task agent", "task_prompt": "<markdown prompt>",
    "tools": [{"toolid": "abc123", "name": "my_tool"}], "predefinedTools": [], "mcp_tools": [],
    "datasource_ids": ["<knowledge base id>"], "top_k": 3, "threshold": 0.2,      // RAG (empty list = none)
    "capture_variables": [{"id": 1234567890123, "name": "county", "type": "String",
                           "llmDescription": "County where the business is", "variableType": "ai-derived"}],
    "input_variables": [{"id": 1234567890124, "name": "application_id", "type": "String"}],
    "decision_variable": [], "child_nodes": ["my-child"], "jev_nodes": [], "agent_node": [],
    "orchestration_model": {"modelName": "gpt-5.2", "apiKeyName": "Phinite Api", "envencryptid": null,
                            "resource": "text", "operation": "analysis", "workspaceId": WS, "createdAt": "<iso>",
                            "model_config": {"max_tokens": 8192, "reasoning_effort": "medium"}},
    "provider": null}},
 {"id": "my-child", "type": "child", "position": {...}, "width": 230, "height": 211, "selected": false,
  "dragging": false, "label": "My Child", "details": {
    "name": "My Child", "type": "child agent", "task_prompt": "…", "tools": [], "predefinedTools": [],
    "llm_tool_description": "What the child does (the master sees this as a tool description)",
    "orchestration_model": { /* resource text|image|video|audio|document, operation analysis|generation */ },
    "provider": null, "child_variables": {"capture_variables": [...], "input_variables": [...]},
    "decision_variable": [], "datasource_ids": [], "mcp_tools": [], "top_k": 3, "threshold": 0.2}},
 {"id": "end", "type": "end", "position": {"x": 0, "y": 0}, "width": 59, "height": 32, "label": "", "details": {}}
]
```

- **`model_config`** is what Studio fills from the model catalog: each parameter's `default` in the model's
  `modelConfig` schema (`GET /models_V2` records), e.g. gpt-5.2 → `{max_tokens: 8192, reasoning_effort: "medium"}`,
  gemini-3.1-pro-preview → `{top_k, top_p, max_tokens, temperature, thinking_level}`. Claude 4.5+ notes say not to
  send `temperature` and `top_p` together; the plugin keeps `temperature`.
- **`edges`:** `{id: "reactflow__edge-<src>-<tgt>", source, target, sourceHandle: "right", targetHandle: null, type: "custom", data: {label, bidirectionalArrows}}`.
- **Child edges** run child → parent with `bidirectionalArrows: true`.
- **Master-to-master edges** carry a label; with several outgoing edges the router picks by label ([07 § 2](07_MULTIAGENT_AND_MULTIMODAL.md)).
- **Variable `id`s** are stripped by the server and can be random.
- **System tools** (RAGTool, FinishTool, FlowEndTool, StoreVariableTool) need no config. Just name them in the prompt. StoreVariableTool is for children only.

### Models (`orchestration_model`)

- **Model catalog (verified 2026-10-23):** `GET /models_V2?modelType=<text|image|video|audio|document>&operation=<analysis|generate>` → `{models: [{name, provider, model_label, inputType, outputType, toolCallSupport, phinite_default, …}], count}`; 92 models on prod, the same list as the UI's model picker. Newer servers serve it at `/models`. Details and the per-task rules: [07 § 4](07_MULTIAGENT_AND_MULTIMODAL.md).
- **Current UI block for a Phinite-hosted model:** `{"modelName", "resource", "operation", "envencryptid": null, "developMode": "phinite"}` (+ optional `model_config`), `provider: null`.

| Model | `orchestration_model` | `provider` |
|---|---|---|
| Phinite-hosted gpt-5.2 | `{"modelName": "gpt-5.2", "apiKeyName": "Phinite Api", "resource": "text", "operation": "analysis", "workspaceId": WS, "envencryptid": null, "createdAt": "<iso>"}` | `null` |
| BYOM Gemma_CIQ | `{"modelName": "google/gemma-4-31B-it-qat-w4a16-ct", "compatibleApi": "openai", "modelLabel": "Gemma_CIQ", "byomid": "x1pD7JX", "developMode": "byom", "resource": "text", "operation": "analysis", "workspaceId": WS, "envencryptid": null, "createdAt": "<iso>"}` | `"byom"` |
| BYOM Mistral_CIQ | Same shape with `"modelName": "mistralai/Ministral-3-8B-Reasoning-2512"`, `"modelLabel": "Mistral_CIQ"`, `"byomid": "_VzlpRl"` | `"byom"` |

- **Children** set `operation` to `analysis` or `generation` and `resource` to `text|image|video|audio|document`.
- **BYOM models are per workspace.** `GET /byok/byom/catalogs?workspaceid=WS` → `[{byomid, modelName, modelLabel, compatibleApi, …}]` (verified 2026-10-22). Example: YGG93YE lists Gemma_CIQ `x1pD7JX` and Mistral_CIQ `_VzlpRl`; a fresh workspace lists none. A graph copied to another workspace must take the `byomid` from that workspace's catalog. The plugin's graph builder matches the model by `modelLabel`. `GET /models` returned 404 on prod.

## Chat and test (Studio test chat; also runs autonomous graphs)

`POST /stream/process_query?workspaceid=WS` returns Server-Sent Events: `data: {...}` lines, decoded as UTF-8.

- **Start a session:**
  ```json
  {"message": "Hi", "flow_id": "<flowid>", "flow_version": "0", "env": "development", "workspaceid": "WS",
   "user_variables": {"application_id": "SGP-2026-00001"}, "image": [], "audio": [], "video": [], "document": []}
  ```
- **Send a `Unique-Id: <uuid>` header on the first call.** It becomes the `workflow_id`, which was verified. ai-core keeps run state in memory per server, and the id routes follow-ups to the same one.
- **Continue it:** `{"workflow_id": "<from the first response>", "message": "next turn"}`
- **This test endpoint drops `user_variables`, and drops `document` URLs on the first turn.** api-server's `stream.ts` doesn't forward them; confirmed by a probe on 2026-10-22, where the tool never received `probe_uv`. To test `user_variables`, use the autonomous test below.
- **Each event:** `{"workflow_id", "response": {"query": "<agent reply>", "image", "audio", "video"}, "status": "waiting_for_input" | "completed" | "continue_without_user_input", "requires_input", "error", "approval_request"}`
- **End of stream:** `{"status": "complete"}`.

`kit/chat.py` wraps it, and `kit/phinite.py` `Chat.send()` returns `{reply, status, errors, seconds, events}`.

## Autonomous test runs (verified 2026-10-22)

1. Start a run:
   ```json
   POST /testing-flows/test_autonomous/start?workspaceid=WS
   {"flow_id", "flow_version": "0", "env": "development", "workspaceid": WS, "user_variables": {...}, "message", "image": [], "audio": [], "video": [], "document": []}
   ```
   It returns `{workflow_id, status: "pending"}`.
2. Poll `GET /testing-flows/test_autonomous/status/{workflow_id}?workspaceid=WS` until it ends. The response is `{status: "completed" | …, response: <all session variables>, logs, requires_input, error}`.

`user_variables` reach param-less tools here. The probe tool saw `probe_id` with `conversation_history` and `workflow_id`. For builds: `/testing-build/test_autonomous/start` + `/status/{workflow_id}`.

## Run logs (verified 2026-10-22)

- **`GET /logs-metadata/details?session_id=<workflow_id>&workspace_id=WS`** returns `{success, data: [...]}`. Each entry is `{timestamp_ms, time, level, node_id, message, status}`. The levels are:
  - `variable`: `name = value`
  - `tool_call`
  - `tool_output`: the tool's output JSON; `node_id` is the tool name
  - `llm_input`, `llm_output`
  - `info`
  This is the API behind the session-log export, and the plugin's `get_logs` reads it.
- **`GET /testing/logs/snapshot?id=<workflow_id>&limit=N`** returns `{response: [...entries], status, cursor}`, the live view.
- **`POST /testing/logs` returns 404.** It's still listed in Swagger, but is gone in code and on prod.

## Builds, triggers and channels

- **Build** (one flow version + pinned tool versions + environment assignments):
  1. `GET /agent-build/flow-dependencies?workspaceid&flowid&version` returns `{tools: [{tool_id, tool_name, version, version_notes}], rags, mcps}`. Each tool's `version` is its **latest** one; it is 0 if never published, so publish first.
  2. `POST /agent-build {workspaceid, flowid, flow_version, tools, rags, mcps, environment: ["development"], description}`. If `flow_version` is omitted, the server publishes the draft.
  3. `PUT /agent-build/{id} {"environment": "development"}`: a string assigns the build exclusively. `production` needs an earlier dev or uat assignment.
  4. `GET /agent-build?workspaceid&flowid` lists builds. The shapes come from a UI-made build (OCbV9yF) and the code; the kit hasn't created one yet.
- **Integration hubs:** `trigger_auto` (autonomous trigger), `trigger_conv` (conversational trigger: hands off to a channel via `funnelIntegrationid`) and `chat_api_001` (Chat API). List them with `GET /integration-hub?subCategory=trigger`.
- **Creating integrations:** the UI posts to **`POST /integration_V2?workspaceid=WS`**. Captured from the UI on 2026-10-22, for a Chat API channel and a Background Task trigger. Plain `/integration` also accepts the call on prod. Send the full UI body shown below in both cases.
- **Trigger:**
  - `POST /integration_V2?workspaceid=WS {workspaceid, integrationhubid: "trigger_auto", type: "autonomous-trigger", subType: "autonomous", category: "trigger", description: "<name>", flowid, emailFilters: [], encrypted: false, triggerConfig: {triggerType: "autonomous", workflowType: "API" | "Background Task" | "Cron Job", cronSchedule, cronSchedules: {development, uat, production}, funnelIntegrationid: ""}}`. Shapes come from UI-made triggers, e.g. jVbetVVRM "Agency Review" in YGG93YE.
  - **Send `type`, `subType` and `category` yourself.** Prod doesn't derive them from the hub (newer dev code does). The trigger lookup `GET /trigger/{integrationid}/{env}` filters on `category: "trigger"`, so without it the lookup always answers 404 "We don't have any build for this trigger in this env". ai-core then fails with `'NoneType' object is not subscriptable`. Verified 2026-10-22.
  - **Calling it** goes to ai-core through the app gateway. The public base is `https://app.phinite.ai/api/v1/ai` on prod and `https://webhook.dev.phinite.ai/api/v1/ai` on dev (ai-core's `AI_CORE_BASE_HOST`). `ai-core.phinite.ai` is internal only and answers an nginx 404 from outside:
    - sync: `POST /trigger/{workspaceid}/{integrationid}/{env}`
    - background: `POST /trigger/start/{workspaceid}/{integrationid}/{env}`, then `GET /trigger/status/{workspaceid}/{workflow_id}`
  - Send `Authorization: Bearer <workspace API key>` and JSON `{"message", "user_variables"}`, or multipart with `files`.
  - **Send a `Unique-Id: <uuid>` header and keep it.** The gateway routes ai-core calls by it.
    - **Background runs:** it becomes the `workflow_id`, so the status call reaches the same server.
    - **Sync runs:** the response's `workflow_id` is a *different* id. The run's logs (`/logs-metadata/details?session_id=`) are stored under the Unique-Id you sent.
  - **Verified live 2026-10-22** on a UI-made trigger, both sync and background. `user_variables` reached the tool, and the response carried all session variables.
  - `env` is the full name: `development`, `uat` or `production`.
  - **The flow needs an agent build assigned to that env.**
- **Chat API channel (verified live 2026-10-22):**
  - Create it with `POST /integration_V2?workspaceid=WS {workspaceid, integrationhubid: "chat_api_001", type: "chat_api", subType: "chat_api", category: "channel", description, flowid, emailFilters: [], encrypted: false}`.
  - Call `POST https://app.phinite.ai/api/v1/ai/chat_api/{integrationid}/{env}` with `Authorization: Bearer <workspace API key>` and a `unique-id` header. The first turn opens with "hi", and `user_variables` aren't accepted.
  - Continue with `POST …/api/v1/ai/chat_api/{session_id}` and `{message}`. The reply is newline-delimited JSON.
  - It needs a build of the flow assigned to that env.
- **Workspace API key:** `POST /api-keys {workspaceid, name, expiry (ISO, ≤ 1 year)}`. It's checked by ai-core for triggers and the Chat API, and can't call most api-server routes.
  - **The response is the workspace's whole key list,** not the new key. Pick the newest record with your `name`.
  - `GET /api-keys/{workspaceid}` lists the keys with their values, masked for the QA role.
- **Builds (verified live 2026-10-22):** `POST /agent-build` + `PUT /agent-build/{id} {"environment": "development"}` worked. The plugin then reuses a build that pins the same flow and tool versions.

## Knowledge bases (RAG datasources, verified 2026-10-23)

Prod's gateway is picky about spelling: knowledge bases live under **`/datasource`** (lower case) and their files
under **`/dataSourceItem`** (camel case). Other spellings answer a plain-text `404 page not found`.

| Action | Call |
|---|---|
| List | `GET /datasource/{workspaceid}/live` → `[{datasourceid, name, chunkSize: 800, chunkOverlap: 100, collectionCount, itemStatus}]` (also `GET /datasource_V2?workspaceid=`, paginated) |
| Details + files | `GET /datasource?datasourceid=ID` → `{details, collections: [{datasourceitemid, name, type, size, status: "Completed", ready: true, …}]}` |
| Create | `POST /datasource {"userid", "workspaceid", "name"}`; `userid` is the `id` claim of your token |
| Upload a file | 1. `POST /dataSourceItem/upload-url {userid, workspaceid, datasourceid, name, filename, contentType, size}` → `{uploadUrl, objectKey, datasourceitemid, headers}`. 2. `PUT uploadUrl` with the bytes and those headers (signed storage URL). 3. `POST /dataSourceItem {userid, workspaceid, datasourceid, name, filename, contentType, size, objectKey, datasourceitemid}` registers it and starts indexing |
| Indexing status | `GET /dataSourceItem/status/{datasourceitemid}` → `{status: "Processing", message: "Processing chunk 1 of 1"}` … `{status: "Completed", ready: true}` (a small file took ~10 s) |
| Formats | PDF, DOCX, XLSX, PPTX, TXT, CSV, HTML, MD, JSON, XML, PNG, JPG, TIFF |

**Attach to an agent:** `details.datasource_ids: ["<datasourceid>", …]`, with `top_k` (3) and `threshold` (0.2). The
agent then has **RAGTool**; its prompt must say when to search ("search the knowledge base with RAGTool first and
answer only from it"). *Verified:* an agent answered "BLUE-HERON-42" and "4 business hours" from uploaded files,
and the log showed `RAGTool` with the matching chunk.

## Env variables

- `GET /envEncrypt/flow-gen-env/{ws}` returns names and ids only.
- `POST /envEncrypt/ {workspaceid, name, type: "Custom", dataType: "string", dev, uat, prod}` creates a variable; values are encrypted in Vault.
- **`PUT /envEncrypt/{id}` replaces the whole record.** Every value you don't send becomes "".
- `GET /envEncrypt/{id}?env=dev|uat|prod` returns one decrypted value.
- **Every tool receives every workspace variable** for the run's env (development uses `dev`, uat `uat`, production `prod`) as `env_variables`.

## Triggering a graph from a tool (graph-to-graph)

Phinite has a trigger API for graphs. The payload is `{"message": "...", "user_variables": {"key": "value"}}`, and `user_variables` become **session variables** in the triggered graph: tool `inputs` plus agent input variables.

- The endpoint is configured by the user. In the tool, keep it in a constant or env variable, e.g. `AGENCY_REVIEW_TRIGGER_URL`. Example: `sba-phase0/tools/Small_Business_Assistant/trigger_agency_review.py`.
- **The call needs `Authorization: Bearer <workspace API key>`,** read from an env variable such as `PHINITE_TRIGGER_API_KEY`. Without it the trigger answers 401. The URL format and background variant are in [Builds, triggers and channels](#builds-triggers-and-channels).
- **Without the endpoint:** reproduce a trigger in tests with the chat API plus `user_variables`. It's the same effect: `kit/chat.py ... --vars application_id=X`.

## Files in chat

- **What the user reported:** the Studio upload puts a file URL into a capture variable whose description says it holds file links, e.g. `uploaded_file_url`.
- **What we verified:** through the API, `"document": [url]` reached **neither the model nor the tools**.
  - **The reason (code):** `/stream/process_query` drops documents on the first turn.
  - **Later turns:** follow-ups forward them, but ai-core shows them to the model only if its `inputType` lists `document`/`file`. Tools see them only inside `conversation_history`.
- **Upload a file to get a URL:** `POST /common-file-upload/integration`, multipart field `file`, returns `publicUrl`. The route comes from the code; not exercised yet.
- **Design rule:** tools take file links from upload-like capture variables **and** from links pasted in `conversation_history` (`_file_links()` in `kit/tool_common.py`).

## Tool runtime (verified)

- **Available:** `psycopg2`, `requests`, `httpx`, `pypdf`, `pdfplumber`, `pdfminer`, `reportlab`, `PIL`, `openpyxl`
- **Not available:** `fitz`/PyMuPDF, `pytesseract`, `python-docx`, `PyPDF2`
- **Network:** outbound HTTPS works (Twilio, GCS downloads).
