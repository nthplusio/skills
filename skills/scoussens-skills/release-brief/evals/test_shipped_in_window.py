"""Run with python3 -B -m unittest discover -s <this directory> -v."""

import json
import os
from pathlib import Path
import shutil
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
    if os.environ.get("GH_STUB_FAIL"):
        sys.exit(1)
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

    def run_script(self, prs, *args, exit_code=0):
        result = subprocess.run(["bash", str(SCRIPT), *args], cwd=self.work, capture_output=True, text=True,
                                env={**self.env, "GH_STUB_PRS": json.dumps(prs)})
        self.assertEqual(result.returncode, exit_code, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def listings(self):
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        return [call for call in calls if call[:2] == ["pr", "list"]]

    def test_single_branch_counts_every_merge_as_product_work(self):
        out = self.run_script({"main": ["#7|2026-01-13|main|add-export|Add export"]},
                              "--since", "2026-01-12", "--production", "main")
        work = between(out, "Product work (merged to 'main'; deployment unverified):", "COMMITS")
        self.assertIn("#7|2026-01-13|main|add-export|Add export", work)
        self.assertIn("count: 1", work)
        self.assertNotIn("Promotions", out)
        self.assertNotIn("A merge into it is a release", out)

    def test_missing_refs_never_mean_identical(self):
        out = self.run_script({}, "--since", "2026-01-12", "--production", "missing-production",
                              "--integration", "missing-integration", exit_code=1)
        self.assertIn("UNKNOWN", out)
        self.assertNotIn("IDENTICAL", out)
        self.assertNotIn("Nothing is queued", out)

    def test_failed_fetch_cannot_certify_stale_equal_refs(self):
        self.push("staging")
        git(self.work, "remote", "set-url", "origin", str(self.origin / "missing"))
        out = self.run_script({}, "--since", "2026-01-12", "--production", "main",
                              "--integration", "staging", exit_code=1)
        self.assertIn("UNKNOWN", out)
        self.assertNotIn("IDENTICAL", out)
        self.assertNotIn("Nothing is queued", out)

    def test_failed_diff_with_valid_refs_is_not_equality(self):
        self.push("staging")
        stub = self.log.parent / "bin" / "git"
        stub.write_text(f"#!{sys.executable}\n"
                        "import os, sys\n"
                        "if sys.argv[1] == 'diff': sys.exit(37)\n"
                        f"os.execv({shutil.which('git')!r}, ['git', *sys.argv[1:]])\n")
        stub.chmod(0o755)
        out = self.run_script({}, "--since", "2026-01-12", "--production", "main",
                              "--integration", "staging", exit_code=1)
        self.assertIn("UNKNOWN", out)
        self.assertNotIn("IDENTICAL", out)
        self.assertNotIn("Nothing is queued", out)

    def test_equal_and_different_trees_are_not_deployment_evidence(self):
        self.push("staging")
        args = ("--since", "2026-01-12", "--production", "main", "--integration", "staging")
        out = self.run_script({}, *args)
        self.assertIn("IDENTICAL", out)
        self.assertIn("Deployment: UNVERIFIED", out)
        (self.work / "feature").write_text("export")
        git(self.work, "add", "feature")
        git(self.work, "commit", "-qm", "Add export")
        self.push("staging")
        out = self.run_script({}, *args)
        self.assertIn("DIVERGED", out)
        self.assertIn("feature", out)
        self.assertIn("Deployment: UNVERIFIED", out)
        self.assertNotIn("IDENTICAL", out)

    def test_release_uses_explicit_boundaries_not_one_parent(self):
        git(self.work, "tag", "v1")
        for subject in ("ABC-11 first change", "ABC-12 second change", "ABC-13 third change"):
            git(self.work, "commit", "-q", "--allow-empty", "-m", subject)
        git(self.work, "tag", "-a", "v2", "-m", "Second release")
        git(self.work, "commit", "-q", "--allow-empty", "-m", "ABC-14 outside release")
        out = self.run_script({}, "--release", "v2", "--previous", "v1", "--production", "main")
        commits = between(out, "COMMITS", "CANDIDATE TRACKER IDS")
        for subject in ("ABC-11 first change", "ABC-12 second change", "ABC-13 third change"):
            self.assertIn(subject, commits)
        self.assertIn("count: 3", commits)
        self.assertNotIn("Initial commit", commits)
        self.assertNotIn("ABC-14", out)
        self.assertFalse(self.log.exists(), "release mode must not query PRs by date")

    def test_invalid_or_ambiguous_release_boundaries_fail(self):
        git(self.work, "tag", "v1")
        git(self.work, "commit", "-q", "--allow-empty", "-m", "Next release")
        git(self.work, "tag", "v2")
        for args, code in [
            (("--release", "v2"), 2),
            (("--release", "missing", "--previous", "v1"), 1),
            (("--release", "v2", "--previous", "missing"), 1),
            (("--release", "v1", "--previous", "v2"), 1),
            (("--release", "v2", "--previous", "v1", "--since", "2026-01-12"), 2),
        ]:
            with self.subTest(args=args):
                out = self.run_script({}, *args, exit_code=code)
                self.assertNotIn("(none)", out)

    def test_failed_forge_query_is_unknown_not_empty(self):
        self.env["GH_STUB_FAIL"] = "1"
        out = self.run_script({}, "--since", "2026-01-12", "--production", "main")
        prs = between(out, "PULL REQUESTS", "COMMITS")
        self.assertIn("UNKNOWN", prs)
        self.assertNotIn("(none)", prs)

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
