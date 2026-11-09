"""Shared helpers for Phinite tools that need no database — copy to <project>/tools-src/_common.py.

For use cases that call APIs, transform data or read files instead of keeping their own tables (assistants,
API integrations, document or media pipelines). kit/build_tools.py (the plugin's deploy_project) puts this block
into every tool file, because Phinite tools are standalone single files.
Contract: Phinite calls main(inputs, env_variables) and expects {"output": {...}, "capture_variables": {...}}.
Each tool body defines _run(inputs, env) and returns _ok(...) or _fail(...). Do not edit the generated tools/.
Every exception becomes a _fail with a useful `next`, so the agent never sees a stack trace.
"""
import json
import re
import time

import requests


# ── shared helpers (same block in every tool) ────────────────────────────────
def _ok(output, capture=None):
    return {"output": {"ok": True, **output}, "capture_variables": capture or {}}


def _fail(error, next_step, retryable=False, **extra):
    return {"output": {"ok": False, "error": error, "next": next_step, "retryable": retryable, **extra},
            "capture_variables": {}}


EMPTY = {"", "null", "none", "n/a", "na", "unknown", "not provided", "not specified", "not mentioned", "-"}


def _str(inputs, *keys, default=None):
    """First non-empty value among keys — capture variables, user_variables or tool outputs injected into inputs."""
    for key in keys:
        value = inputs.get(key)
        if value is not None and str(value).strip().lower() not in EMPTY:
            return _restore_accents(inputs, str(value).strip())
    return default


def _restore_accents(inputs, value):
    """Capture extraction can drop non-ASCII letters ('María' → 'Mara'). If the user's own words in
    conversation_history contain a phrase that reduces to the captured value, use the original phrase."""
    history = inputs.get("conversation_history")
    if not isinstance(history, list) or not value.isascii() or not value.strip():
        return value
    size = len(value.split())
    for turn in reversed(history):
        if not isinstance(turn, dict) or turn.get("role") != "user":
            continue
        words = re.findall(r"[^\s,;:.!?¿¡()\"'{}]+", str(turn.get("message", "")))
        for i in range(len(words) - size + 1):
            phrase = " ".join(words[i:i + size])
            if phrase != value and "".join(c for c in phrase if c.isascii()) == value:
                return phrase
    return value


def _num(inputs, key, default=None):
    value = inputs.get(key)
    if value is None or str(value).strip().lower() in EMPTY:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d[\d,]*(\.\d+)?", str(value))
    return float(match.group(0).replace(",", "")) if match else default


def _bool(inputs, key, default=False):
    value = inputs.get(key)
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in ("true", "yes", "y", "1", "si", "sí")


def _list(inputs, key):
    value = inputs.get(key)
    if value is None or value == "":
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            value = parsed if isinstance(parsed, list) else [parsed]
        except ValueError:
            value = re.split(r"[,;]", value)
    return [str(v).strip() for v in value if str(v).strip()]


def _json(inputs, key, default=None):
    """A capture that holds JSON (e.g. a child agent's stored result), parsed; default if missing or invalid."""
    value = inputs.get(key)
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value) if value else default
    except (TypeError, ValueError):
        return default


_ENV = {}          # env_variables of the current call (set by _run_tool)


def _env_any(*names):
    return next((_ENV[n] for n in names if _ENV.get(n)), None)


def _http(method, url, retries=2, timeout=(10, 30), **kwargs):
    """requests with a timeout and retries on network errors and 429/5xx (outbound calls from the Phinite runtime
    can time out transiently). Raises the last error; _run_tool turns it into a _fail."""
    for attempt in range(retries + 1):
        try:
            response = requests.request(method, url, timeout=timeout, **kwargs)
            if response.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(float(response.headers.get("Retry-After") or 2 ** attempt))
                continue
            return response
        except requests.RequestException:
            if attempt == retries:
                raise
            time.sleep(2 ** attempt)


def _file_links(inputs):
    """File links from capture variables (uploads) and from links pasted in the user's messages."""
    links = []
    for key, value in inputs.items():
        if key == "conversation_history" or value is None:
            continue
        if re.search(r"file|url|document|upload|link|image|video|audio", key, re.I):
            links += re.findall(r"https?://[^\s,;\"'<>\]\[)]+", str(value))
    for turn in inputs.get("conversation_history") or []:
        if isinstance(turn, dict) and turn.get("role") == "user":
            links += re.findall(r"https?://[^\s,;\"'<>\]\[)]+", str(turn.get("message", "")))
    return list(dict.fromkeys(link.rstrip(".") for link in links))


def _pdf_pages(url):
    """Download a PDF and return its text page by page (pypdf, pdfplumber fallback — both are in the runtime)."""
    import io
    data = _http("GET", url)
    data.raise_for_status()
    try:
        from pypdf import PdfReader
        return [(page.extract_text() or "").strip() for page in PdfReader(io.BytesIO(data.content)).pages]
    except Exception:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data.content)) as pdf:
            return [(page.extract_text() or "").strip() for page in pdf.pages]


def _run_tool(inputs, env_variables):
    _ENV.clear()
    _ENV.update(env_variables or {})
    try:
        return _run(inputs or {}, _ENV)
    except requests.RequestException as exc:
        return _fail(f"{TOOL}: external call failed ({exc.__class__.__name__})",
                     "Retry once; if it fails again, tell the user the service is unavailable.", True)
    except Exception as exc:
        return _fail(f"{TOOL} failed: {exc}", "Retry once; if it fails again, report the error to the team.", True)


def main(inputs, env_variables):
    return _run_tool(inputs, env_variables)
