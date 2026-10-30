import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor


SKILL = Path(__file__).resolve().parents[1]
GH = '''#!/usr/bin/env python3
import json, os, subprocess, sys, time
args = sys.argv[1:]
if args == ["auth", "status"]:
    sys.exit(0)
if args[:1] == ["api"]:
    assert args[1] == "repos/target/product/pulls/17/reviews?per_page=100"
    assert "--paginate" in args and "--slurp" in args
    print(os.environ["FORGE_REVIEWS"])
    sys.exit(37 if os.environ.get("FAIL_FETCH") else 0)
assert args[:2] == ["pr", "list"], "unsupported or mutating command"
repo = args[args.index("--repo") + 1]
assert repo in ("target/product", "other/product")
assert args[args.index("--base") + 1] == "staging"
state = args[args.index("--state") + 1]
if state == "merged":
    assert args[args.index("--search") + 1] == "merged:2026-10-01T00:00:00Z..2026-10-30T00:00:00Z"
time.sleep(0.02)
if os.environ.get("FAIL_FETCH"):
    print('[{"number": 999}]')
    sys.exit(37)
rows = json.loads(os.environ["FORGE_ROWS"])
if repo == "other/product":
    rows = [dict(row, number=row["number"] + 100) for row in rows]
rows = rows[:int(args[args.index("--limit") + 1])]
if "--jq" in args:
    subprocess.run(["jq", args[args.index("--jq") + 1]], input=json.dumps(rows), text=True, check=True)
else:
    print(json.dumps(rows))
'''

ROWS = [
    {"number": 32, "createdAt": "2026-10-04", "mergedAt": "2026-10-06", "isDraft": False},
    {"number": 7, "createdAt": "2026-10-01", "mergedAt": "2026-10-02", "isDraft": True},
    {"number": 19, "createdAt": "2026-10-03", "mergedAt": "2026-10-05", "isDraft": False},
]


class ListTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pr digest tests ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.installed = self.root / "source checkout" / "installed skill"
        shutil.copytree(SKILL, self.installed)
        subprocess.run(["git", "init", "-q", str(self.root / "source checkout")], check=True)
        subprocess.run(["git", "-C", str(self.root / "source checkout"), "remote", "add", "origin",
                        "https://github.com/source/skills"], check=True)
        self.target = self.root / "target checkout"
        subprocess.run(["git", "init", "-q", str(self.target)], check=True)
        subprocess.run(["git", "-C", str(self.target), "remote", "add", "origin",
                        "https://github.com/target/product"], check=True)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        (self.bin / "gh").write_text(GH)
        (self.bin / "gh").chmod(0o755)
        self.scratch = self.root / "scratch"
        self.scratch.mkdir()

    def run_list(self, kind, *, drafts=False, repo="target/product", rows=ROWS, limit=4, fail=False):
        args = ["bash", str(self.installed / f"scripts/find_{kind}_prs.sh")]
        if drafts:
            args.append("--include-drafts")
        args += [repo, "staging"]
        if kind == "merged":
            args += ["2026-10-01T00:00:00Z", "2026-10-30T00:00:00Z"]
        args.append(str(limit))
        env = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}",
               "TMPDIR": str(self.scratch), "FORGE_ROWS": json.dumps(rows)}
        if fail:
            env["FAIL_FETCH"] = "1"
        return subprocess.run(args, env=env, cwd=self.installed, capture_output=True, text=True)

    def test_installed_helpers_bind_repository_and_preserve_scope(self):
        for kind, drafts, expected in [("merged", False, [7, 19, 32]),
                                        ("open", False, [19, 32]), ("open", True, [7, 19, 32])]:
            with self.subTest(kind=kind, drafts=drafts):
                result = self.run_list(kind, drafts=drafts)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual([row["number"] for row in json.loads(result.stdout)], expected)

    def test_saturation_before_filtering_is_not_a_complete_or_empty_inventory(self):
        for kind in ["merged", "open"]:
            with self.subTest(kind=kind):
                result = self.run_list(kind, rows=[dict(row, isDraft=True) for row in ROWS], limit=3)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertIn("coverage may be incomplete", result.stderr)

    def test_fetch_failure_and_empty_success_remain_distinct(self):
        for kind in ["merged", "open"]:
            with self.subTest(kind=kind):
                result = self.run_list(kind, fail=True)
                self.assertEqual(result.returncode, 37)
                self.assertEqual(result.stdout, "")
                result = self.run_list(kind, rows=[])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), [])

    def test_search_cap_cannot_be_bypassed_with_larger_limit(self):
        result = self.run_list("merged", limit=1001)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")

    def test_review_history_recipe_preserves_later_comment_only_objections(self):
        pages = [[{"state": "DISMISSED", "body": "Stale approval", "submitted_at": "2026-10-01"},
                  {"state": "COMMENTED", "body": "Looks reasonable", "submitted_at": "2026-10-02"}],
                 [{"state": "COMMENTED", "body": "Do not merge", "submitted_at": "2026-10-03"}]]
        text = (self.installed / "references/review-status.md").read_text()
        recipe = text.split("```bash\n", 1)[1].split("```", 1)[0]
        recipe = recipe.replace("<owner/repo>", "target/product").replace("<n>", "17")
        env = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}", "FORGE_REVIEWS": json.dumps(pages)}
        result = subprocess.run(["bash", "-c", recipe], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([r["body"] for r in json.loads(result.stdout)], ["Looks reasonable", "Do not merge"])
        result = subprocess.run(["bash", "-c", recipe], env={**env, "FAIL_FETCH": "1"},
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)

    def test_concurrent_repositories_keep_their_own_results(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda repo: self.run_list("open", repo=repo),
                                    ["target/product", "other/product"]))
        for result, expected in zip(results, [[19, 32], [119, 132]]):
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([row["number"] for row in json.loads(result.stdout)], expected)
        self.assertEqual(list(self.scratch.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
