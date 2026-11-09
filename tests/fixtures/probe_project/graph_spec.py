"""Minimal no-database project used by tests/smoke_mcp.py --write (deploys into a scratch workspace)."""

MODELS = {"phinite": {"modelName": "gpt-5.2", "apiKeyName": "Phinite Api", "envencryptid": None, "_provider": None}}
DEFAULT_MODEL = "phinite"

TOOLS = {
    "plugin_probe_deploy_echo": ("Probe", "Echoes which inputs it received (test tool, no side effects).", [],
                                 {"probe_result": "Comma-separated names of the inputs the tool received"}),
}

# Knowledge bases this project needs: deploy_project creates them and uploads these files (by name, once).
KNOWLEDGE = {"plugin_probe_project_kb": ["knowledge"]}

GRAPHS = [
    {"name": "plugin_probe_project_chat", "graphType": "conversational",
     "description": "Smoke-test graph deployed by the Claude plugin's tests.",
     "masters": [{"id": "probe-assistant", "name": "Probe Assistant", "prompt": "probe.md",
                  "tools": ["plugin_probe_deploy_echo"],
                  "capture": {"user_name": "First name the user gives, if any"}, "inputs": [],
                  "knowledge": ["plugin_probe_project_kb"]}],
     "children": [],
     "edges": [("start", "probe-assistant", "user starts chat"), ("probe-assistant", "end", "done")]},
]
