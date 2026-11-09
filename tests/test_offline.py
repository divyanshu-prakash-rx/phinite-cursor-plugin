"""Offline tests (no network) for the plugin's local project script: scaffold, bundle, deploy and send through a fake
upload link. The MCP server's own tests live in the phinite-mcp repo.

  python3 -m unittest tests/test_offline.py -v
"""
import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

PLUGIN = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN / "skills" / "phinite-project" / "scripts"))

import phinite_project as project  # noqa: E402

FIXTURE = PLUGIN / "tests" / "fixtures" / "probe_project"


class FakeLink(BaseHTTPRequestHandler):
    """Plays the MCP server's upload endpoint: records what arrives, answers like the server."""
    received = []

    def do_POST(self):
        data = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        url = urllib.parse.urlparse(self.path)
        query = dict(urllib.parse.parse_qsl(url.query))
        FakeLink.received.append((url.path, query, data))
        if url.path.endswith("/knowledge"):
            body = {"ok": True, "file": query.get("name"), "status": "uploaded: indexing"}
        elif self.headers.get("Content-Type") == "application/json":
            bundle = json.loads(data)
            body = {"ok": True, "tools": [{"name": n, "published": True} for n in bundle["tools"]],
                    "graphs": [{"name": g["name"], "flowid": "F1"} for g in bundle["graphs"]],
                    "ids": {"workspace": "WS1", "graphs": {g["name"]: {"flowid": "F1"} for g in bundle["graphs"]}}}
        else:
            body = {"ok": True, "file": query.get("name"), "url": f"https://storage.example/{query.get('name')}"}
        out = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *args):
        pass


class ProjectScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeLink)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.link = f"http://127.0.0.1:{cls.server.server_port}/u/TICKET"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        FakeLink.received = []

    def test_scaffold_and_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "uc"
            project.scaffold(target, "myuc")
            self.assertIn('SCHEMA = "myuc"', (target / "tools-src" / "_common.py").read_text(encoding="utf-8"))
            bundle, knowledge, bundled = project.build_bundle(target)
            self.assertEqual(bundled, ["tools/Example_Graph/start_case.py"])
            self.assertEqual(bundle["format"], 1)
            master = bundle["graphs"][0]["masters"][0]
            self.assertNotIn("prompt_file", master)
            self.assertGreater(len(master["prompt"]), 40)                     # the .md text, not its name
            self.assertIn("def main", bundle["tools"]["start_case"]["code"])
            self.assertEqual(json.loads((target / "deploy-out" / "bundle.json").read_text(encoding="utf-8")), bundle)

    def test_scaffold_without_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "uc"
            files = project.scaffold(target, database=False)
            self.assertNotIn("db/schema.sql", files)
            self.assertNotIn("psycopg2", (target / "tools-src" / "_common.py").read_text(encoding="utf-8"))
            _, _, bundled = project.build_bundle(target)
            self.assertEqual(bundled, ["tools/Example_Graph/lookup_item.py"])
            if importlib.util.find_spec("requests"):         # the template's tools import requests
                out = subprocess.run([sys.executable, str(target / "demo" / "smoke_test.py")], capture_output=True,
                                     text=True)
                self.assertIn("ALL PASSED", out.stdout, out.stderr)
            with self.assertRaises(FileExistsError):
                project.scaffold(target, database=False)

    def test_deploy_uploads_knowledge_then_bundle_and_saves_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "probe"
            shutil.copytree(FIXTURE, target)
            result = project.deploy(target, self.link)
            self.assertTrue(result["ok"], result)
            paths = [r[0] for r in FakeLink.received]
            self.assertEqual(paths[-1], "/u/TICKET")
            self.assertTrue(all(p == "/u/TICKET/knowledge" for p in paths[:-1]) and len(paths) > 1)
            self.assertEqual(FakeLink.received[0][1]["kb"], "plugin_probe_project_kb")
            ids = json.loads((target / "phinite_ids.json").read_text(encoding="utf-8"))
            self.assertEqual(ids["workspace"], "WS1")
            self.assertNotIn("ids", result["report"])

    def test_dry_run_sends_only_the_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "probe"
            shutil.copytree(FIXTURE, target)
            project.deploy(target, self.link, dry_run=True)
            self.assertEqual([r[0] for r in FakeLink.received], ["/u/TICKET"])

    def test_send_files_and_folders(self):
        result = project.send(self.link, [str(FIXTURE / "knowledge")])
        self.assertTrue(result["ok"])
        self.assertEqual({r["file"] for r in result["files"]}, {f.name for f in (FIXTURE / "knowledge").iterdir()})

    def test_send_skips_hidden_and_env_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp)
            for name, text in (("notes.md", "# notes"), (".env", "SECRET=1"), ("prod.env", "SECRET=2")):
                (folder / name).write_text(text, encoding="utf-8")
            result = project.send(self.link, [str(folder)])
            self.assertEqual([r["file"] for r in result["files"]], ["notes.md"])
            self.assertEqual(sorted(result["skipped"]), [".env", "prod.env"])
            self.assertNotIn(b"SECRET", b"".join(r[2] for r in FakeLink.received))
            with self.assertRaises(ValueError):
                project.send(self.link, [str(folder / ".env")])

    def test_only_phinite_upload_links_are_used(self):
        for good in ("https://mcp.dev.phinite.ai/u/gAAAA-b_c=", "https://mcp.phinite.ai/u/T/",
                     "http://localhost:8080/u/T", self.link):
            self.assertTrue(project.check_link(good))
        for bad in ("https://evil.example/u/T", "http://mcp.dev.phinite.ai/u/T", "https://phinite.ai.evil.example/u/T",
                    "https://mcp.dev.phinite.ai/upload", "https://mcp.dev.phinite.ai/u/T?x=1", "file:///etc/passwd",
                    "http://10.0.0.5/u/T"):
            with self.assertRaises(ValueError, msg=bad):
                project.check_link(bad)
        with self.assertRaises(ValueError):
            project.send("https://evil.example/u/T", [str(FIXTURE / "knowledge")])
        self.assertEqual(FakeLink.received, [])

    def test_prompt_files_must_be_inside_the_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            outside = pathlib.Path(tmp) / "secret.md"
            outside.write_text("not a prompt", encoding="utf-8")
            target = pathlib.Path(tmp) / "probe"
            shutil.copytree(FIXTURE, target)
            graph = {"masters": [{"id": "m", "prompt_file": str(outside)}]}
            with self.assertRaises(FileNotFoundError):
                project.inline_prompts(graph, target)
            graph = {"masters": [{"id": "m", "prompt_file": "../secret.md"}]}
            with self.assertRaises(FileNotFoundError):
                project.inline_prompts(graph, target)

    def test_db_env_file_copies_only_db_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = pathlib.Path(tmp) / "other.env"
            source.write_text("# other project\nDB_HOST=db.local\nexport DB_USER=svc\nOPENAI_API_KEY=sk-other-123\n"
                              "SLACK_TOKEN=xoxb-other\nDB_PASSWORD='pw-456'\n", encoding="utf-8")
            target = pathlib.Path(tmp) / "uc"
            project.scaffold(target, "myuc", db_env_file=str(source))
            copied = (target / ".env").read_text(encoding="utf-8")
            self.assertIn("DB_HOST=db.local", copied)
            self.assertIn("export DB_USER=svc", copied)
            self.assertIn("DB_PASSWORD='pw-456'", copied)
            self.assertNotIn("OPENAI_API_KEY", copied)
            self.assertNotIn("SLACK_TOKEN", copied)
            only_secrets = pathlib.Path(tmp) / "nodb.env"
            only_secrets.write_text("OPENAI_API_KEY=sk\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                project.scaffold(pathlib.Path(tmp) / "uc2", "myuc", db_env_file=str(only_secrets))

    def test_env_check_reports_names_never_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "uc"
            project.scaffold(target, database=False)
            (target / "tools-src" / "Example_Graph" / "notify.py").write_text(
                '"""Notify."""\ndef _run(inputs, env):\n    key = env.get("MYUC_API_KEY")\n'
                '    region = _env_any("MYUC_REGION", "REGION")\n    return _ok({"sent": bool(key and region)})\n',
                encoding="utf-8")
            (target / ".env").write_text("MYUC_API_KEY=value-abc-123\nMYUC_REGION=\nOTHER_SECRET=value-xyz-789\n",
                                         encoding="utf-8")
            report = project.env_check(target)
            self.assertEqual(report["needed"], ["MYUC_API_KEY", "MYUC_REGION", "REGION"])
            self.assertEqual(report["ready"], ["MYUC_API_KEY"])
            self.assertEqual(report["blank"], ["MYUC_REGION"])
            self.assertEqual(report["missing"], ["REGION"])
            self.assertEqual(report["not_needed_in_file"], ["OTHER_SECRET"])
            self.assertNotIn("value-", json.dumps(report))
            db = pathlib.Path(tmp) / "db"
            project.scaffold(db, "myuc")
            report = project.env_check(db)              # template .env: only DB_PORT has a value
            self.assertEqual(report["ready"], ["DB_PORT"])
            self.assertEqual(report["blank"], ["DB_HOST", "DB_NAME", "DB_PASSWORD", "DB_USER"])
            self.assertIn("TWILIO_AUTH_TOKEN", report["optional_helpers"])
            out = subprocess.run([sys.executable, str(pathlib.Path(project.__file__)), "env-check", str(db)],
                                 capture_output=True, text=True)
            self.assertEqual(json.loads(out.stdout)["ready"], ["DB_PORT"])

    def test_knowledge_files_stay_inside_the_project_and_skip_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "probe"
            shutil.copytree(FIXTURE, target)
            (target / "knowledge" / ".credentials.json").write_text('{"key": "secret"}', encoding="utf-8")
            (target / "knowledge" / "prod.env").write_text("KEY=secret", encoding="utf-8")
            names = [f.name for f in project.knowledge_files(["knowledge"], target)]
            self.assertEqual(names, ["probe_handbook.md"])
            with self.assertRaises(ValueError):
                project.knowledge_files(["knowledge/.credentials.json"], target)
            outside = pathlib.Path(tmp) / "personal.pdf"
            outside.write_bytes(b"%PDF-1.4")
            for path in (str(outside), "../personal.pdf"):
                with self.assertRaises(ValueError, msg=path):
                    project.knowledge_files([path], target)
            result = project.deploy(target, self.link)           # deploy uploads only the visible document
            self.assertTrue(result["ok"], result)
            uploaded = [q.get("name") for path, q, _ in FakeLink.received if path.endswith("/knowledge")]
            self.assertEqual(uploaded, ["probe_handbook.md"])

    def test_knowledge_files_rules(self):
        with self.assertRaises(ValueError):
            project.knowledge_files(["graph_spec.py"], FIXTURE)
        with self.assertRaises(FileNotFoundError):
            project.knowledge_files(["missing"], FIXTURE)

    def test_cli_reports_errors_as_json(self):
        out = subprocess.run([sys.executable, str(pathlib.Path(project.__file__)), "bundle", "/nonexistent/x"],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 1)
        self.assertFalse(json.loads(out.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
