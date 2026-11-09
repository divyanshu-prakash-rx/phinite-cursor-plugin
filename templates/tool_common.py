"""Shared helpers for Phinite tools — copy to <project>/tools-src/_common.py and set SCHEMA.

kit/build_tools.py puts this block into every tool file (Phinite tools are standalone single files).
Contract: Phinite calls main(inputs, env_variables) and expects {"output": {...}, "capture_variables": {...}}.
Each tool body defines _run(cur, inputs, env) and returns _ok(...) or _fail(...). Do not edit the generated tools/.
"""
import json
import random
import re
import string
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal

import psycopg2
from psycopg2.extras import Json, RealDictCursor

SCHEMA = "myschema"   # ← the use case's Postgres schema (each use case gets its own; tools set search_path to it)


# ── shared helpers (same block in every tool) ────────────────────────────────
def _connect(env):
    return psycopg2.connect(
        host=env.get("DB_HOST"), port=int(env.get("DB_PORT") or env.get("PORT") or 5432),
        dbname=env.get("DB_NAME"), user=env.get("DB_USER"),
        password=env.get("DB_PASSWORD") or env.get("DB_PASSWROD"),
        connect_timeout=10, options=f"-c search_path={SCHEMA},public")


def _plain(value):
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _ok(output, capture=None):
    return {"output": _plain({"ok": True, **output}), "capture_variables": _plain(capture or {})}


def _fail(error, next_step, retryable=False, **extra):
    return {"output": _plain({"ok": False, "error": error, "next": next_step, "retryable": retryable, **extra}),
            "capture_variables": {}}


EMPTY = {"", "null", "none", "n/a", "na", "unknown", "not provided", "not specified", "not mentioned", "-"}


def _str(inputs, *keys, default=None):
    """First non-empty value among keys — tool params or capture variables injected into inputs."""
    for key in keys:
        value = inputs.get(key)
        if value is not None and str(value).strip().lower() not in EMPTY:
            return _restore_accents(inputs, str(value).strip())
    return default


def _restore_accents(inputs, value):
    """Capture extraction can drop non-ASCII letters ('María Álvarez' → 'Mara lvarez'). If the user's own words
    in conversation_history contain a phrase that reduces to the captured value, use the original phrase."""
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
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    text = str(value)
    match = re.search(r"-?\d[\d,]*(\.\d+)?", text)
    if not match:
        return default
    number = float(match.group(0).replace(",", ""))
    if re.search(r"\d\s*(k|K|thousand|mil)\b", text):
        number *= 1000
    elif re.search(r"\d\s*(m|M|million|millones|millón)\b", text):
        number *= 1000000
    return number


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
            value = [v for v in re.split(r"[,;]", value)]
    return [str(v).strip() for v in value if str(v).strip()]


def _code(value):
    return re.sub(r"[^A-Z0-9]+", "_", str(value or "").upper()).strip("_")


def _name_key(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()


def _next_id(cur, table, column, prefix):
    year = datetime.now().year
    cur.execute(f"SELECT {column} FROM {table} WHERE {column} LIKE %s ORDER BY {column} DESC LIMIT 1",
                (f"{prefix}-{year}-%",))
    row = cur.fetchone()
    last = int(row[column].rsplit("-", 1)[1]) if row else 0
    return f"{prefix}-{year}-{last + 1:05d}"


def _audit(cur, actor, action, subject_id, details):
    cur.execute("INSERT INTO audit_log (actor, action, subject_id, details) VALUES (%s, %s, %s, %s)",
                (actor, action, subject_id, Json(_plain(details))))


_ENV = {}          # env_variables of the current call (set by _run_tool)
SMS_LOG = []       # SMS delivery results of the current call, added to the tool output
_TWILIO_FROM = {}  # cache: account sid → sender number


def _env_any(*names):
    return next((_ENV[n] for n in names if _ENV.get(n)), None)


def _e164(raw):
    """The number exactly as given: '+…' is kept digit for digit; 10 digits get TWILIO_DEFAULT_COUNTRY_CODE (+1)."""
    raw = str(raw or "").strip()
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+") or raw.startswith("00"):
        return "+" + digits.lstrip("0") if raw.startswith("00") else "+" + digits
    if len(digits) == 10:
        return (_env_any("TWILIO_DEFAULT_COUNTRY_CODE") or "+1") + digits
    return "+" + digits if len(digits) > 10 else None


def _twilio_sender(sid, token):
    sender = _env_any("TWILIO_FROM_NUMBER", "TWILIO_PHONE_NUMBER", "TWILIO_FROM")
    if sender:
        return {"From": sender}
    if _env_any("TWILIO_MESSAGING_SERVICE_SID"):
        return {"MessagingServiceSid": _env_any("TWILIO_MESSAGING_SERVICE_SID")}
    if sid not in _TWILIO_FROM:
        import requests
        response = requests.get(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers.json",
                                params={"PageSize": 20}, auth=(sid, token), timeout=15)
        response.raise_for_status()
        numbers = [n for n in response.json().get("incoming_phone_numbers", []) if (n.get("capabilities") or {}).get("sms")]
        _TWILIO_FROM[sid] = numbers[0]["phone_number"] if numbers else None
    return {"From": _TWILIO_FROM[sid]} if _TWILIO_FROM[sid] else None


def _send_sms(to_raw, body):
    sid = _env_any("TWILIO_ACCOUNT_SID", "TWILIO_ACOUNT_SID", "TWILIO_SID")
    token = _env_any("TWILIO_AUTH_TOKEN", "TWILIO_ACCOUNT_TOKEN", "TWILIO_ACOUNT_TOKEN", "TWILIO_TOKEN")
    to = _e164(to_raw)
    if not to:
        return {"to": to_raw, "status": "FAILED", "error": "not a valid phone number"}
    if not (sid and token):
        return {"to": to, "status": "NOT_CONFIGURED", "error": "TWILIO_ACOUNT_SID / TWILIO_ACCOUNT_TOKEN missing"}
    try:
        import requests
        sender = _twilio_sender(sid, token)
        if not sender:
            return {"to": to, "status": "FAILED", "error": "no SMS-capable Twilio number on the account (set TWILIO_FROM_NUMBER)"}
        response = requests.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                                 data={"To": to, "Body": body[:1500], **sender}, auth=(sid, token), timeout=20)
        data = response.json() if response.content else {}
        if response.status_code < 300:
            return {"to": to, "status": "SENT", "sid": data.get("sid"), "twilio_status": data.get("status")}
        return {"to": to, "status": "FAILED", "error": f"Twilio {data.get('code')}: {data.get('message')}"}
    except Exception as exc:  # the outbox row is kept either way
        return {"to": to, "status": "FAILED", "error": str(exc)[:300]}


