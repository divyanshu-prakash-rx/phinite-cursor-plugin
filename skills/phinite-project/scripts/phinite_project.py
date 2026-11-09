"""Phinite use-case projects on this machine (the hosted Phinite MCP server can't read local files). Stdlib only.

  python3 phinite_project.py new <folder> [--schema S | --no-database] [--db-env-file F]
  python3 phinite_project.py bundle <folder>                       write <folder>/deploy-out/bundle.json, print a summary
  python3 phinite_project.py deploy <folder> --link URL [--dry-run] bundle, upload KNOWLEDGE files, deploy, save ids
  python3 phinite_project.py send <link> <file or folder>...       send files to an upload_file / add_knowledge_files link
  python3 phinite_project.py env-check <folder> [--env-file F]     env names the tools read; which the file fills (no values)

Project layout (templates/project):
  graph_spec.py (or deploy/graph_spec.py)   MODELS, DEFAULT_MODEL, TOOLS, GRAPHS, optional KNOWLEDGE
                                            ({"knowledge base name": ["knowledge/file.pdf", "knowledge/folder"]})
  tools-src/_common.py + tools-src/<Folder>/<tool>.py   helper block + per-tool bodies (bundled into tools/)
  tools/<Folder>/<tool>.py                  standalone tool code that is uploaded
  agent-prompts/<file>.md                   prompt text (inlined into the bundle)
  phinite_ids.json                          ids written by deploy (per workspace)
graph_spec.py runs here, on the user's machine, never on the server. The deploy link comes from the MCP tool
deploy_project and is valid for 15 minutes.

Files only go to upload links of the Phinite MCP server (https on *.phinite.ai, the PHINITE_MCP_URL host, or
localhost), never to another URL. Hidden files such as .env are never sent by `send`: env values go through
set_env_vars, with only the names env-check reports as ready. --db-env-file copies only the DB_* lines of a file.
"""
import argparse
import importlib.util
import json
import os
import pathlib
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request

PLUGIN = pathlib.Path(__file__).resolve().parents[3]
TEMPLATE = PLUGIN / "templates" / "project"
TEMPLATE_NODB = PLUGIN / "templates" / "project_nodb"
TOOL_COMMON = PLUGIN / "templates" / "tool_common.py"
TOOL_COMMON_NODB = PLUGIN / "templates" / "tool_common_nodb.py"
BUNDLE_FORMAT = 1
USER_AGENT = "phinite-project/0.4.3"
TRUSTED_DOMAIN = ".phinite.ai"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
LINK_PATH = re.compile(r"/u/[A-Za-z0-9_=-]+/?")
KB_FORMATS = {".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".csv", ".html", ".htm", ".md", ".json", ".xml", ".png",
              ".jpg", ".jpeg", ".tiff", ".tif"}
DB_NAMES = ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
# env.get("X") / env["X"] / env_variables.get("X") / _ENV.get("X"), and every quoted name in _env_any("A", "B")
ENV_READ = re.compile(r"""(?:\benv(?:_variables)?|\b_ENV)\s*(?:\.get\(|\[)\s*["']([A-Za-z_][A-Za-z0-9_]*)["']""")
ENV_ANY = re.compile(r"\b_env_any\(([^)]*)\)")
QUOTED = re.compile(r"""["']([A-Za-z_][A-Za-z0-9_]*)["']""")


