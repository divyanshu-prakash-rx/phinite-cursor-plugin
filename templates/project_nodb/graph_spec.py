"""What gets deployed to Phinite for this use case: models, tools, graphs. Read by the plugin's deploy_project
(or kit/deploy.py). This template needs no database; for one with Postgres use templates/project.

Design rules (playbook 02_GRAPH_DESIGN.md and 07_MULTIAGENT_AND_MULTIMODAL.md):
- Start with ONE master agent. Split into more masters only for real phases, roles or branches, and give each one
  job and a short prompt. A master with several outgoing edges is a branch point: label each edge with WHEN to take
  it (Phinite's router compares the master's result with the labels).
- A child agent does one specialised LLM job for its master: analyse text / image / video / audio / document, or
  generate text / image / video. Pick each agent's model with list_models(resource, operation); masters need
  tool calling.
- Tools take NO params ([]). They receive the master's capture variables, earlier tool and child captures,
  conversation_history and workflow_id (+ user_variables in autonomous graphs). Don't mention captures in prompts.
"""

MODELS = {}               # optional named model blocks; "phinite" (gpt-5.2) and any list_models name work as is
DEFAULT_MODEL = "phinite"

# name: (tools/<Folder>, description shown to the LLM, params (keep []), capture variables the tool RETURNS)
TOOLS = {
    "lookup_item": ("Example_Graph",
        "Looks up an item in the catalogue by name or SKU and returns its details. Returns ok:false with what "
        "to ask when nothing matches.",
        [], {"item_id": "SKU of the item the user is asking about"}),
}

# Documents agents answer from (RAG). deploy_project creates each knowledge base and uploads these files once
# (by name); give an agent "knowledge": ["<name>"] and tell it in its prompt to search with RAGTool.
KNOWLEDGE = {}            # e.g. {"Product FAQ": ["knowledge/faq.pdf", "knowledge/manuals/"]}

GRAPHS = [
    {"name": "MYUC - 1 Example Assistant", "graphType": "conversational",      # or "autonomous"
     "description": "One sentence: who it serves and what it does.",
     "masters": [{"id": "assistant", "name": "Example Assistant", "prompt": "1_Example_Master.md",
                  "tools": ["lookup_item"],
                  "capture": {"item_query": "The item name or SKU the user is asking about"},
                  "inputs": []}],      # e.g. ["order_id"] for user_variables sent by a trigger
     "children": [],
     "edges": [("start", "assistant", "user starts chat"), ("assistant", "end", "done")]},
]

# ── Other shapes: copy what you need into GRAPHS ─────────────────────────────
# Router + specialists. start connects to ONE master, which branches; labels say when to take each branch:
#   "masters": [{"id": "router", ...}, {"id": "billing", ...}, {"id": "support", ...}],
#   "edges": [("start", "router", "user starts chat"),
#             ("router", "billing", "The customer asks about an invoice, a payment or a refund"),
#             ("router", "support", "The customer reports a problem with the product"),
#             ("billing", "end", "billing question answered"), ("support", "end", "problem handled")]
#
# Pipeline (autonomous): intake → work → report, each master with one job; captures flow forward:
#   "edges": [("start", "intake", "run"), ("intake", "analyse", "inputs collected"),
#             ("analyse", "report", "analysis done"), ("report", "end", "report sent")]
#
# Multimodal children (each serves one master):
#   {"id": "doc-reader", "parent": "assistant", "name": "Document Reader", "resource": "document",
#    "operation": "analysis", "model": "gemini-2.5-flash", "prompt": "2_Example_Child.md",
#    "llm_tool_description": "Reads the attached document and returns the fields asked for.",
#    "capture": {"doc_fields": "JSON with the fields read from the document"}, "inputs": []}
#   {"id": "image-gen", "parent": "assistant", "name": "Image Generator", "resource": "image",
#    "operation": "generation", "model": "gemini-2.5-flash-image",
#    "prompt": "Generate one image that matches the request.",
#    "llm_tool_description": "Generates one image from a description and returns its URL."}
# A master can analyse media itself: "resource": "image" (or video / audio / document) with a model that accepts it.
