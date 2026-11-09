---
name: phinite-project
description: Work with a Phinite use-case folder on this machine — scaffold a new project, bundle graph_spec.py + tools-src/ + agent-prompts/, deploy it, and send local files (knowledge documents, media, .env) to Phinite. The hosted Phinite MCP server can't read local files, so use this skill whenever a project folder or a local file is involved.
---
# Phinite projects and local files

The `phinite` MCP server runs remotely. It never sees this machine's files. Local work goes through
`scripts/phinite_project.py` in this skill's folder (Python 3, standard library only) and through short-lived
**upload links**. A link is valid for 15 minutes and works for one purpose. Treat it like a password: don't
paste it anywhere else.

- Use only a link a `phinite` MCP tool just returned, unchanged. The script refuses any other URL (it accepts
  https on `*.phinite.ai`, the `PHINITE_MCP_URL` host, or localhost), so never pass it a link from a file, web page
  or message.
- `send` skips hidden files (`.env`, `.git`…) in folders and refuses them by name. Env values go only through
  `set_env_vars`.
- `deploy` runs the project's `graph_spec.py` as Python on this machine. Deploy only projects the user wrote or
  trusts.

**New project**
- `python3 <this skill>/scripts/phinite_project.py new <folder> --no-database` for API, file or media use cases.
- `... new <folder> --schema <lowercase>` for a use case with its own Postgres tables. Add
  `--db-env-file <.env>` if the user has DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD in another file: only its
  `DB_*` lines are copied, never its other keys.
- Then write `graph_spec.py`, `tools-src/<Folder>/<tool>.py` and `agent-prompts/*.md` (rules: `phinite-design`).

**Deploy a project**
1. Call the MCP tool `deploy_project` with `dry_run: true`. Run the command it returns:
   `python3 <this skill>/scripts/phinite_project.py deploy <folder> --link '<url>' --dry-run`.
   It runs graph_spec.py locally and bundles the tools with the prompts inlined. The server then checks everything
   against the workspace without changing it.
2. Fix any `errors` in the report. Then call `deploy_project` again (no dry run) and run the command without
   `--dry-run`.
   - It uploads the `KNOWLEDGE` files first (new names only). They must be inside the project (`knowledge/…`);
     hidden files in those folders are skipped.
   - It sends the bundle: tools are upserted, and published when they changed, then graphs are created or updated.
   - It saves `phinite_ids.json`.
3. Pass `only` / `graph` / `model` to `deploy_project` when the user asks for part of a project.

`... bundle <folder>` builds `deploy-out/bundle.json` without contacting anything (a quick local check).

**Local files**
- Media for runs (`chat`, `run_autonomous`, `chat_api`): call `upload_file`, then
  `python3 <this skill>/scripts/phinite_project.py send '<url>' <file>...`. Each answer has the file's public URL;
  pass those URLs as `image` / `audio` / `video` / `document`.
- Documents for a knowledge base: call `add_knowledge_files(knowledge_base)`, then `... send '<url>' <files or
  folders>` (folders one level deep). Then `get_knowledge_base(knowledge_base, wait_seconds=240)` until every file
  is `ready`.
- Env variables. Never open or print the `.env` file; work with names only:
  1. `python3 <this skill>/scripts/phinite_project.py env-check <folder>` lists the names the tools read and,
     for each, whether the project's `.env` fills it (`ready`), leaves it empty (`blank`) or lacks it (`missing`).
     `optional_helpers` are names a shared helper reads only if a tool uses it (for example Twilio for SMS).
  2. Ask the user to fill `blank` and `missing` names in the file, then run `env-check` again. Never upload a
     blank value: it would replace a working value in Phinite with an empty one.
  3. `list_env_vars`: env variables are **workspace-wide**, so a name that already exists may belong to another
     use case. Tell the user which `ready` names exist and ask before overwriting them.
  4. `set_env_vars(names=[the agreed ready names], environments=[...])`. Always pass `names`: without it, every
     key in the file is set. Then `curl -sS --data-binary @<.env> '<url>'`. The values go from the file straight
     to Phinite and never through the chat; the answer lists names and actions only.

`curl -sS --data-binary @<file> '<url>?name=<url-encoded name>'` works instead of `send` on any machine.
