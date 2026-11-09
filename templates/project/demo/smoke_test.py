"""Smoke test: call every tool's main() against the real DB, with inputs shaped the way Phinite passes them
(capture variables + conversation_history), and assert each outcome. No LLM involved. Resets the DB before/after.

  python demo/smoke_test.py [--keep]
"""
import importlib.util
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import simulate  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV = simulate.load_env()
TOOLS = {p.stem: p for p in (ROOT / "tools").glob("*/*.py")}


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


simulate.reset()
tool("start_case", False, request="")                                   # missing answer → ok:false
case = tool("start_case", customer_name="Maria Gonzalez", request="order status",
            conversation_history=history("Hi, I'm Maria Gonzalez and I need help with my order"))
assert case["case_id"].startswith("CASE-")
assert tool("start_case", customer_name="Maria Gonzalez", request="again")["already_open"]
print("\nALL PASSED")
if "--keep" not in sys.argv:
    simulate.reset()
