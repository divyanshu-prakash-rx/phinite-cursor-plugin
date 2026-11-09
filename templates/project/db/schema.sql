-- Schema for this use case. Each use case gets its OWN schema in the shared DB (DROP + CREATE = clean reset).
-- Replace "myschema" here, in tools-src/_common.py (SCHEMA) and in demo/simulate.py (SCHEMA).
DROP SCHEMA IF EXISTS myschema CASCADE;
CREATE SCHEMA myschema;
SET search_path = myschema, public;

CREATE TABLE cases (
    case_id        text PRIMARY KEY,
    customer_name  text NOT NULL,
    request        text NOT NULL,
    language       text NOT NULL DEFAULT 'en',
    status         text NOT NULL DEFAULT 'OPEN',
    created_at     timestamptz NOT NULL DEFAULT now()
);

-- ── Required by the kit's shared tool helpers ────────────────────────────────
CREATE TABLE notifications (          -- outbox for SMS / email / Teams (SMS is also sent via Twilio when configured)
    id               serial PRIMARY KEY,
    created_at       timestamptz NOT NULL DEFAULT now(),
    channel          text NOT NULL,
    recipient        text NOT NULL,
    subject          text NOT NULL,
    body             text NOT NULL,
    related_id       text,
    sent_to          text,
    delivery_status  text,
    provider_id      text,
    delivery_error   text
);

CREATE TABLE audit_log (
    id          serial PRIMARY KEY,
    at          timestamptz NOT NULL DEFAULT now(),
    actor       text NOT NULL,
    action      text NOT NULL,
    subject_id  text,
    details     jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE tool_call_log (          -- every tool call: the exact inputs Phinite passed + outcome (debugging gold)
    id      serial PRIMARY KEY,
    at      timestamptz NOT NULL DEFAULT now(),
    tool    text NOT NULL,
    inputs  jsonb NOT NULL,
    ok      boolean NOT NULL,
    error   text
);