# ── scaffold ─────────────────────────────────────────────────────────────────
def scaffold(target, schema="", db_env_file="", database=True):
    """New use-case folder. database=True: Postgres schema `schema` (db/schema.sql, DB tool helpers, simulate +
    smoke test against the DB). database=False: no DB; tools call APIs or read files (helpers without psycopg2)."""
    target = pathlib.Path(target).expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"{target} exists and is not empty")
    if not database:
        shutil.copytree(TEMPLATE_NODB, target, dirs_exist_ok=True)
        write(target / "tools-src" / "_common.py", read(TOOL_COMMON_NODB))
        if db_env_file:
            write(target / ".env", db_env_lines(db_env_file))
        else:
            write(target / ".env", "# env variables your tools read (also set them in Phinite: set_env_vars)\n")
        write(target / ".gitignore", GITIGNORE)
        return sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file())
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", schema or ""):
        raise ValueError("schema must be lowercase letters, digits or underscore (e.g. myuc)")
    shutil.copytree(TEMPLATE, target, dirs_exist_ok=True)
    for rel in ("db/schema.sql", "demo/simulate.py"):
        p = target / rel
        if p.exists():
            write(p, read(p).replace("myschema", schema))
    common = read(TOOL_COMMON).replace('SCHEMA = "myschema"', f'SCHEMA = "{schema}"')
    write(target / "tools-src" / "_common.py", common)
    if db_env_file:
        write(target / ".env", db_env_lines(db_env_file))
    else:
        write(target / ".env", "DB_HOST=\nDB_PORT=5432\nDB_NAME=\nDB_USER=\nDB_PASSWORD=\n")
    write(target / ".gitignore", GITIGNORE)
    return sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file())


GITIGNORE = ".env\n.env.*\n__pycache__/\ndeploy-out/\n"


def read(path):
    return pathlib.Path(path).read_text(encoding="utf-8")


def write(path, text):
    pathlib.Path(path).write_text(text, encoding="utf-8")


# ── env variables (names only; values never leave this machine except through a set_env_vars link) ─────────
def env_key(line):
    """The key of a KEY=VALUE line, read the way the server reads an uploaded file; '' for other lines."""
    if "=" not in line or line.lstrip().startswith("#"):
        return ""
    return line.split("=", 1)[0].strip().removeprefix("export ").strip()


def env_values(text):
    """{key: value} of an env file, as the server parses an uploaded one (quotes stripped, blank values kept)."""
    return {env_key(line): line.split("=", 1)[1].strip().strip('"').strip("'")
            for line in text.splitlines() if env_key(line)}


def db_env_lines(path):
    """Only the DB_* lines of an existing env file, so a new project never inherits another project's secrets."""
    keep = [line for line in read(pathlib.Path(path).expanduser()).splitlines() if env_key(line).startswith("DB_")]
    if not keep:
        raise ValueError(f"{pathlib.Path(path).name}: no DB_* lines to copy")
    return "# DB_* lines copied by phinite_project.py new; add the other variables your tools read\n" + \
        "\n".join(keep) + "\n"


def env_names_in(path):
    text = read(path)
    names = set(ENV_READ.findall(text))
    for args in ENV_ANY.findall(text):
        names.update(QUOTED.findall(args))
    return names


def env_check(project, env_file=""):
    """Which env variable names the project's tools read, and which of them the local env file fills. Reports names
    only, never values: pass `ready` as set_env_vars(names=...)."""
    project = pathlib.Path(project).expanduser().resolve()
    if not project.is_dir():
        raise FileNotFoundError(f"Not a project folder: {project}")
    common = project / "tools-src" / "_common.py"
    bodies = sorted((project / "tools-src").glob("*/*.py")) or sorted((project / "tools").glob("*/*.py"))
    tools = set().union(*(env_names_in(f) for f in bodies)) if bodies else set()
    database = common.exists() and "psycopg2" in read(common)
    needed = sorted(tools | (set(DB_NAMES) if database else set()))
    helpers = sorted(env_names_in(common) - set(needed)) if common.exists() else []
    path = pathlib.Path(env_file).expanduser() if env_file else project / ".env"
    values = env_values(read(path)) if path.is_file() else {}
    return {"ok": True, "env_file": str(path), "env_file_found": path.is_file(), "needed": needed,
            "ready": [n for n in needed if values.get(n)],
            "blank": [n for n in needed if n in values and not values[n]],
            "missing": [n for n in needed if n not in values],
            "optional_helpers": helpers,
            "not_needed_in_file": sorted(set(values) - set(needed) - set(helpers)),
            "next": "Fill blank/missing names in the file first. Check list_env_vars: a name that already exists is "
                    "workspace-wide, so ask before overwriting it. Then set_env_vars(names=<ready>, "
                    "environments=[...]) and send the file to the link."}


