"""What gets deployed to Phinite for this use case: models, tools, graphs. Read by the plugin's deploy_project
(or kit/deploy.py). This template keeps its data in Postgres; without a database use templates/project_nodb.

Design rules (playbook 02_GRAPH_DESIGN.md and 07_MULTIAGENT_AND_MULTIMODAL.md):
- Start with ONE master agent. Split into more masters only for real phases, roles or branches, and give each one
  job and a short prompt. A master with several outgoing edges is a branch point: label each edge with WHEN to take
  it (Phinite's router compares the master's result with the labels).
- A child agent does one specialised LLM job for its master: analyse text / image / video / audio / document, or
  generate text / image / video. Pick each agent's model with list_models(resource, operation); masters need
  tool calling.
- Tools take NO params ([]). A tool with params receives ONLY the LLM's arguments; a param-less tool receives every
  non-empty capture variable of its master + capture variables returned by earlier tools/child agents
  + conversation_history + workflow_id (+ user_variables in AUTONOMOUS graphs). Don't mention captures in prompts.
- A child agent stores its output with StoreVariableTool into one of its "capture" variables; tools then get it.
"""

# Optional named model blocks. "phinite" (gpt-5.2) and any model name from list_models work without an entry here.
# BYOM models are per workspace: refer to them by label (e.g. "Gemma_CIQ"); the plugin looks up the byomid.
MODELS = {}
DEFAULT_MODEL = "phinite"

# name: (tools/<Folder>, description shown to the LLM, params (keep []), capture variables the tool RETURNS)
TOOLS = {
    "start_case": ("Example_Graph",
        "Creates (or updates) the case from what the user told us. Returns ok:false with the missing answers.",
        [], {"case_id": "Case id"}),
}

# Documents agents answer from (RAG). deploy_project creates each knowledge base and uploads these files once
# (by name); give an agent "knowledge": ["<name>"] and tell it in its prompt to search with RAGTool.
KNOWLEDGE = {}            # e.g. {"Product FAQ": ["knowledge/faq.pdf", "knowledge/manuals/"]}

GRAPHS = [
    {"name": "MYUC - 1 Example Assistant", "graphType": "conversational",      # or "autonomous"
     "description": "One sentence: who it serves and what it does.",
     "masters": [{"id": "example-assistant", "name": "Example Assistant", "prompt": "1_Example_Master.md",
                  "tools": ["start_case"],
                  "capture": {"customer_name": "Full name of the person in the chat",
                              "request": "What the person needs help with, in their words",
                              "preferred_language": "Language the person writes in: 'es' or 'en'"},
                  "inputs": []}],          # e.g. ["case_id"] for session variables sent by a trigger
     "children": [],
     # child example (one specialised job for its master; resource/operation pick what it works on):
     # {"id": "doc-verifier", "parent": "example-assistant", "name": "Document Verifier", "prompt": "2_Example_Child.md",
     #  "llm_tool_description": "Reads the extracted pages and stores result_json.", "capture": {"result_json": "..."},
     #  "inputs": ["document_bundle"], "resource": "text", "operation": "analysis", "model": "phinite"},
     # {"id": "image-gen", "parent": "example-assistant", "name": "Image Generator", "resource": "image",
     #  "operation": "generation", "model": "gemini-2.5-flash-image", "prompt": "Generate one image ...",
     #  "llm_tool_description": "Generates one image from a description and returns its URL."},
     "edges": [("start", "example-assistant", "user starts chat"), ("example-assistant", "end", "done")]},
]

# Router + specialists: start connects to ONE master, which branches; each label says WHEN to take that branch:
#   "edges": [("start", "router", "user starts chat"),
#             ("router", "billing", "The customer asks about an invoice, a payment or a refund"),
#             ("router", "support", "The customer reports a problem with the product"),
#             ("billing", "end", "billing question answered"), ("support", "end", "problem handled")]
