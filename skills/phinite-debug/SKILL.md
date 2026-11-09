---
name: phinite-debug
description: How to test and debug Phinite graphs and tools — test_tool, chat, run_autonomous, reading run logs (get_logs), tool_call_log, and a symptom → cause → fix table from real builds. Use when a Phinite run misbehaves, a tool gets wrong inputs, or before declaring a use case done.
---
# Testing and debugging Phinite graphs

Read `references/04_TESTING_AND_DEBUGGING.md` (test levels + the debugging table) and
`references/06_LESSONS_LEARNED.md` (every platform quirk we hit, with the fix). They come from the playbook and
name its `kit/` scripts, which the plugin doesn't ship: use the matching `phinite` MCP tool (the table in 04 maps
them), and skip any step that copies a browser cookie or token.

**Test ladder (cheapest first)**
1. Local smoke test of the tools against the DB (`demo/smoke_test.py` in the project) — no LLM.
2. `test_tool(tool, inputs)` — one deployed tool in Phinite with exact inputs (strings, as captures arrive). It
   really runs (DB writes, SMS…). No captures or conversation_history are added.
3. `chat(flow, message)` turn by turn (conversational) or `run_autonomous(flow, user_variables)` (autonomous).
4. End-to-end scenario across graphs (the project's `demo/live_e2e.py` if it has one).

**Reading a run**: `get_logs(workflow_id)` lists, in order, variables set (`variable`: `name = value`), each tool
call and its output (`tool_output`, node = tool name), and errors. Add `include_llm: true` to see the model's
inputs/outputs when the cause is the model's reasoning. Projects with a DB also have `tool_call_log` (exact inputs
Phinite passed to each tool).

**Most common causes**
- Agent claims an action but no tool ran → explicit step order + honesty rule; stronger model.
- Tool got `inputs: {}` → it has params; make it param-less and move values to master captures.
- Value missing from inputs → no capture with that name/description, or the value only appeared in a tool output
  that same turn → add a capture or a DB fallback.
- Code change not visible in tests → the tool was published before and the change is only in the draft →
  `publish_tool` (or `deploy_project`, which publishes changed tools).
- `user_variables` ignored → conversational test chat drops them; test with `run_autonomous`, or put the id in the
  message text.
- Trigger/Chat API 401 → missing or wrong workspace API key; 4xx "no build" → `create_build` for that environment.
- The run went down the wrong branch → read the branching master's FinishTool output in `get_logs`; make it summarise
  the request, and rewrite the edge labels to say when to take each branch (no overlap).
- An agent says it saw no file → in test chat, files on the first turn are dropped (send them on a follow-up); check
  the agent's model accepts that resource (`list_models`) and that the agent's `resource` is set.
- The agent ignores its documents → `get_logs` shows no `RAGTool` call: add "search the knowledge base with RAGTool
  first" to its prompt; `get_knowledge_base` shows whether each file is `ready` (still indexing or failed).
- A generated image/video is missing → generation children have no tools and return URLs to their master; the
  master must show or pass them on (they never land in a capture by themselves).
- HTML 403 from a script → User-Agent contains `python-requests` (edge firewall).

Fix → redeploy (`deploy_project`, or `upsert_tool` / `set_flow_graph`) → re-run the same test → compare logs.
