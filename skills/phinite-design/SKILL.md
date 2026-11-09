---
name: phinite-design
description: How to design any agentic use case on Phinite — one agent or several (router, pipeline, children), labelled edges for branching, multimodal masters and children (image, video, audio, document analysis; text, image, video generation), knowledge bases (RAG) from the user's files, picking the right model per agent, capture variables, param-less tools, prompts and guardrails. Use before creating or changing any Phinite graph, tool or graph_spec.py.
---
# Designing Phinite agent graphs

Read the references before designing: `references/07_MULTIAGENT_AND_MULTIMODAL.md` (architecture, branching,
multimodal, models), `references/02_GRAPH_DESIGN.md` (variables, prompts, guardrails) and
`references/03_PROJECT_AND_TOOLS.md` (project layout, graph_spec.py, tool helpers). They come from the playbook
and name its `kit/` scripts, which the plugin doesn't ship: use the `phinite` MCP tools and the `phinite-project`
script instead. The rules that matter most:

**1. Architecture: as few agents as the job allows**
- Start with **one master + tools**. Most assistants and back-office jobs need nothing more.
- Add a **specialist master** only for a different job, phase or rule set; join masters with edges.
  - **Router + specialists:** start → one router master → labelled branches. Use it when intents need different
    tools, prompts or models.
  - **Pipeline:** intake → work → report. Use it for autonomous back-office runs.
- Add a **child agent** for one specialised LLM job a master delegates: read a PDF, check photos, write a letter,
  generate an image or a video. A child connects only to its parent.
- **Two graphs:** a person talks to a conversational graph, and long or reviewed work runs in an autonomous graph
  started by a trigger.
- **Each agent gets one job** and a short prompt (role → numbered steps with stops → rules). If a prompt grows, the
  agent probably does two jobs. Facts, rules and side effects belong in tools; data moves through captures, not
  prompts.

**2. Branching = edge labels**
- `start` connects to exactly **one** master. Every master needs an outgoing edge and must be reachable.
- With several outgoing edges, Phinite's router compares the master's **FinishTool result** with each **edge
  label** and picks the branch. So:
  - Labels say *when* to go there: "The customer asks about a refund", not "done".
  - Branches don't overlap.
  - The branching master ends with "call FinishTool with a one-line summary of the request".
- `set_flow_graph` and `deploy_project` reject unlabelled branches and warn about vague labels.

**3. Multimodal agents** (`resource` + `operation` on each agent)

| Agent | Analysis | Generation |
|---|---|---|
| Master | text, image, video, audio, document | not allowed: give generation to a child |
| Child | text, image, video, audio, document | text, image, video |

- Children see the run's attached files, even when their master's model can't read that type.
- Image and video generation children get **no tools** and can't store variables. They return public file URLs
  to their master, which shows them or passes them on.
- **Getting files in:**
  - Test chat drops files on the **first** turn, so send them on a follow-up.
  - `run_autonomous` takes them on the first call; triggers take multipart files; the Chat API takes URL lists.
  - `chat`, `run_autonomous` and `chat_api` take file URLs. For local files, use `upload_file` and the
    `phinite-project` skill's `send` command, which return the URLs.

**4. The right model for each agent**
- **Find candidates:** `list_models(resource, operation, tool_calling=true)` reads Phinite's model catalog (the
  UI's picker). Use the returned `ref` as the agent's `model`. Also valid: `phinite` (gpt-5.2: text + image input,
  tool calling), or a BYOM label.
- **Masters need tool calling:** they call FinishTool and tools.
- **Analysis models:** `inputType` must cover the resource.
- **Generation models:** `outputType` must be that resource. Examples: gemini-2.5-flash-image for images, veo-3.1-*
  for video.
- **Children that store results or call tools** also need tool calling.
- **Built-in check:** the plugin refuses any graph whose model can't do its agent's task.

**5. Variables** (verified by probes; the most common source of bugs)
- **Master captures:** Phinite fills each master capture variable from the conversation or trigger message, using
  its description. Write precise descriptions, and never mention captures in the prompt.
- **What a tool receives:** tools take **no params**. A param-less tool gets:
  - every non-empty capture of its master;
  - captures returned by earlier tools and children;
  - `conversation_history` and `workflow_id`;
  - in **autonomous** graphs, the trigger's `user_variables`.

  A tool *with* params receives only the LLM's arguments.
- **Captures are strings,** and they lose non-ASCII letters; `_str()` repairs them from `conversation_history`.
- **A child stores its result** in its capture variable with **StoreVariableTool**; later tools receive it.

**6. Tools**
- **Contract:** `def main(inputs, env_variables) -> {"output": {...}, "capture_variables": {...}}`. Results carry
  `ok`, `error` and `next`, where `next` is an instruction the agent can follow.
- **Guardrails live in the tool:** refuse with `ok:false`, keep calls idempotent, and never leave half-written
  state.
- **Runtime libraries:** requests, httpx, pypdf, pdfplumber, reportlab, PIL, openpyxl, psycopg2. No PyMuPDF or OCR.
- **Env variables:** every tool gets **all** of the workspace's env variables for the run's environment, and every
  use case in the workspace shares them.
  - Name a use case's own secrets with its prefix (`MYUC_SLACK_TOKEN`, not `SLACK_TOKEN`), so two use cases can't
    overwrite each other. Reuse a shared name (such as the template's `DB_*`) only when the use case really shares
    that resource.
  - Read them in tools with `env.get("NAME")` or `_env_any("NAME", ...)`, so the project script's `env-check`
    finds them.
  - Set them with `set_env_vars(names=[...])` and the steps in the `phinite-project` skill: only the names the
    tools need, never blank values, and never overwriting an existing name without asking. The values never pass
    through the chat.

**7. Knowledge bases (RAG): answering from the user's documents**
- **When:** an agent must answer from documents (manuals, policies, FAQs, contracts, product sheets) → put them
  in a knowledge base. Live data and anything with rules or side effects → a tool. Short fixed facts → the prompt.
- **Upload:** when the user gives or points to files, call `add_knowledge_files(knowledge_base)`. Then send the
  files or folders to the link it returns with the `phinite-project` skill's `send` command.
  - The upload creates the knowledge base if needed and skips names already there.
  - Then run `get_knowledge_base(knowledge_base, wait_seconds=240)` until every file is ready.
  - In a project, copy the documents into `knowledge/` and declare `KNOWLEDGE = {"<name>": ["knowledge/…"]}` in
    graph_spec.py; `deploy_project` uploads them before the graphs. Paths outside the project are refused, and
    hidden files are never uploaded.
- **Attach:** give the agent `"knowledge": ["<name>"]` (optional `top_k`, `threshold`). Its prompt must say when to
  search: "search the knowledge base with RAGTool first and answer only from what it returns".
- **Scope:** give each specialist only the knowledge it needs. Image/video generation children can't use RAG.
- **Formats:** PDF, DOCX, XLSX, PPTX, TXT, CSV, HTML, MD, JSON, XML, PNG, JPG, TIFF.

**8. Workflow with the plugin**
- **Scaffold:** the `phinite-project` skill's `new` command, with `--no-database` for API, file or media use cases,
  or `--schema <name>` when the use case keeps its own tables.
- **Build and deploy:** write `graph_spec.py`, `tools-src/` and `agent-prompts/`. Run `deploy_project` as a dry run,
  then deploy, each time running the command it returns. Then test (`phinite-debug`) and ship (`phinite-ship`).
- **Quick graph without a project:** `upsert_tool` + `set_flow_graph`.
- **Editing an existing graph, including UI-built ones:** `get_flow` returns the same spec shape; edit it and send
  it back.
