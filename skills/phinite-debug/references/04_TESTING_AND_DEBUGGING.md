# 04 · Testing and debugging

There are four levels. Always run them in this order, and **reset the DB before every live run**: ids assume a fresh state.

## 1. Local smoke test: tools only, no LLM (`demo/smoke_test.py`)

- **What it does:** imports each built tool, calls `main(inputs, env)` against the real DB, and asserts the outcome.
- **Shape of inputs:** captures as strings, plus `conversation_history=[{"role": "user", "message": "{'message': '…'}"}]`.
- **What to cover:** the happy path, **every refusal** (`expect_ok=False`), idempotency (same call twice), and the full multi-graph story in order.
- **Speed:** each call opens a remote DB connection, about 1–2 s, so 50 calls take about 2 minutes. Run it in the background or use `python -u` so the log flushes.

## 2. Live single tool in Phinite (`kit/test_tool.py`)

Runs one deployed tool in the real Phinite runtime, with the inputs you give and the env variables of the chosen workspace environment. Use it after deploying tools and before chatting with a graph. It catches what a local run can't: a package missing from the runtime, an env variable name or environment that differs, no network access from Phinite.

```bash
python kit/test_tool.py --project ../my-uc start_case --inputs '{"customer_name": "Maria Gonzalez", "request": "loan help"}'
python kit/test_tool.py --project ../my-uc post_slack_update --inputs-file ../my-uc/demo/sample_inputs/dry_run.json --out result.json
python kit/test_tool.py --project ../my-uc collect_github_activity --inputs '{}' --env production
```

- **Inputs:** send only `inputs`; the env variables come from `--env` (default `development`). Shape the inputs like a graph run: captures as strings, plus `conversation_history` if the tool reads it.
- **Output:** it prints `output` (what the calling agent would see) and `capture_variables` (what a graph would store as session variables). `--out` saves the full result.
- **Side effects are real.** Keep sample inputs in `demo/sample_inputs/`, including a dry-run input for every tool that posts or sends.
- **Where to get realistic inputs:** from a real run. The exported session log (`play_c_<workflow_id>.json`) has every tool call's parameters.

## 3. Live single graph (`kit/chat.py`)

```bash
python kit/chat.py --project ../my-uc "Assistant" "Hi, I own a bakery…" "We have 9 employees…"
python kit/chat.py --project ../my-uc "Review" --vars application_id=SGP-2026-00001 "Review application SGP-2026-00001"
python demo/simulate.py log 10        # what each tool actually received, and ok/error
```

Read the agent's replies **and** the tool log. A fluent reply can hide a tool that never ran.

## 4. Live end-to-end (`demo/live_e2e.py`)

This plays the whole story through the deployed graphs (chat turns, simulated human steps, trigger-equivalent calls) and checks the DB after each step with ✔/✘. Copy `../sba-phase0/demo/live_e2e.py` as the pattern. It ends by printing the total tool calls and every refused call.

## With the Claude plugin

| Kit step | Plugin tool |
|---|---|
| `kit/test_tool.py` | `test_tool(tool, inputs, version="latest")` |
| `kit/chat.py` | `chat(flow, message, session)` for conversational graphs |
| — | `run_autonomous(flow, user_variables)` for autonomous graphs; it really passes `user_variables` |
| Session-log export (`play_c_<workflow_id>.json`) | `get_logs(workflow_id)`: the same Loki entries (variables, tool calls with outputs, LLM I/O on request), read through `GET /logs-metadata/details` |
| `kit/deploy.py` | `deploy_project(path)`: also publishes changed tools, so tests never run stale tool code |

## Debugging playbook

| Symptom | Look at | Usual cause, and the fix |
|---|---|---|
| Agent says it did X, but nothing in the DB | `tool_call_log` (no row for that tool) | The model skipped the call. Add an explicit step order and the honesty rule; try a stronger model (Mistral 8B did this) |
| Tool called with `inputs: {}` | `tool_call_log.inputs` | The tool has **params**. Set `params: []` and move the values to master captures |
| A value missing from `inputs` | `tool_call_log.inputs` | No capture with that name or description, or the value was only in tool output that same turn. Add a capture, or a DB fallback in the tool |
| Tool loops (same call many times) | `tool_call_log` | Its `next` asks for something the agent can't supply. Make `next` actionable, or make the tool find it |
| "María" stored as "Mara" | `tool_call_log.inputs` | Capture extraction drops non-ASCII. `_str` restores it from `conversation_history` |
| `user_variables` ignored | `tool_call_log.inputs` | A conversational graph. Put the id in the message text |
| Uploaded file not seen | `tool_call_log.inputs` | Name an upload capture (`uploaded_file_url`) **and** accept pasted links (`_file_links`) |
| Child output missing in a tool | the child capture name vs. what the tool reads | The child prompt must say "Store it in `<var>` with StoreVariableTool". The tool should fall back to building the text from the DB |
| Agent asks for things in the wrong order | the reply | Write explicit "one step at a time" steps with "Stop and wait" |
| AI flags trivial differences as blockers | review summary | Set a tolerance in the child prompt **and** downgrade AI findings on topics a rule check passed |
| 401/403 from a kit script | | Session expired: `python kit/set_auth.py` |
| Graph changes not visible | | You deployed `--only tools`. Prompt and capture changes need `--only graphs` |
| Tool change not visible in a flow test | `get_tool(tool, "latest")` vs the draft | The tool was published once, and the edit is only in the draft. Flow tests run the latest **published** version, so publish it (`publish_tool` or `deploy_project`) |
| HTML "403 Forbidden" from a script | the User-Agent | The edge firewall blocks UAs containing `python-requests` on some routes. Send your own UA |
| Tool works locally but fails in Phinite | `kit/test_tool.py` with the same inputs | A package missing from the runtime, a different env variable name or environment (`--env`), or no network access |

**Probe technique**, for unknown platform behaviour such as "what does a tool receive when …?": deploy a tiny probe tool that writes its full `inputs` and `importlib` checks into the DB, attach it to a throwaway graph, and chat with it. That's how every rule in 02 was established. The probes `sba_probe_tool`, `sba_probe_flow` and `sba_probe_chat` already exist in the workspace for reuse; they can't be deleted.