# ── bundle ───────────────────────────────────────────────────────────────────
def load_spec(project):
    for candidate in (project / "graph_spec.py", project / "deploy" / "graph_spec.py"):
        if candidate.exists():
            spec = importlib.util.spec_from_file_location(f"graph_spec_{abs(hash(str(candidate)))}", candidate)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise FileNotFoundError(f"No graph_spec.py in {project} (or {project}/deploy)")


def prompts_dir(project):
    for candidate in (project / "agent-prompts", project / "deploy" / "agent-prompts"):
        if candidate.exists():
            return candidate
    return project / "agent-prompts"


def bundle_tools(project):
    """tools-src/ → tools/: each tool = docstring + _common.py helpers + TOOL name + body. Compiles each result."""
    src = project / "tools-src"
    if not (src / "_common.py").exists():
        return []
    common = read(src / "_common.py")
    if "\n\n\n# ── shared helpers" not in common:
        raise ValueError("tools-src/_common.py must contain the '# ── shared helpers' marker after its imports")
    head, helpers = common.split("\n\n\n# ── shared helpers", 1)
    helpers = "# ── shared helpers" + helpers
    built = []
    for body_file in sorted(src.glob("*/*.py")):
        match = re.match(r'(""".*?"""\n)(.*)', read(body_file), re.S)
        if not match:
            raise ValueError(f"{body_file} must start with a docstring")
        doc, rest = match.group(1), match.group(2).strip("\n")
        out = (f'{doc}{head}\n\nTOOL = "{body_file.stem}"\n\n\n{helpers.rstrip()}\n\n\n'
               f"# ── tool logic ───────────────────────────────────────────────────────────────\n{rest}\n")
        dest = project / "tools" / body_file.parent.name / body_file.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        write(dest, out)
        compile(out, str(dest), "exec")
        built.append(dest.relative_to(project).as_posix())
    return built


def tool_definition(project, spec, name):
    folder, description, params, capture = spec.TOOLS[name]
    path = project / "tools" / folder / f"{name}.py"
    if not path.exists():
        raise FileNotFoundError(f"tool code not found: {path}")
    return {"code": read(path), "description": description, "params": [list(p) if isinstance(p, tuple) else p
                                                                              for p in params],
            "capture": dict(capture)}


def knowledge_files(paths, base=None):
    """Expand files and folders (one level deep) into the list of uploadable files; raises on bad paths.
    With a project (`base`), every file must be inside it (KNOWLEDGE entries point at knowledge/…), and hidden or env
    files are never uploaded: agents can read and quote whatever is in a knowledge base."""
    root = pathlib.Path(base).expanduser().resolve() if base else None

    def inside(path):
        return root is None or path.resolve().is_relative_to(root)

    files = []
    for item in paths or []:
        p = pathlib.Path(item).expanduser()
        if root and not p.is_absolute():
            p = root / p
        if not inside(p):
            raise ValueError(f"{item}: knowledge files must be inside the project; copy them into knowledge/")
        if p.is_dir():
            files += sorted(f for f in p.iterdir() if f.is_file() and sendable(f) and inside(f)
                            and f.suffix.lower() in KB_FORMATS)
        elif p.is_file():
            if not sendable(p):
                raise ValueError(f"{p.name}: hidden and env files are never uploaded")
            if p.suffix.lower() not in KB_FORMATS:
                raise ValueError(f"{p.name}: unsupported format (use {sorted(KB_FORMATS)})")
            files.append(p)
        else:
            raise FileNotFoundError(f"Not a file or folder: {p}")
    if not files:
        raise ValueError(f"No uploadable files in {paths}")
    return files


