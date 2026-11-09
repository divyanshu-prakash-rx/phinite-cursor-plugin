# 06 · Lessons learned (SBA builds, Oct 2026)

Each item was hit for real and fixed. Check the list before designing.

**Platform**
1. **Tools and graphs can't be deleted through the API** (500 foreign key). Deploy matches by name and updates in place. Pick names carefully; probes stay forever.
2. **Tools with params get no captures.** Every tool is param-less (02 § Variables).
3. **`user_variables`:** they work in autonomous graphs, but not in conversational ones through the chat API.
4. **API `"document"` payload:** it didn't reach the model or the tools. Use an upload capture and accept pasted links.
5. **Capture extraction drops accents.** Repair the value from `conversation_history`.
6. **Save graphs the way Studio does** (captured 2026-10-23): PUT `{edges, blocks_content, isSaved, isPublished, workspaceid}` with each block's position and size on the block; Studio no longer sends `nodes`, and the server runs only `blocks_content` + `edges`. Always send the complete graph.
7. **Test one tool with `POST /testing/tool/conversations`** (`kit/test_tool.py`). It runs a deployed tool with exactly the `inputs` you send, plus the env variables of the environment you name (`development` by default). It is not a graph run: no captures or `conversation_history` are added. Guessed paths like `/tool/{id}/run` return 404; this is the call Studio's test panel makes.
8. **The tool runtime has pypdf, pdfplumber and reportlab,** but no PyMuPDF or OCR.

**Models**
9. **Mistral_CIQ (8B)** skipped tool calls and invented success. Gemma_CIQ and gpt-5.2 were reliable once prompts gave an explicit step order.
10. **Gemma** invented a prerequisite (a phone number before anything else) until the prompt said "Do NOT ask for a phone number yet" and "one step at a time".
11. **Child agents add their own dates and deadlines** that conflict with the official text. Tell them not to write dates, and have the tool append the official items.
12. **A child flagged a 2% revenue difference as high severity.** Add a tolerance in the prompt, and downgrade AI findings when the matching rule check passed.

**Design**
13. **Put every guardrail in the tool.** The model will occasionally try the wrong thing; the tool must refuse with a useful `next`.
14. **Roll back refused calls.** Otherwise half-written state breaks the next run.
15. **Idempotency:** creating an application, approval or card twice must return the existing one.
16. **No tipping off:** text sent to applicants or lenders is filtered for integrity words; drafted letters that mention integrity fall back to a standard letter.
17. **Generated SMS and letters must carry the reference id**, so a person returning by chat can be matched.
18. **Seed-dependent ids** (e.g. `APP-2026-00053`) only hold after a reset. Runbooks must say "reset first".
19. **The remote DB adds about 1–2 s per tool call.** Run long local tests in the background with `python -u`.
20. **zsh doesn't word-split `$VAR` commands.** In shell loops use functions, not `C="python x.py"; $C …`.

