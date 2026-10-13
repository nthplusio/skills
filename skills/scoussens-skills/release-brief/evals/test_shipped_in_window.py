"""Run with python3 -B -m unittest discover -s <this directory> -v."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "shipped-in-window.sh"

# Stands in for gh: logs every call, and for `pr list` prints the lines the real
# gh would print for that --base after the script's --jq filter.
GH_STUB = """
import json, os, sys
args = sys.argv[1:]
with open(os.environ["GH_STUB_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
if args[:2] == ["auth", "status"]:
    sys.exit(0)
if args[:2] == ["pr", "list"]:
    base = args[args.index("--base") + 1] if "--base" in args else ""
    print("\\n".join(json.loads(os.environ["GH_STUB_PRS"]).get(base, [])))
    sys.exit(0)
sys.exit(1)
"""


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
                   cwd=cwd, check=True, capture_output=True)


def between(text, start, end):
    return text.split(start, 1)[1].split(end, 1)[0]


class ShippedInWindow(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.log = root / "gh.log"
        stub = root / "bin" / "gh"
        stub.parent.mkdir()
        stub.write_text(f"#!{sys.executable}\n{GH_STUB}")
        stub.chmod(0o755)
        self.origin = root / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(self.origin)], check=True)
        self.work = root / "work"
        self.work.mkdir()
        git(self.work, "init", "-q")
        git(self.work, "commit", "-q", "--allow-empty", "-m", "Initial commit")
        git(self.work, "remote", "add", "origin", str(self.origin))
        self.push("main")
        self.env = {**os.environ, "PATH": f"{stub.parent}{os.pathsep}{os.environ['PATH']}",
                    "GH_STUB_LOG": str(self.log)}

    def push(self, branch):
        git(self.work, "push", "-q", "origin", f"HEAD:{branch}")
        git(self.work, "fetch", "-q", "origin")

    def run_script(self, prs, *args):
        result = subprocess.run(["bash", str(SCRIPT), *args], cwd=self.work, capture_output=True, text=True,
                                env={**self.env, "GH_STUB_PRS": json.dumps(prs)})
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def listings(self):
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        return [call for call in calls if call[:2] == ["pr", "list"]]

    def test_single_branch_counts_every_merge_as_product_work(self):
        out = self.run_script({"main": ["#7|2026-01-13|main|add-export|Add export"]},
                              "--since", "2026-01-12", "--production", "main")
        work = between(out, "Product work (merged to 'main'; each merge is also a release):", "COMMITS")
        self.assertIn("#7|2026-01-13|main|add-export|Add export", work)
        self.assertIn("count: 1", work)
        self.assertNotIn("Promotions", out)

    def test_two_branch_splits_changes_from_promotions(self):
        self.push("staging")
        out = self.run_script({"staging": ["#8|2026-01-13|staging|add-import|Add import"],
                               "main": ["#9|2026-01-14|main|staging|Release"]},
                              "--since", "2026-01-12", "--production", "main", "--integration", "staging")
        work = between(out, "Product work (merged to 'staging'):", "Promotions")
        promotions = between(out, "Promotions (merged to 'main')", "COMMITS")
        self.assertIn("#8|", work)
        self.assertNotIn("#9|", work)
        self.assertIn("#9|", promotions)

    def test_every_listing_filters_merge_date_on_the_server(self):
        self.push("staging")
        self.run_script({}, "--since", "2026-01-12", "--until", "2026-01-16",
                        "--production", "main", "--integration", "staging")
        self.run_script({}, "--since", "2026-01-12", "--production", "main", "--integration", "staging")
        searches = []
        for call in self.listings():
            self.assertIn("--base", call)
            searches.append(call[call.index("--search") + 1])
        self.assertEqual(searches, ["merged:2026-01-12T00:00:00Z..2026-01-16T23:59:59Z"] * 2
                         + ["merged:>=2026-01-12T00:00:00Z"] * 2)

    def test_ticket_ids_come_from_lowercase_branch_names_but_not_versions(self):
        out = self.run_script({"main": ["#7|2026-01-13|main|abc-12-fix-login|Fix login",
                                        "#10|2026-01-13|main|doorbell-0.1.1|Bump the plugin"]},
                              "--since", "2026-01-12", "--production", "main")
        ids = out.split("CANDIDATE TRACKER IDS", 1)[1]
        self.assertIn("ABC-12", ids)
        self.assertNotIn("DOORBELL-0", ids)


if __name__ == "__main__":
    unittest.main()