def inline_prompts(graph, project):
    """graph_spec.py names prompt files ("prompt": "1_X.md" or "prompt_file"); the server only takes the text.
    Prompt files must sit inside the project, so a spec can't pull other files from this machine into the bundle."""
    pdir = prompts_dir(project)

    def inside(path):
        resolved = path.resolve()
        return resolved.is_file() and resolved.is_relative_to(project)

    def fix(agent):
        agent = dict(agent)
        ref = agent.pop("prompt_file", None)
        prompt = agent.get("prompt") or ""
        if not ref and prompt.endswith(".md") and "\n" not in prompt and (pdir / prompt).exists():
            ref = prompt
        if ref:
            path = next((p for p in (pdir / ref, project / ref) if inside(p)), None)
            if not path:
                raise FileNotFoundError(f"agent '{agent.get('id')}': prompt file {ref} not found inside the project "
                                        f"({pdir})")
            agent["prompt"] = read(path)
        return agent
    return {**graph, "masters": [fix(a) for a in graph["masters"]],
            "children": [fix(a) for a in graph.get("children") or []]}


def read_ids(project):
    for candidate in (project / "phinite_ids.json", project / "deploy" / "phinite_ids.json"):
        if candidate.exists():
            return candidate, json.loads(read(candidate))
    return project / "phinite_ids.json", {}


def build_bundle(project):
    """(bundle, local files per knowledge base, files bundled into tools/). Writes deploy-out/bundle.json."""
    project = pathlib.Path(project).expanduser().resolve()
    spec = load_spec(project)
    bundled = bundle_tools(project)
    knowledge = {name: knowledge_files(paths, project) for name, paths in (getattr(spec, "KNOWLEDGE", {}) or {}).items()}
    _, ids = read_ids(project)
    bundle = {"format": BUNDLE_FORMAT, "project": project.name, "models": getattr(spec, "MODELS", {}) or {},
              "default_model": getattr(spec, "DEFAULT_MODEL", None),
              "tools": {name: tool_definition(project, spec, name) for name in spec.TOOLS},
              "graphs": [inline_prompts(g, project) for g in spec.GRAPHS],
              "knowledge": {name: [f.name for f in files] for name, files in knowledge.items()},
              "ids": ids}
    bundle = json.loads(json.dumps(bundle))           # exactly what is sent (tuples become lists)
    out = project / "deploy-out"
    out.mkdir(exist_ok=True)
    write(out / "bundle.json", json.dumps(bundle, indent=1))
    return bundle, knowledge, bundled


# ── talking to upload links ──────────────────────────────────────────────────
def check_link(link):
    """Accept only an upload link of the Phinite MCP server, so local files can't be sent to another host (for
    example by a link planted in a document or web page Claude read)."""
    url = urllib.parse.urlsplit(link)
    host = (url.hostname or "").lower()
    configured = (urllib.parse.urlsplit(os.environ.get("PHINITE_MCP_URL", "")).hostname or "").lower()
    trusted = host.endswith(TRUSTED_DOMAIN) or host in LOCAL_HOSTS or (configured and host == configured)
    secure = url.scheme == "https" or (url.scheme == "http" and host in LOCAL_HOSTS)
    if not (trusted and secure and LINK_PATH.fullmatch(url.path) and not url.query and not url.fragment):
        raise ValueError("not a Phinite upload link: use the upload_url an MCP tool (deploy_project, upload_file, "
                         "add_knowledge_files) returned, unchanged")
    return link.rstrip("/")


def sendable(path):
    """Hidden files (.env, .git…) and env files never leave the machine through `send`."""
    return not path.name.startswith(".") and not path.name.lower().endswith(".env")


def post(url, data, content_type="application/octet-stream", timeout=900):
    request = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": content_type, "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {"ok": False, "error": f"HTTP {e.code}"}
    except urllib.error.URLError as e:
        return 0, {"ok": False, "error": f"can't reach the MCP server ({e.reason})"}


def with_query(url, **params):
    return url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)


