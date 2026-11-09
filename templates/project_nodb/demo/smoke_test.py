"""Smoke test: call every tool's main() with inputs shaped the way Phinite passes them (capture variables +
conversation_history) and assert each outcome. No LLM and no Phinite calls.

  python demo/smoke_test.py      (build tools/ first: the plugin's deploy_project dry run, or kit/build_tools.py)
"""
import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS = {p.stem: p for p in (ROOT / "tools").glob("*/*.py")}
ENV = {}                                   # env_variables your tools read, from the project's .env if present
if (ROOT / ".env").exists():
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            ENV[key.strip()] = value.strip()


def tool(name, expect_ok=True, **inputs):
    spec = importlib.util.spec_from_file_location(name, TOOLS[name])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = module.main(inputs, ENV)["output"]
    print(f"  {'ok ' if out['ok'] else 'ERR'} {name}: {out.get('error') or ''}")
    assert out["ok"] == expect_ok, f"{name}: {json.dumps(out, default=str)[:800]}"
    return out


def history(*messages):   # the shape Phinite uses for conversation_history
    return [{"role": "user", "message": str({"message": m})} for m in messages]


tool("lookup_item", False)                                           # nothing asked yet → ok:false with a next step
item = tool("lookup_item", item_query="desk lamp", conversation_history=history("Do you have the desk lamp?"))
assert item["item"]["sku"] == "SKU-100"
tool("lookup_item", False, item_query="teapot")
print("\nALL PASSED")
