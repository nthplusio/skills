import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor


SKILL = Path(__file__).resolve().parents[1]


def fixture(number=17):
    def review(login, kind, state):
        return {"user": {"login": login, "type": kind}, "state": state,
                "body": "Do not merge" if state == "COMMENTED" else "",
                "submitted_at": "2026-10-03T02:00:00Z", "html_url": f"https://example.test/{login}"}

    def comment(login, body):
        return {"author": {"login": login}, "body": body, "path": "src/example.py", "line": 7}

    comments = [comment("custom-reviewer", "**[Unsafe input]** _(source: bugs, style)_")]
    comments += [comment("reviewer", f"follow-up {i}") for i in range(99)]
    tail = [comment("author", "Fixed in the follow-up commit"), comment("reviewer", "Confirmed")]
    threads = [{"id": "T1", "isResolved": False, "isOutdated": False,
                "comments": {"nodes": comments, "totalCount": 102}}]
    threads += [{"id": "T2", "isResolved": True, "comments": {
        "nodes": [comment("reviewer", "Second finding")], "totalCount": 1}}]

    def thread_page(nodes, more):
        return {"data": {"repository": {"pullRequest": {"reviewThreads": {
            "nodes": nodes, "pageInfo": {"hasNextPage": more, "endCursor": "next" if more else None}}}}}}

    commits = [{"oid": sha, "authors": [{"login": author}],
                "committedDate": "2026-10-04T01:00:00Z", "messageHeadline": "fixup! input"}
               for sha, author in [("own", "author"), ("foreign", "upstream"), ("own2", "author")]]
    return {
        "repo": "target/product",
        "pr": {"number": number, "title": f"PR {number}", "author": {"login": "author"},
               "createdAt": "2026-10-01T00:00:00Z", "mergedAt": "2026-10-05T00:00:00Z",
               "additions": 200, "reviews": [], "comments": [], "files": [], "commits": commits},
        "reviews": [[review("custom-reviewer[bot]", "Bot", "DISMISSED"),
                     review("author", "User", "COMMENTED")],
                    [review("reviewer", "User", "CHANGES_REQUESTED")]],
        "threads": [thread_page(threads, True), thread_page([{
            "id": "T3", "isResolved": False, "comments": {
                "nodes": [comment("reviewer", "Last-page finding")], "totalCount": 1}}], False)],
        "thread-comments:T1": [{"data": {"node": {"comments": {
            "nodes": nodes, "pageInfo": {"hasNextPage": more, "endCursor": "next" if more else None}}}}}
                               for nodes, more in [(comments, True), (tail, False)]],
        "timeline": [[{"event": "ready_for_review", "created_at": "2026-10-02T00:00:00Z"},
                      {"event": "review_dismissed"}], [{"event": "head_ref_force_pushed"}]],
        "counts": [{"data": {"repository": {"pullRequest": {
            "comments": {"totalCount": 0}, "commits": {"totalCount": 3}, "files": {"totalCount": 0}}}}}],
        "check-runs:own": [{"check_runs": [{"name": "lint", "conclusion": "success"},
                                          {"name": "build", "conclusion": "success"}]},
                           {"check_runs": [{"name": "unit", "conclusion": "failure"}]}],
        "check-runs:foreign": [{"check_runs": []}],
        "check-runs:own2": [{"check_runs": [{"name": "unit", "conclusion": "success"}]}],
    }


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pr detail tests ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.installed = self.root / "source skills" / "pr-detail"
        shutil.copytree(SKILL, self.installed)
        subprocess.run(["git", "init", "-q", str(self.root / "source skills")], check=True)
        subprocess.run(["git", "-C", str(self.root / "source skills"), "remote", "add", "origin",
                        "https://github.com/source/skills"], check=True)
        self.target = self.root / "target checkout"
        subprocess.run(["git", "init", "-q", str(self.target)], check=True)
        subprocess.run(["git", "-C", str(self.target), "remote", "add", "origin",
                        "https://github.com/target/product"], check=True)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        shutil.copyfile(SKILL / "evals/fixture_gh.py", self.bin / "gh")
        (self.bin / "gh").chmod(0o755)
        self.scratch = self.root / "tmp"
        self.scratch.mkdir()

    def environment(self, data, name="fixture"):
        path = self.root / f"{name}.json"
        path.write_text(json.dumps(data))
        return {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}",
                "FORGE_FIXTURE": str(path), "TMPDIR": str(self.scratch), "SKILL_DIR": str(self.installed)}

    def gather(self, data):
        result = subprocess.run(["bash", str(self.installed / "scripts/gather_pr.sh"),
                                 data["repo"], str(data["pr"]["number"])],
                                cwd=self.installed, env=self.environment(data), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def metrics(self, data):
        result = subprocess.run(["python3", str(self.installed / "scripts/metrics.py")],
                                input=json.dumps(data), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_all_pages_and_actor_attribution(self):
        data = self.gather(fixture())
        self.assertEqual([t["id"] for t in data["threads"]], ["T1", "T2", "T3"])
        self.assertEqual(len(data["threads"][0]["comments"]["nodes"]), 102)
        self.assertEqual(len(data["timeline"]), 3)
        self.assertEqual(len(data["checkRuns"][0]["runs"]), 3)
        metrics = self.metrics(data)
        self.assertTrue(metrics["evidence"]["complete"])
        self.assertEqual(metrics["review"]["botRounds"], 1)
        self.assertEqual(metrics["review"]["botReviewStates"], ["DISMISSED"])
        self.assertEqual(metrics["review"]["authorReplyCount"], 1)
        self.assertEqual([r["who"] for r in metrics["review"]["humanReviews"]], ["reviewer"])
        self.assertEqual(metrics["review"]["unclassifiedLogins"], [])
        self.assertEqual(metrics["findings"]["authorEngaged"], 1)
        self.assertEqual(metrics["findings"]["byCategory"], {"untagged": 2, "bugs": 1, "style": 1})
        self.assertEqual(metrics["churn"]["commitsByAuthor"], 2)
        self.assertEqual(metrics["churn"]["commitsByOthers"], 1)
        self.assertEqual(metrics["churn"]["forcePushes"], 1)
        self.assertEqual(metrics["ci"]["commitsWithFailingChecks"], 1)

    def test_failures_survive_metrics_without_manufacturing_clean_ci(self):
        data = fixture()
        data["fail"] = ["reviews", "timeline", "thread-comments:T1", "check-runs:foreign", "counts"]
        gathered = self.gather(data)
        metrics = self.metrics(gathered)
        self.assertEqual(set(metrics["evidence"]["failedFetches"]), {
            "reviews", "timeline", "thread-comments:T1", "check-runs:foreign", "collection-counts"})
        self.assertFalse(metrics["evidence"]["complete"])
        self.assertIsNone(metrics["review"]["mergedWithNoReview"])
        self.assertEqual(metrics["ci"]["commitsChecked"], 2)
        self.assertEqual(len(gathered["threads"][0]["comments"]["nodes"]), 100)

    def test_capped_collections_and_ci_sample_are_disclosed(self):
        data = fixture()
        commit = data["pr"]["commits"][0]
        data["pr"]["commits"] = [copy.deepcopy(commit) for _ in range(41)]
        counts = data["counts"][0]["data"]["repository"]["pullRequest"]
        counts.update({"commits": {"totalCount": 44}, "files": {"totalCount": 2}})
        metrics = self.metrics(self.gather(data))
        self.assertEqual(set(metrics["evidence"]["truncatedSources"]), {
            "commits", "files", "check-runs:commits-after-40"})
        self.assertEqual(metrics["ci"]["commitsChecked"], 40)
        self.assertFalse(metrics["evidence"]["complete"])

    def test_concurrent_assessments_do_not_share_scratch_or_evidence(self):
        recipe = (self.installed / "SKILL.md").read_text().split("```bash\n", 1)[1].split("\n```", 1)[0]

        def assess(number):
            command = recipe.replace("<owner/repo>", "target/product").replace("<N>", str(number))
            command += '\nprintf "%s\\n" "$RUN_DIR"'
            result = subprocess.run(["bash", "-e", "-c", command], cwd=self.target,
                                    env=self.environment(fixture(number), str(number)),
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return Path(result.stdout.strip())

        with ThreadPoolExecutor(max_workers=2) as pool:
            directories = list(pool.map(assess, [17, 29]))
        self.assertNotEqual(*directories)
        self.assertEqual([json.loads((d / "metrics.json").read_text())["pr"]["number"]
                          for d in directories], [17, 29])
        self.assertEqual([json.loads((d / "pr.json").read_text())["pr"]["number"]
                          for d in directories], [17, 29])
        self.assertEqual(set(self.scratch.iterdir()), set(directories))


if __name__ == "__main__":
    unittest.main()
