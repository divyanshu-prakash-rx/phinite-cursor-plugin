# 02 · Designing agent graphs

## Building blocks

| Block | Use it for |
|---|---|
| **Master agent** (`task agent`) | The orchestrator of a graph. It talks to the user (chat graphs), calls tools, delegates to children, and ends with FinishTool (hand over to the next master) or FlowEndTool (end the run). |
| **Child agent** (`child agent`) | One specialised LLM job for its master: verify extracted documents, draft a letter, write a summary. It stores its result with **StoreVariableTool** into its capture variable, and later tools receive that variable. |
| **Tool** | Python `main(inputs, env_variables)`. All facts, rules, DB writes and side effects (SMS, email, triggers) happen here, never in the prompt. |
| **Edges** | `start → master → … → end`. Master → master edges are labelled; the FinishTool summary routes. Each child connects only to its parent. |

**Graph types:**
- **conversational:** a person chats with it. Examples: applicant assistant, officer desk.
- **autonomous:** started by a trigger or message with `user_variables`; runs to the end with no human. Examples: back-office review.

**Size:** prefer few graphs, split by *who* is served; inside a graph, start with one master and add masters or children only for the reasons in [07 § 1](07_MULTIAGENT_AND_MULTIMODAL.md). Branch points route by edge label ([07 § 2](07_MULTIAGENT_AND_MULTIMODAL.md)). Example from the SBA builds: In the SBA Phase 0 the split was one applicant chat, one autonomous agency review, and one officer chat in Teams. One master per graph is usually enough. Use 2 masters only for a real hand-off, like package-builder → submission.

## Variables: the most important section

Verified by logging every tool's `inputs`:

1. **Capture variables** (on the master) are filled automatically by Phinite from the conversation or trigger message, using each `llmDescription`. **Don't mention them in the prompt.** Write precise descriptions, e.g. `"loan_amount": "Amount requested in US dollars (a number)"`.
2. A tool with **no params** receives in `inputs`:
   - every *non-empty* capture of its master
   - every `capture_variables` returned earlier by tools or child agents in the session
   - `conversation_history` and `workflow_id`
   - in **autonomous** graphs, the `user_variables` sent by the trigger.
3. A tool **with params** receives **only the LLM's arguments**, with no captures at all. **So every tool has `params: []`.** Values the agent itself decides (a summary, a yes/no) become captures too, or the tool builds them from the DB.
4. Captures arrive as **strings** ("150000", "Lake", "true"). Tools parse leniently with `_num`, `_bool`, `_str`.
5. Capture extraction **drops non-ASCII letters**: "María Álvarez" becomes "Mara lvarez". `_str()` repairs the value from `conversation_history`.
6. In a **conversational** graph, `user_variables` sent with the first message did **not** reach the tools (tested with two key names). Put needed ids in the message text instead ("I got your text about application SGP-2026-00001"), and have the SMS include the id.
7. **Ids that appear only in tool output** may not be captured in the same turn. Tools should resolve fall-backs from the DB, e.g. by business name, or "the only pending case".
8. **Tool-returned captures flow to later tools automatically.** For example, `start_application` returns `application_id` and `screen_borrower` gets it.

## Prompts

- **Shape:** Role (1–2 lines), then numbered **Steps** in strict order, then **Rules**. Keep it short. Never list fields to pass to tools.
- **Spell out the order and the stops.** Write "As soon as you have X, call `tool`; reply; stop and wait." Gemma once demanded a phone number before every other step until the order was explicit.
- **"Whenever the user uploads or shares files, call `add_documents` in that same turn."** Without this line the model collected everything and checked nothing.
- **Honesty rule, always:** "Never report an action unless the tool returned ok:true. When a tool returns ok:false, follow its `next`."
- **Tools return `ok`, `error` and `next`.** `next` is an instruction the agent follows, e.g. "Ask the applicant for: ein, naics".
- **Humans approve:** "read back the decision and ask *Shall I record this?*; only after an explicit yes…". The tool also refuses unless the `confirmed` capture is `true`.
- **Child prompts:** say exactly what JSON to output, when to use high severity, and "Store it in `<var>` with **StoreVariableTool**". Tell it what not to write (dates, numbered lists) when the tool appends official text.
- **Citations:** have tools return `link` fields (`url#page=N`) and tell the agent to cite with markdown links taken *only* from tool output.

## Guardrails belong in tools, not prompts

- **State checks happen in the DB.** For example: no submission without approval, no recommend-approve while deficiencies are open, integrity holds block letters. The prompt can be wrong; the tool refuses.
- **A refused call (`ok:false`) rolls back,** so nothing is half-written. `_run_tool` in `kit/tool_common.py` handles this.
- **"AI finds, rules decide."** An AI finding on a topic a deterministic check already passed is kept as a note, not a blocker. A 2% revenue estimate gap must not block approval.
- **No tipping off.** Integrity findings never appear in anything sent to applicants or lenders; filter the text in tools.

## Models

Pick each agent's model for its task with the plugin's `list_models(resource, operation, tool_calling)` (Phinite's model catalog: [07 § 4](07_MULTIAGENT_AND_MULTIMODAL.md)). Masters need tool calling; media analysis and image/video generation need a model whose `inputType`/`outputType` covers it. What we saw in past builds:

| Model | Result |
|---|---|
| **Gemma_CIQ** (`gemma-4-31B`) | All Phase 0 graphs, including the child verifier, ran correctly once prompts gave an explicit order. **Default for CIQ.** |
| **Phinite gpt-5.2** | Most reliable tool use; it ran all Phase 1 graphs first time. |
| **Mistral_CIQ** (`Ministral-8B`) | It skipped required tool calls and claimed success: "I've shared your information" with no referral created. Avoid it for tool-heavy masters. |

Switch models at deploy time: `kit/deploy.py --model <key>`. You can also set `"model": "<key>"` on one agent in `graph_spec.py`.

## Patterns that worked

- **Instant vs. deep checks.** An instant check in chat uses metadata only (file name, type, year). The deep check runs in an autonomous graph: a tool extracts text page by page, a child verifies it, and tools run the rules.
- **Deficiency loop.** The autonomous review creates an info request and sends an SMS that includes the id. The applicant returns to the chat and the agent calls `get_my_application`. Then `confirm_info_provided`, then trigger review again (pass 2).
- **One-page summary with evidence.** Every check carries `{passed, detail, evidence: "file p.N", citation}`. The officer's Q&A tool returns facts, checks and passages with `url#page=N` links.
- **Audit:** `audit_log` holds every state change, `tool_call_log` every tool call, and an audit PDF (reportlab) is stored in the DB on the final decision.
