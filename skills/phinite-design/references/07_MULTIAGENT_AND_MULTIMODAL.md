# 07 · Multi-agent architecture and multimodal agents

How to shape any use case into Phinite agents: how many, who does what, how they hand over, and which model each
one uses for text, images, video, audio and documents. Everything marked *verified* was run on app.phinite.ai on
2026-10-22/23 (plugin tests `tests/smoke_mcp.py --multimodal`); the routing rules come from ai-core's code.

## 1. One agent or several?

Start with **one master agent plus tools**. Add agents only when one of these is true:

| Signal | Shape |
|---|---|
| The prompt keeps growing because the agent does unrelated jobs (billing *and* tech support *and* sales) | **Router + specialists**: one master works out the intent, labelled edges send the run to a specialist master |
| The work has phases with different goals or rules (collect → check → decide → report) | **Pipeline**: one master per phase; captures carry the results forward |
| One step needs a different skill or model (read a PDF, look at a photo, write a long letter, make an image) | **Child agent** under the master that needs it |
| A person must review or approve before the rest happens | Two graphs: a **conversational** one for the person, an **autonomous** one started by a trigger |
| Long, independent jobs run without anyone watching | An **autonomous** graph behind a trigger (API, background or cron) |

Signs you split too far: agents that only pass text along, edges nobody can label clearly, or two agents with
the same tools. Merge them back.

Keep every prompt to one job: role (1–2 lines), numbered steps with explicit stops, rules. Put facts, rules and
side effects in tools; pass data through capture and input variables instead of pasting it into prompts.

## 2. How agents hand over (from ai-core's code)

- **Masters** run in the order the edges allow. A master ends its turn with **FinishTool** (hand over) or
  **FlowEndTool** (stop the whole run).
