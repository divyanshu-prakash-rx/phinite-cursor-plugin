"""start_case — Example Assistant (Phinite tool, no params: reads capture variables from inputs).

Creates the case from the captured answers; returns ok:false with the list of answers still missing so the
agent knows exactly what to ask. Idempotent: an existing open case for the same person is returned.

inputs (captures): customer_name, request, preferred_language
env:     DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
returns: case_id
capture: case_id
"""


def _run(cur, inputs, env):
    name = _str(inputs, "customer_name")
    request = _str(inputs, "request")
    missing = [k for k, v in (("customer_name", name), ("request", request)) if not v]
    if missing:
        return _fail("Some answers are still needed", "Ask the user for: " + ", ".join(missing), missing=missing)
    cur.execute("SELECT case_id FROM cases WHERE lower(customer_name) = lower(%s) AND status = 'OPEN'", (name,))
    existing = cur.fetchone()
    if existing:
        return _ok({"case_id": existing["case_id"], "already_open": True}, {"case_id": existing["case_id"]})
    case_id = _next_id(cur, "cases", "case_id", "CASE")
    cur.execute("INSERT INTO cases (case_id, customer_name, request, language) VALUES (%s, %s, %s, %s)",
                (case_id, name, request, _str(inputs, "preferred_language", default="en")))
    _audit(cur, "example_assistant", "CASE_CREATED", case_id, {"request": request})
    return _ok({"case_id": case_id}, {"case_id": case_id})