**Platform API (Claude plugin build, 2026-10-22)**
30. **Bearer works everywhere.** `Authorization: Bearer <phinite_access_token>` needs no cookie and no CSRF, for reads and writes. It's the simplest auth for scripts and the plugin.
31. **Send your own User-Agent.** `python-requests/…` gets an HTML 403 from the edge firewall on `/testing/tool/conversations`. `phinite-claude-plugin/0.1` and curl pass.
32. **Flow tests run the latest *published* tool version**, verified with the MARK_A/MARK_B probe. After the first publish, a draft-only change is invisible until you publish again. A build pins versions; a flow publish doesn't.
33. **List endpoints return one record per version** (draft + each published). Collapse them by id, or counts and lookups go wrong.
34. **BYOM `byomid` is per workspace.** Read it from `GET /byok/byom/catalogs?workspaceid=`. A graph copied to a new workspace with the old id points at nothing.
35. **Triggers and the Chat API live on ai-core,** reached through the gateway at `https://app.phinite.ai/api/v1/ai/...` (dev: `webhook.dev.phinite.ai/api/v1/ai`). `ai-core.phinite.ai` is internal only. They need a **Bearer workspace API key**, full env names, and an **agent build assigned to that env**.
36. **`POST /testing/logs` is gone.** Read run logs with `GET /logs-metadata/details?session_id=<workflow_id>`, which has every variable, tool call and tool output.
37. **The reason for lessons 3 and 4:** the Studio chat endpoint (`/stream/process_query`) drops `user_variables`, and drops `document` on the first turn, before ai-core sees them. The autonomous test endpoint passes `user_variables`.
38. **Create integrations exactly like the UI.** On prod, `POST /integration` stores only what you send, and the trigger lookup filters on `category: "trigger"`. A trigger created without `type`/`subType`/`category` exists in the list but can never run: ai-core says `'NoneType' object is not subscriptable`. Send `type: "autonomous-trigger"`, `subType: "autonomous"`, `category: "trigger"` (Chat API: `chat_api`/`chat_api`/`channel`).
39. **`POST /api-keys` answers with the whole key list** of the workspace. Take the newest record with your name; don't assume the response is the new key.
40. **Keep the `Unique-Id` you send to a trigger.** A sync trigger returns a different `workflow_id` from the one its logs are stored under: logs use the sent Unique-Id. Background runs use the Unique-Id as the `workflow_id`. Integrations made without the UI's fields are also invisible in the UI's lists, so you can't fix or delete them there.
41. **Pick models from the catalog, per task.** `GET /models_V2?modelType=&operation=` lists what the UI offers for that resource and operation, with `inputType`, `outputType` and `toolCallSupport`. A model that can't do the task fails quietly (an image "generated" by a text model is just text).
42. **The test chat drops files on the first turn** (verified: an image on turn 1 → "NO IMAGE", the same image on turn 2 → described). Start the conversation, then attach. Autonomous tests and triggers take files on the first call.
43. **Children see the run's attachments.** A text master handed an attached PDF to a document-analysis child, which read it. A master's own model only sees media its `inputType` covers.
44. **Image/video generation children have no tools.** They return public file URLs to their master; don't give them captures or tools.
45. **Branching = edge labels.** With several outgoing edges, ai-core's router compares the master's FinishTool result with the labels. "done" or empty labels route at random; write "The customer asks about a refund". start connects to one master.
46. **Knowledge bases: mind the route spelling.** On prod the gateway serves `/datasource` (lower case) and `/dataSourceItem` (camel case); `/dataSource` and `/datasourceitem` answer a plain-text 404. File upload is signed URL → PUT → register → poll status.
47. **RAG needs a prompt line.** An agent with `datasource_ids` gets RAGTool, but uses it reliably only when the prompt says when to search and to answer from the results.
48. **Every integration needs a build in its environment** (user confirmed; verified for triggers and the Chat API). Without one, the trigger lookup says "We don't have any build for this trigger in this env". The plugin now checks before `call_trigger` / `chat_api`.
49. **Fill `model_config` like Studio:** the defaults of the model's `modelConfig` schema from the catalog (gpt-5.2 → max_tokens 8192, reasoning_effort medium). The plugin does this unless a spec sets `model_config`.

**API-only use cases (GitHub → Slack daily update, `gitupdates/github-slack-daily`, Oct 2026)**
21. **No DB is fine.** Write a DB-less `tools-src/_common.py` (same `# ── shared helpers` marker, `_run(inputs, env)`, `_ok`/`_fail`, a `_run_tool` that turns every exception into `_fail`). `kit/build_tools.py` works unchanged. Copy `github-slack-daily/tools-src/_common.py` as the starting point.
22. **Where to see what the tools did.** The chat SSE stream carries only agent replies: no tool calls, no tool outputs. The session log you can export from Phinite (`play_c_<workflow_id>.json`, from Loki, kept 60 days) has everything: each tool's call parameters and output, every variable set (`activity_data = …`), and the LLM inputs and outputs. Each entry is cut at 8,000 characters. Still have the master's FlowEndTool message report the key fields (counts, `warnings`, ids of what was posted), because that is what you see without the log.
23. **Outward-facing tools get a dry run.** Use a `dry_run` capture and also match "dry run / preview / don't post" in the user turns of `conversation_history`. The tool returns the would-be message as `preview`. Every live test then runs without posting.
24. **Idempotency without a DB:** the posting tool returns a capture (`slack_posted_window`) and refuses a second post for the same window in the same run.
25. **External calls from the Phinite runtime can time out transiently** (we saw `ConnectTimeout` to api.github.com once, fine before and after). Use `timeout=(10, 30)`, retry network errors with backoff, and never let a `requests` exception escape the tool.
26. **Live test runs spend the real API quota.** Five runs scanning every branch of a busy GitHub org used up the token's 5,000/hour. Count the calls per run before testing repeatedly. Treat secondary rate limits (`Retry-After`, about 60 s) differently from a used-up quota (`X-RateLimit-Remaining: 0`). A partial scan must be visible in the output, not look like a quiet day.
27. **A large JSON capture works:** `activity_data` (a day of commits) went from a tool to the child's input variable and to the next tool. Still give the later tool a fallback (re-collect from a small `activity_window` capture) in case a capture is cut off.
28. **Workspace `9ARiQ0J` uses Phinite gpt-5.2** (`apiKeyName "Phinite Api"`, provider null). An autonomous master + child + 2 tools ran in about 90 s.
29. **A child agent's input variable goes into its prompt in full.** Run 1's summarizer received the whole `activity_data` (19.5K characters of SHAs, paths and stats) because it was declared as the child's input. Have the tool return a second, compact capture written for the LLM (`commit_digest`: only the text it needs, with a size cap) and declare only that as the child's input. Keep the full data for the tools, which cost no tokens. Also tell the master not to paste data into its request to the child.
