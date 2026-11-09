"""Demo helper for this use case.

  python demo/simulate.py reset          load db/schema.sql (+ db/seed.sql if present) — wipes this use case's schema
  python demo/simulate.py log [N]        last N tool calls: tool, ok, error, inputs (what Phinite really passed)
  python demo/simulate.py outbox [N]     last N notifications (SMS with Twilio delivery status)
Reads DB_* from ../.env.
"""
import json
import os
import pathlib
import sys

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = "myschema"


def load_env():
    env = dict(os.environ)
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, value = line.split("=", 1)
            env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return env


def connect():
    env = load_env()
    return psycopg2.connect(host=env["DB_HOST"], port=int(env.get("DB_PORT") or env.get("PORT") or 5432),
                            dbname=env["DB_NAME"], user=env["DB_USER"],
                            password=env.get("DB_PASSWORD") or env.get("DB_PASSWROD"),
                            options=f"-c search_path={SCHEMA},public", connect_timeout=10)


def show(query, params=()):
    with connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        return cur.fetchall()


def reset():
    with connect() as conn, conn.cursor() as cur:
        cur.execute((ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
        if (ROOT / "db" / "seed.sql").exists():
            cur.execute((ROOT / "db" / "seed.sql").read_text(encoding="utf-8"))
    print(f"schema {SCHEMA} reset")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "log"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    if cmd == "reset":
        reset()
    elif cmd == "log":
        for row in reversed(show("SELECT tool, ok, error, inputs FROM tool_call_log ORDER BY id DESC LIMIT %s", (n,))):
            row["inputs"].pop("conversation_history", None)
            print(f"{row['tool']:28s} ok={row['ok']} {row['error'] or ''}\n    {json.dumps(row['inputs'], ensure_ascii=False)[:600]}")
    elif cmd == "outbox":
        for row in reversed(show("SELECT * FROM notifications ORDER BY id DESC LIMIT %s", (n,))):
            print(f"\n[{row['channel']}] {row['recipient']} — {row['subject']} {row['delivery_status'] or ''} "
                  f"{row['delivery_error'] or ''}\n{row['body']}")