- **One outgoing edge:** the run follows it.
- **Several outgoing edges (a branch point):** ai-core's router compares the master's FinishTool result with each
  edge **label** (or the target agent's name if a label is empty) and picks one; it may also pick "end" when an
  end edge exists. So labels are routing criteria:
  - say **when** to take the branch: "The customer asks about an invoice, a payment or a refund";
  - make the branches mutually exclusive, and cover the likely cases;
  - have the branching master's prompt end with "call FinishTool with a one-line summary of the request" so the
    router has something to compare.
- **start** connects to exactly **one** master; branch from that master (the platform's own builder enforces this).
- Every master needs an outgoing edge (to another master or to end) and must be reachable from start.
- **Children** belong to exactly one master and connect only to it (child → parent, two-way). The master calls a
  child like a tool, using the child's `llm_tool_description`. A child returns its answer to the master, or stores
  it in a capture variable with **StoreVariableTool** for later tools and agents.

*Verified:* a router master with two labelled branches sent "create an image of a red bicycle…" to the image branch
and "What is the capital of France?" to the text branch.

## 3. What each agent can work on

Each agent's model block has a `resource` (what it works on) and an `operation`:

| | analysis | generation |
|---|---|---|
| **Master** | text, image, video, audio, document | not allowed: put generation in a child |
| **Child** | text, image, video, audio, document | text, image, video (no audio or document generation) |

- **Media to a master** (*verified*): an autonomous master with `resource: image` and an image-capable model
  described the image attached to the run.
- **Media to a child** (*verified*): a text master (gpt-5.2) asked its `resource: document` child (Gemini) to read
  the PDF attached to the run; the child read it and stored vendor and total with StoreVariableTool. The child gets
  the run's attachments even when the master's model can't read that file type.
- **Generation children** (*verified* for image): an image or video generation child gets **no tools** (so no
  StoreVariableTool). It returns public file URLs (`storage.googleapis.com/phinite-public/<org>/…png`) to its
  master, which can show them (`![…](url)`) or pass them to a tool. Give it a one-job prompt; the master writes the
  detailed description.

## 4. Picking the model for each agent

The UI's model picker reads Phinite's model catalog; the API is
`GET /models_V2?modelType=<text|image|video|audio|document>&operation=<analysis|generate>` (prod; newer servers:
`/models`). In the plugin: **`list_models(resource, operation, tool_calling)`**. Each model lists `inputType`,
`outputType` and `toolCallSupport`. On 2026-10-23 the catalog had 92 models:

| Task | Examples (prod, 2026-10-23) |
|---|---|
| Text analysis / generation (82) | gpt-5.2, gpt-5.4, gpt-4.1, claude-sonnet-4-6@default, gemini-3.1-pro-preview, Kimi-K2.5 |
| Image analysis (31) | gpt-5.2, claude-sonnet-4-6@default, gemini-2.5-flash, Qwen3-VL |
| Image generation (5) | gemini-2.5-flash-image, gemini-3-pro-image, gemini-3.1-flash-image, luma-uni-1.1 |
| Video analysis (6) / generation (3) | gemini-2.5-flash, gemini-3.1-pro-preview / veo-3.1-fast-generate-001, veo-3.1-generate-001 |
| Audio analysis (7) | gemini-2.5-flash, gemini-3.1-pro-preview |
| Document analysis (7) | gemini-2.5-flash, gemini-2.5-pro, gemini-3.1-pro-preview |

Rules:
- **Masters need tool calling** (they call FinishTool and tools). 22 catalog models have none; ai-core then falls
  back to prompt-parsed tool calls, which is less reliable. `list_models(..., tool_calling=true)`.
- **Analysis:** the model's `inputType` must include the resource and its `outputType` text. **Generation:** its
  `outputType` must include the resource.
- A child that stores results (capture variables) or calls tools also needs tool calling.
- The plugin checks all of this when it builds a graph and refuses a mismatch, e.g. "agent 'image-gen' generates
  image, but gpt-5.2 … doesn't".
- Model block shapes the UI saves: Phinite-hosted `{"modelName", "resource", "operation", "envencryptid": null,
  "developMode": "phinite"}` (+ optional `model_config`: temperature, top_p, max_tokens, reasoning_effort,
  thinking_level), the older `{"modelName", "apiKeyName": "Phinite Api", …}`, and BYOM
  `{"modelName", "compatibleApi", "modelLabel", "byomid", "developMode": "byom"}` with `provider: "byom"`.

## 5. Getting media into a run

| Entry point | How | Notes |
|---|---|---|
| Studio test chat (`/stream/process_query`) | `image` / `audio` / `video` / `document` URL lists | **Dropped on the first turn** (*verified*: the agent saw no image), sent on follow-ups. Start the chat, then attach. |
| Autonomous test (`/testing-flows/test_autonomous/start`) | same URL lists on the start call | *Verified* for image and PDF |
| Trigger (`/api/v1/ai/trigger/...`) | multipart `files` (with `message`, `user_variables` as form fields) | Phinite uploads them and passes them to the run |
| Chat API (`/api/v1/ai/chat_api/...`) | JSON `image` / `audio` / `video` / `document` URL lists, or multipart files | |
| Files you have locally | `POST /common-file-upload/integration` (multipart `file`) → public URL | the plugin uploads local paths for you |

Tools never receive the files themselves. They see the URLs in `conversation_history` and in any capture whose
description holds file links; `_file_links()` collects both, `_pdf_pages()` reads PDFs (pypdf/pdfplumber).

## 6. Knowledge bases (RAG)

Use a knowledge base when an agent must answer from **documents** (policies, manuals, FAQs, contracts, product
sheets) that are too long for a prompt and change separately from the graph. Use a **tool** instead for live data
(orders, balances, availability) and for anything with rules or side effects.

- A knowledge base is a Phinite datasource: files are chunked (800 characters, 100 overlap by default) and indexed;
  upload any of PDF, DOCX, XLSX, PPTX, TXT, CSV, HTML, MD, JSON, XML, PNG, JPG, TIFF.
- Attach it per agent (`"knowledge": ["Store FAQ"]`, optional `top_k` / `threshold`). Several agents can share one;
  give each specialist only the knowledge it needs.
- The agent searches with **RAGTool**; say in its prompt when to search and to answer only from the results.
- Image/video generation children have no tools, so they can't search knowledge bases.
- With the plugin: `add_knowledge_files(knowledge_base, paths)` (files or folders; waits for indexing; skips names
  already there), or declare them in `graph_spec.py` (`KNOWLEDGE = {"Store FAQ": ["knowledge/"]}`) so
  `deploy_project` uploads them before deploying the graphs.

## 7. Patterns, as graph specs

**Single agent with tools** (most assistants):
```python
"masters": [{"id": "assistant", "name": "Order Assistant", "prompt": "1_Assistant.md",
             "tools": ["find_order", "update_address"],
             "capture": {"order_id": "Order number the customer gives"}}],
"edges": [("start", "assistant", "customer starts chat"), ("assistant", "end", "done")]
```

**Router + specialists** (different jobs, tools or models per intent):
```python
"masters": [{"id": "router", "name": "Front Desk", "prompt": "0_Router.md"},
            {"id": "billing", "name": "Billing Agent", "tools": ["get_invoice", "issue_refund"], "prompt": "1_Billing.md"},
            {"id": "support", "name": "Support Agent", "tools": ["search_kb", "open_ticket"], "prompt": "2_Support.md"}],
"edges": [("start", "router", "customer starts chat"),
          ("router", "billing", "The customer asks about an invoice, a payment or a refund"),
          ("router", "support", "The customer reports a problem with the product or service"),
          ("billing", "end", "billing request handled"), ("support", "end", "support request handled")]
```

**Pipeline** (autonomous back office):
```python
"edges": [("start", "intake", "run starts"), ("intake", "review", "documents collected"),
          ("review", "report", "review complete"), ("report", "end", "report delivered")]
```

**Master + multimodal children** (one specialised job each):
```python
"masters": [{"id": "claims", "name": "Claims Handler", "model": "phinite", "tools": ["save_claim"], ...}],
"children": [
  {"id": "photo-check", "parent": "claims", "name": "Damage Photo Checker", "resource": "image",
   "operation": "analysis", "model": "gemini-2.5-flash", "capture": {"damage_json": "Damage found in the photos"},
   "llm_tool_description": "Looks at the attached photos and stores the visible damage as JSON."},
  {"id": "letter", "parent": "claims", "name": "Letter Writer", "resource": "text", "operation": "generation",
   "model": "phinite", "llm_tool_description": "Writes the claim decision letter from the facts it is given."}]
```

## 8. Checklist before deploying a design

- [ ] Could one master with tools do it? If yes, stop there.
- [ ] Each agent has one job and a short prompt; rules live in tools.
- [ ] start → exactly one master; every master reachable and with an outgoing edge.
- [ ] Every branch label says when to take it; branches don't overlap.
- [ ] Every agent's model fits its resource and operation (`list_models`); masters have tool calling.
- [ ] Generation children have no tools or captures; their master handles the returned URLs.
- [ ] Media enters the way the entry point supports (not on the first test-chat turn).
- [ ] Agents that answer from documents have a knowledge base and a prompt that says when to use RAGTool.
- [ ] Every trigger or channel's flow has a build assigned to the environment it is called in.
