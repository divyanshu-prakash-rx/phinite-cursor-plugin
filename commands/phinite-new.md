# Start a new Phinite use case (scaffold the project folder, then design the graphs)

Arguments: <folder> [db schema] [short description of the use case]

Start a new Phinite use case: the details the user typed after the command

1. Load the `phinite-design` skill and read its references before designing anything. Load `phinite-project` for the
   local project script.
2. Agree the design with the user in a few lines: who each graph serves, conversational vs autonomous, the agents
   (one master unless there are distinct jobs or phases; children for specialised or multimodal work), the edges and
   their labels, the model for each agent (`list_models`), the tools (param-less) and the capture variables each
   master needs. Ask only what you can't infer.
3. Scaffold the folder with the project script's `new` command. Use `--no-database` unless the use case keeps its own
   records. With a database, pass a lowercase `--schema` (derive it from the folder). If the user has a `.env` with
   DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD, also pass `--db-env-file` (only its `DB_*` lines are copied). Give
   the use case's own secrets names with its prefix (`<SCHEMA>_…`), because env variables are workspace-wide.
4. Write `graph_spec.py`, `tools-src/<Folder>/<tool>.py`, `agent-prompts/*.md` (and `db/schema.sql`) following the
   skill's rules (one job per agent, labelled branches, guardrails in tools, ok/error/next results). If agents must
   answer from the user's documents, copy them into `knowledge/`, declare them in `KNOWLEDGE` and attach them with
   `"knowledge"`.
5. Do a dry run: call `deploy_project` with `dry_run: true` and run the command it returns. Fix any problems, then
   suggest `/phinite-deploy`.
