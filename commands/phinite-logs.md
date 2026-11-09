# Read and explain the log of a Phinite run (tool calls, inputs, outputs, variables, errors)

Arguments: <workflow_id> [include llm]

Explain the Phinite run: the details the user typed after the command

1. `get_logs` with the workflow id (`include_llm: true` only if the user asked or the cause is in the model's
   reasoning).
2. Load the `phinite-debug` skill and walk the trace: which agent ran, which tools it called, with which inputs, what
   they returned, which variables were set, and where it went wrong.
3. Answer in plain words, then give the most likely cause and the concrete fix from the skill's debugging table.
