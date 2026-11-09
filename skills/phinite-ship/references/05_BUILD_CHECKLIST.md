# 05 · Build checklist: from use case to verified demo

## A. Understand
- [ ] Who are the people involved (citizen, staff, approver, partner)? Which steps are conversational and which autonomous? Where must a **human approve**?
- [ ] List the decisions and the rules behind them. Which documents prove what?
- [ ] Propose a graph split, usually 2–5 graphs, one per audience, and agree the demo story, including a "gap → fix → resume" loop if relevant.

## B. Set up
- [ ] `python kit/set_auth.py --check`. If it's expired, refresh it (00).
- [ ] `python kit/new_project.py ../<uc> --schema <uc> --db-env ../sba-phase0/.env`
- [ ] Confirm the Phinite workspace `env_variables` contain `DB_*`, plus Twilio if SMS is needed.
- [ ] Choose the model (`DEFAULT_MODEL`); default to Gemma_CIQ for CIQ.

## C. Build
- [ ] `db/schema.sql` + `seed.sql`, with rules and thresholds as data.
- [ ] `graph_spec.py`: graphs, masters, children, **captures with precise descriptions**, tools with `params: []`.
- [ ] `tools-src/…`: every guardrail checked in the DB; refusals carry an actionable `next`; idempotent where re-runs happen.
- [ ] `agent-prompts/…`: Role, numbered Steps with stops, Rules (honesty, `ok:false → next`, human confirmation).
- [ ] `python kit/build_tools.py --project ../<uc>` and `python -m pyflakes ../<uc>/tools`

## D. Test
- [ ] `demo/smoke_test.py` passes: happy path, refusals, the whole story.
- [ ] `python kit/deploy.py --project ../<uc>`, then `--dry-run` first if you're unsure.
- [ ] `kit/test_tool.py` each tool with realistic inputs (a dry-run input for tools with side effects).
- [ ] `kit/chat.py` each graph; read `simulate.py log` after each run.
- [ ] `demo/live_e2e.py` passes end to end; reset the DB afterwards.

## E. Hand over
- [ ] `README.md`: graphs, tools, known gaps.
- [ ] `DEMO_RUNBOOK.md`: what to type, what to show, terminal steps, reset.
- [ ] `variables.md` (env, captures, tools), generated from `graph_spec.py`.
- [ ] Note what's mocked vs. real, and what the user must configure (trigger URLs, env vars).
- [ ] **Leave the DB reset** to a clean demo state.

## Definition of done
Every graph has been run **live in Phinite** with at least one full scenario. `tool_call_log` shows no unexpected refusals. Every claim in the docs is backed by a live run, not only the local test.