def deploy(project, link, dry_run=False):
    link = check_link(link)
    project = pathlib.Path(project).expanduser().resolve()
    bundle, knowledge, bundled = build_bundle(project)
    result = {"project": str(project), "bundled": bundled, "knowledge_uploads": []}
    if not dry_run:
        for kb, files in knowledge.items():
            for f in files:
                status, answer = post(with_query(link + "/knowledge", kb=kb, name=f.name), f.read_bytes())
                result["knowledge_uploads"].append({"knowledge_base": kb, "file": f.name, "http": status,
                                                    "status": answer.get("status") or answer.get("error")})
                if status != 200:
                    result.update(ok=False, error=f"upload of {f.name} failed: {answer.get('error')}",
                                  next=answer.get("next"))
                    return result
    status, report = post(link, json.dumps(bundle).encode(), "application/json")
    result["report"] = report
    result["ok"] = status == 200 and report.get("ok", False)
    if status == 200 and report.get("ids"):
        ids_file, _ = read_ids(project)
        write(ids_file, json.dumps(report.pop("ids"), indent=1))
        result["ids_file"] = str(ids_file)
    return result


def send(link, paths):
    link = check_link(link)
    files, skipped = [], []
    for item in paths:
        p = pathlib.Path(item).expanduser()
        if p.is_dir():
            for f in sorted(x for x in p.iterdir() if x.is_file()):
                (files if sendable(f) else skipped).append(f)
        elif not p.is_file():
            raise FileNotFoundError(f"Not a file or folder: {p}")
        elif not sendable(p):
            raise ValueError(f"{p.name}: hidden and env files are never sent (env values: set_env_vars)")
        else:
            files.append(p)
    if not files:
        raise ValueError(f"No files to send in {paths}")
    results = []
    for f in files:
        status, answer = post(with_query(link, name=f.name), f.read_bytes())
        results.append({"file": f.name, "http": status, **answer})
    return {"ok": all(r["http"] == 200 for r in results), "files": results,
            "skipped": [f.name for f in skipped]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    new = sub.add_parser("new")
    new.add_argument("folder")
    new.add_argument("--schema", default="")
    new.add_argument("--no-database", action="store_true")
    new.add_argument("--db-env-file", default="")
    sub.add_parser("bundle").add_argument("folder")
    dep = sub.add_parser("deploy")
    dep.add_argument("folder")
    dep.add_argument("--link", required=True)
    dep.add_argument("--dry-run", action="store_true")
    snd = sub.add_parser("send")
    snd.add_argument("link")
    snd.add_argument("paths", nargs="+")
    chk = sub.add_parser("env-check")
    chk.add_argument("folder")
    chk.add_argument("--env-file", default="")
    args = parser.parse_args(argv)
    try:
        if args.command == "new":
            files = scaffold(args.folder, args.schema, args.db_env_file, not args.no_database)
            out = {"ok": True, "path": str(pathlib.Path(args.folder).expanduser().resolve()), "files": files,
                   "next": "Edit graph_spec.py, tools-src/ and agent-prompts/, then deploy (dry run first)"}
        elif args.command == "bundle":
            bundle, knowledge, bundled = build_bundle(args.folder)
            out = {"ok": True, "bundle": str(pathlib.Path(args.folder).expanduser().resolve() / "deploy-out" /
                                             "bundle.json"),
                   "bundled": bundled, "tools": sorted(bundle["tools"]), "graphs": [g["name"] for g in bundle["graphs"]],
                   "knowledge": bundle["knowledge"]}
        elif args.command == "deploy":
            out = deploy(args.folder, args.link, args.dry_run)
        elif args.command == "env-check":
            out = env_check(args.folder, args.env_file)
        else:
            out = send(args.link, args.paths)
    except (FileNotFoundError, FileExistsError, ValueError, SyntaxError, KeyError) as e:
        out = {"ok": False, "error": f"{e.__class__.__name__}: {e}"}
    print(json.dumps(out, indent=1, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
