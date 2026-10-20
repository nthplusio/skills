from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class PickerPortalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.skill = self.root / "installed 'skill"
        shutil.copytree(Path(__file__).resolve().parents[1], self.skill)
        self.project = self.root / "project"
        self.project.mkdir()
        self.inventory = self.project / "inventory.json"
        self.calls = self.project / "calls"
        executable = self.root / "amp"
        executable.write_text(
            '#!/usr/bin/env node\n'
            'const fs = require("node:fs");\n'
            'if (process.argv.slice(2).join(" ") !== "skills list --json") process.exit(9);\n'
            'fs.appendFileSync("calls", "discovery\\n");\n'
            'setTimeout(() => process.stdout.write(fs.readFileSync("inventory.json", "utf8")), 150);\n'
        )
        executable.chmod(0o755)
        self.env = {**os.environ, "HOME": str(self.root), "PORT": "0",
                    "PUBLIC_URL": "https://picker.example.test/",
                    "PATH": str(self.root) + os.pathsep + os.environ["PATH"]}
        key = hashlib.sha256(str(self.project).encode()).hexdigest()[:16]
        self.state = self.root / ".cache/amp/picking-skills" / key
        self.data = {"skills": [{
            "name": "review", "description": "Audit authentication.",
            "baseDir": (self.root / 'hosted skills/review@rev "two"').as_uri(),
            "source": "global-workspace", "body": "BODY MUST NOT APPEAR",
        }], "errors": []}
        self.inventory.write_text(json.dumps(self.data))
        self.start_server()
        self.addCleanup(self.stop_server)

    def start_server(self):
        self.server = subprocess.Popen(
            ["node", str(self.skill / "scripts/server.mjs"), str(self.project)],
            cwd=self.skill, env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        for _ in range(200):
            try:
                info = json.loads((self.state / "service.json").read_text())
                self.base = "http://127.0.0.1:" + str(info["port"])
                self.get("/health")
                return
            except (OSError, ValueError):
                if self.server.poll() is not None:
                    self.fail(self.server.stderr.read().decode())
                time.sleep(0.025)
        self.fail("Picker server did not become ready")

    def stop_server(self):
        self.server.terminate()
        self.server.wait(timeout=5)
        self.server.stderr.close()

    def get(self, path, headers=None):
        try:
            response = urlopen(Request(self.base + path, headers=headers or {}), timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read().decode()

    def launch(self, query="", message=None):
        args = ["node", str(self.skill / "scripts/launch.mjs"), query]
        if message is not None:
            path = self.root / (hashlib.sha256(message.encode()).hexdigest() + ".txt")
            path.write_bytes(message.encode())
            args += ["--message-file", str(path)]
        return subprocess.run(args, cwd=self.project, env=self.env,
                              text=True, capture_output=True, timeout=10)

    def test_refresh_uses_project_inventory_and_never_serves_bodies_or_stale_metadata(self):
        status, headers, payload = self.get("/api/skills")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertNotIn("BODY MUST NOT APPEAR", payload)
        skill = json.loads(payload)["skills"][0]
        self.assertEqual(skill["directory"], str(self.root / 'hosted skills/review@rev "two"'))
        self.data["skills"][0]["description"] = "Edited description. </script> $& ```"
        self.data["errors"] = ["warning"]
        self.inventory.write_text(json.dumps(self.data))
        refreshed = json.loads(self.get("/api/skills")[2])
        self.assertEqual(refreshed["skills"][0]["description"], self.data["skills"][0]["description"])
        self.assertEqual(refreshed["warnings"], 1)
        for invalid in [None, {"skills": []}, {"skills": [{"name": "incomplete"}], "errors": []}]:
            self.inventory.write_text(json.dumps(invalid))
            self.assertEqual(self.get("/api/skills")[0], 502)
        self.inventory.write_text('{"skills": [], "errors": []}')
        self.assertEqual(json.loads(self.get("/api/skills")[2])["skills"], [])

    def test_concurrent_reads_share_discovery_but_later_refresh_is_fresh(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.get("/api/skills")[0], range(4)))
        self.assertEqual(results, [200] * 4)
        self.assertEqual(self.calls.read_text().splitlines(), ["discovery"])
        self.get("/api/skills")
        self.assertEqual(len(self.calls.read_text().splitlines()), 2)

    def test_concurrent_launches_reuse_service_and_keep_each_message_private_and_intact(self):
        messages = ['  Use <skill> for A.\r\nThen <skill> again. $& 界  ', 'Use <skill> for B.']
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda message: self.launch("code review", message), messages))
        ids = []
        for result, message in zip(results, messages):
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertLess(len(result.stdout.encode()), 200)
            self.assertNotIn(message, result.stdout)
            id = re.search(r'https://picker.example.test/#([a-f0-9-]{36})', result.stdout)[1]
            ids.append(id)
            saved = json.loads(self.get("/api/requests/" + id)[2])
            self.assertEqual(saved, {"query": "code review", "message": message})
            path = self.state / "requests" / (id + ".json")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(set(ids)), 2)
        self.assertFalse(self.calls.exists(), "Launch must not rediscover skills")
        self.stop_server()
        self.start_server()
        self.assertEqual(json.loads(self.get("/api/requests/" + ids[0])[2])["message"], messages[0])
        expired = self.state / "requests" / (ids[0] + ".json")
        yesterday = time.time() - 86401
        os.utime(expired, (yesterday, yesterday))
        self.assertEqual(self.get("/api/requests/" + ids[0])[0], 410)
        self.assertFalse(expired.exists())

    def test_only_narrow_read_routes_are_available_and_navigation_from_amp_is_allowed(self):
        status, headers, html = self.get("/", {"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(status, 200)
        self.assertEqual(headers["x-amp-review-widget"], "off")
        self.assertNotIn("Audit authentication.", html)
        self.assertEqual(self.get("/api/skills", {"Origin": "https://unrelated.test"})[0], 403)
        for path in ["/api/requests", "/api/skills?cwd=/tmp", "/SKILL.md", "/../../etc/passwd"]:
            self.assertEqual(self.get(path)[0], 404)
        result = self.launch(message="This task has no placeholder.")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("<skill> placeholder", result.stderr)


if __name__ == "__main__":
    unittest.main()