def _notify(cur, channel, recipient, subject, body, related_id):
    cur.execute("INSERT INTO notifications (channel, recipient, subject, body, related_id) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id", (channel, recipient, subject, body, related_id))
    notification_id = cur.fetchone()["id"]
    if channel == "SMS":
        result = _send_sms(recipient, body)
        cur.execute("UPDATE notifications SET sent_to = %s, delivery_status = %s, provider_id = %s, delivery_error = %s "
                    "WHERE id = %s", (result.get("to"), result["status"], result.get("sid"), result.get("error"),
                                      notification_id))
        SMS_LOG.append(result)
    return notification_id


def _file_links(inputs):
    """File links from capture variables (uploads) and from links pasted in the user's messages."""
    links = []
    for key, value in inputs.items():
        if key == "conversation_history" or value is None:
            continue
        if re.search(r"file|url|document|upload|link", key, re.I):
            links += re.findall(r"https?://[^\s,;\"'<>\]\[)]+", str(value))
    for turn in inputs.get("conversation_history") or []:
        if isinstance(turn, dict) and turn.get("role") == "user":
            links += re.findall(r"https?://[^\s,;\"'<>\]\[)]+", str(turn.get("message", "")))
    return list(dict.fromkeys(l.rstrip(".") for l in links))


def _pdf_pages(url):
    """Download a PDF and return its text page by page (pypdf, pdfplumber fallback — both are in the runtime)."""
    import io
    import requests
    data = requests.get(url, timeout=30)
    data.raise_for_status()
    try:
        from pypdf import PdfReader
        return [(page.extract_text() or "").strip() for page in PdfReader(io.BytesIO(data.content)).pages]
    except Exception:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data.content)) as pdf:
            return [(page.extract_text() or "").strip() for page in pdf.pages]


def _run_tool(inputs, env_variables):
    env = env_variables or {}
    _ENV.clear()
    _ENV.update(env)
    SMS_LOG.clear()
    try:
        conn = _connect(env)
    except Exception as exc:
        return _fail(f"Database connection failed: {exc}",
                     "Check DB_HOST, DB_PORT, DB_NAME, DB_USER and DB_PASSWORD in env_variables.", True)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            result = _run(cur, inputs or {}, env)
        if result["output"].get("ok"):
            conn.commit()
        else:
            conn.rollback()  # a refused call never leaves half-written state
    except Exception as exc:
        conn.rollback()
        result = _fail(f"{TOOL} failed: {exc}", "Retry once; if it fails again, report the error to the team.", True)
    try:  # observability: what the agent / capture variables actually passed in, and the outcome
        with conn.cursor() as cur:
            cur.execute("INSERT INTO tool_call_log (tool, inputs, ok, error) VALUES (%s, %s, %s, %s)",
                        (TOOL, Json(_plain(dict(inputs or {}))), bool(result["output"].get("ok")),
                         result["output"].get("error")))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()
    if SMS_LOG:
        result["output"]["sms_delivery"] = _plain(list(SMS_LOG))
    return result


def main(inputs, env_variables):
    return _run_tool(inputs, env_variables)

