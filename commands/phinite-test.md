# Test a Phinite graph (chat or autonomous run), then read the run log and diagnose

Arguments: <graph name or flow id> [message or user_variables JSON]

Test this Phinite graph: the details the user typed after the command

1. Find the flow with `list_flows`; note whether it is conversational or autonomous.
2. Conversational: `chat` with the user's message (or a realistic first message for the use case), then continue
   the conversation turn by turn, passing the returned `workflow_id` as `session`, until the scenario is complete. Files (image,
   audio, video, document) go on the second turn onwards, as URLs. For local files, use `upload_file` and the
   `phinite-project` skill's `send` command to get the URLs first.
   Autonomous: `run_autonomous` with the given `user_variables` (as a JSON object), message and any files.
   For a graph with branches, run one case per branch and check each reached the right agent.
3. `get_logs` with the run's `workflow_id`: check that every expected tool ran, with the expected inputs, and that
   nothing failed. Load the `phinite-debug` skill to diagnose anything unexpected.
4. Report what happened in plain words, then the fix you propose (prompt, capture description, tool code). Apply it
   with `/phinite-deploy` for a project folder (or `upsert_tool` / `set_flow_graph`), and test again when the user
   agrees.
