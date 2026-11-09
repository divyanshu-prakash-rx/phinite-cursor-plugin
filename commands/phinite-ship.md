# Ship a tested graph — publish, build, assign an environment, and expose it (trigger or Chat API)

Arguments: <graph name or flow id> [development|uat|production]

Ship this Phinite graph: the details the user typed after the command (environment defaults to development)

1. Load the `phinite-ship` skill.
2. `publish_flow` → new flow version.
3. `create_build` for that version and environment. If it refuses because a tool was never published, publish it
   (or run `deploy_project`) and retry.
   For uat or production, set that environment's env variables first (the `phinite-ship` skill, step 3): they
   start empty there.
4. Autonomous graph: `create_trigger` (ask: API, background or cron; for cron, the schedule). Conversational graph:
   `create_chat_api`.
5. `create_api_key`. It keeps an existing active key named `phinite-mcp`. The key stays in Phinite and is never
   shown; callers copy it from the Phinite UI (API keys).
6. Prove it works from outside: `call_trigger` with realistic `user_variables`, or `chat_api` with a first message;
   then `get_logs` on the returned workflow id.
7. Report the URLs per environment, how callers authenticate (Bearer workspace API key) and the exact request body.
