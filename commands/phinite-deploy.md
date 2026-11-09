# Deploy a use-case folder to Phinite (tools upserted and published when changed, graphs updated)

Arguments: <folder> [only tools|graphs] [graph name filter]

Deploy the use case in: the details the user typed after the command

1. `whoami`: confirm the workspace with the user if this is the first deploy of the session.
2. Load the `phinite-project` skill. Call `deploy_project` with `dry_run: true` (plus `only` / `graph` if the user
   gave them), then run the returned command on the folder with `--dry-run`. Stop and fix any graph problems in the
   report.
3. Call `deploy_project` again without `dry_run` and run its command. It goes in this order:
   - It uploads the files listed in `KNOWLEDGE` to their knowledge bases (new names only).
   - It upserts every tool and publishes the ones that changed, because flow tests run the latest published tool
     version.
   - It creates or updates every graph and saves `phinite_ids.json`.
4. Env variables (never open the `.env`; follow the `phinite-project` skill): run the script's `env-check` on the
   folder and compare its `needed` names with `list_env_vars`. For names the workspace lacks, have the user fill any
   `blank`/`missing` ones, then `set_env_vars(names=[those names])` and send the `.env` to the link. Ask before
   overwriting a name that already exists: it is shared by the whole workspace.
5. Report a short table: each tool (created/updated, published version) and each graph (flow id, type). Then
   suggest `/phinite-test`.
