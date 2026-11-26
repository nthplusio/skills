"""GitHub-native stacked PRs with local forge doubles; no live API calls or writes."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import freshness
import land
import ledger
import stacks
from decision_fixtures import assessment, authority, HEAD, BASE, REVISION, TARGET


def entry(number, position, state="OPEN", base="main"):
    return {"position": position, "pullRequest": {"number": number, "state": state, "isDraft": False,
            "baseRefName": base, "headRefName": f"layer-{number}", "headRefOid": HEAD}}


def stack_entry(number, nodes, total=None):
    position = next(n["position"] for n in nodes if n["pullRequest"]["number"] == number)
    return {"position": position, "stack": {"number": 7, "size": len(nodes), "baseRefName": "main",
            "entries": {"totalCount": total or len(nodes), "nodes": nodes}}}


LOWER, UPPER = entry(16, 1), entry(17, 2, base="layer-16")


def reply(payload, code=0):
    return lambda command, **kwargs: subprocess.CompletedProcess(command, code, json.dumps(payload), "")


class StackReadTests(unittest.TestCase):
    def read(self, payload, code=0):
        with patch.object(subprocess, "run", side_effect=reply(payload, code)):
            return stacks.stack_of("owner/repo", 17)

    def test_membership_order_and_landing_scope(self):
        top = entry(18, 3, base="layer-17")
        stack = self.read({"data": {"repository": {"pullRequest": {"stackEntry": stack_entry(17, [top, UPPER, LOWER])}}}})
        self.assertEqual([e["number"] for e in stack["entries"]], [16, 17, 18])
        self.assertEqual([e["number"] for e in stacks.below(stack, 17)], [16])
        self.assertIn("lands with #16 below", stacks.label(stack, 17))
        self.assertIn("under #18", stacks.label(stack, 17))
        # A plain --base listing finds only the bottom layer.
        self.assertEqual(stacks.missing_members([stack], {16}, "main"), {17: 7, 18: 7})
        self.assertEqual(stacks.missing_members([stack], {16}, "develop"), {})
        merged = self.read({"data": {"repository": {"pullRequest": {"stackEntry": stack_entry(17, [entry(16, 1, "MERGED"), UPPER])}}}})
        self.assertEqual(stacks.below(merged, 17), [])

    def test_unstacked_schema_absent_and_failed_reads_differ(self):
        self.assertIsNone(self.read({"data": {"repository": {"pullRequest": {"stackEntry": None}}}}))
        # A forge without the stack schema is read again for a branch stack; with no parent PR it is unstacked.
        absent = {"errors": [{"extensions": {"code": "undefinedField", "fieldName": "stackEntry"}}]}
        plain = {"data": {"repository": {"pullRequest": {"baseRef": {"associatedPullRequests": {"totalCount": 0, "nodes": []}}}}}}
        with patch.object(subprocess, "run", side_effect=[reply(absent)([]), reply(plain)([])]):
            self.assertIsNone(stacks.stack_of("owner/repo", 17))
        for payload, code in [({}, 1), ({"errors": [{"message": "rate limited"}]}, 0),
                              ({"data": {"repository": {"pullRequest": {"stackEntry": stack_entry(17, [LOWER, UPPER], total=60)}}}}, 0)]:
            with self.subTest(payload=payload):
                self.assertEqual(self.read(payload, code), {"status": "unknown"})
        self.assertEqual(stacks.label({"status": "unknown"}, 17), "Stack membership unknown")


class StackQueueTests(unittest.TestCase):
    def test_upper_layer_targeting_the_lower_branch_is_triaged_with_its_order(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("round_queue", Path(__file__).resolve().parents[1] / "scripts/queue.py")
        queue = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(queue)
        row = lambda n, created, base: {"number": n, "title": f"Layer {n}", "author": {"login": "author"},
            "createdAt": created, "isDraft": False, "reviewDecision": "APPROVED", "headRefOid": HEAD,
            "baseRefOid": BASE, "updatedAt": REVISION, "mergeStateStatus": "CLEAN", "additions": 1, "deletions": 0}
        lower, upper = row(16, "2026-11-01T00:00:00Z", "main"), row(17, "2026-11-02T00:00:00Z", "layer-16")
        stack = {"status": "stacked", "number": 7, "base": "main", "size": 2, "position": 1,
                 "entries": [{"position": 1, "number": 16, "state": "OPEN", "isDraft": False},
                             {"position": 2, "number": 17, "state": "OPEN", "isDraft": False}]}
        details = {"files": [{"path": "README.md"}], "statusCheckRollup": []}
        empty = {"failedFetches": [], "truncatedSources": [], "timeline": [], "requestedReviewers": [],
                 "pr": {"reviews": []}}
        output = io.StringIO()
        with patch.object(sys, "argv", ["queue.py", "main"]), \
                patch.object(queue, "gh_json", side_effect=[[lower], upper, details, details, lower, upper, []]), \
                patch.object(queue, "base_changes", return_value={"files": [], "commits": []}), \
                patch.object(queue, "repo_slug", return_value="owner/repo"), \
                patch.object(queue, "handled_requests", return_value=[]), \
                patch.object(queue, "stack_of", side_effect=lambda repo, n: {**stack, "position": n - 15}), \
                patch.object(queue, "collect", return_value=empty), contextlib.redirect_stdout(output):
            queue.main()
        text = output.getvalue()
        self.assertIn("2 open non-draft PR(s)", text)
        self.assertIn("#17", text)
        self.assertIn("Stack #7 · 2 of 2 on main · lands with #16 below", text)
        self.assertIn("per-PR auto-merge unavailable", text)


class StackLandingTests(unittest.TestCase):
    def run_land(self, args, *, named=(16, 17), nodes=(LOWER, UPPER), merge_ok=True, extension=True):
        writes = []
        merged = set()

        def forge(command, **kwargs):
            if command[:3] == ["gh", "pr", "view"]:
                number = int(command[3])
                payload = {"id": f"PR_{number}", "state": "MERGED" if number in merged else "OPEN",
                           "headRefOid": HEAD, "baseRefOid": BASE, "baseRefName": "main", "updatedAt": REVISION,
                           "reviewDecision": "APPROVED", "mergeStateStatus": "CLEAN", "isDraft": False}
            elif command[:2] == ["gh", "stack"] and command[2] == "--help":
                return subprocess.CompletedProcess(command, 0 if extension else 1, "", "")
            elif command[:3] == ["gh", "stack", "merge"]:
                writes.append(command)
                if merge_ok:
                    merged.update(n["pullRequest"]["number"] for n in nodes)
                return subprocess.CompletedProcess(command, 0 if merge_ok else 1, "", "" if merge_ok else "denied")
            elif command[:3] == ["gh", "pr", "merge"]:
                writes.append(command)
                return subprocess.CompletedProcess(command, 1, "", "Auto-merge is not supported for stacked pull requests.")
            elif command[:3] == ["gh", "api", "graphql"] and "stackEntry" in command[4]:
                number = int(command[-1].split("=")[1])
                payload = {"data": {"repository": {"pullRequest": {"stackEntry": stack_entry(number, list(nodes))}}}}
            elif command[:3] == ["gh", "api", "graphql"]:
                payload = {"data": {"node": {"headRefOid": HEAD, "mergeQueueEntry": None}}}
            elif command[:2] == ["gh", "api"] and "/git/ref/heads/" in command[2]:
                payload = {"ref": "refs/heads/main", "object": {"type": "commit", "sha": TARGET["sha"]}}
            else:
                raise AssertionError(command)
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

        output = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            assessments, permission = Path(tmp) / "assessments.json", Path(tmp) / "authority.json"
            assessments.write_text(json.dumps({"repository": "owner/repo", "assessments": [assessment(n) for n in named]}))
            permission.write_text(json.dumps(authority(prs=list(named))))
            argv = [*args, *(f"{n}:{HEAD}" for n in named), "--repo", "owner/repo",
                    "--authority", str(permission), "--assessments", str(assessments)]
            with patch.object(sys, "argv", ["land.py", *argv]), patch.object(subprocess, "run", side_effect=forge), \
                    patch.dict(os.environ, XDG_STATE_HOME=tmp), \
                    patch.object(land.time, "sleep"), patch.object(land, "MAX_POLLS", 2), contextlib.redirect_stdout(output):
                code = land.main()
                self.recorded = ledger.writes("owner/repo")
        return writes, output.getvalue(), code

    def test_auto_merge_is_held_before_github_rejects_it(self):
        writes, output, code = self.run_land(["--enable-auto-merge", "--stack-method", "squash"])
        self.assertEqual((writes, code), ([], 1), output)
        self.assertIn("GitHub refuses auto-merge for stacked PRs", output)

    def test_unnamed_lower_layer_or_missing_method_makes_no_write(self):
        writes, output, code = self.run_land(["--enqueue", "--stack-method", "squash"], named=(17,))
        self.assertEqual((writes, code), ([], 1), output)
        self.assertIn("would also land #16", output)
        writes, output, code = self.run_land(["--enqueue"])
        self.assertEqual((writes, code), ([], 1), output)
        self.assertIn("needs --stack-method", output)

    def test_named_layers_land_with_one_stack_command_from_the_top(self):
        writes, output, code = self.run_land(["--enqueue", "--stack-method", "squash"])
        self.assertEqual(writes, [["gh", "stack", "merge", "17", "--yes", "--squash"]], output)
        self.assertEqual(code, 0, output)
        self.assertIn("all watched PRs landed", output)
        # One command landed both layers; each is recorded at its reviewed head.
        self.assertEqual([(w["number"], w["action"], w["head"]) for w in self.recorded],
                         [(16, "stack-merge", HEAD), (17, "stack-merge", HEAD)])

    def test_failed_stack_write_and_missing_extension_hold_every_covered_layer(self):
        for options in ({"merge_ok": False}, {"extension": False}):
            with self.subTest(options=options):
                writes, output, code = self.run_land(["--enqueue", "--stack-method", "squash"], **options)
                self.assertLessEqual(len(writes), 1)
                self.assertEqual(code, 1)
                self.assertIn("#16 HELD: stack merge failed", output)
                self.assertEqual(self.recorded, [])
                self.assertIn("#17 HELD: stack merge failed", output)
        self.assertIn("gh extension install github/gh-stack", output)


class BranchStackTests(unittest.TestCase):
    """A PR based on another open PR's head branch, without `gh stack`."""

    def read(self, parents):
        pr = {"number": 3663, "state": "OPEN", "isDraft": False, "baseRefName": "feat-3657",
              "headRefName": "feat-3663", "headRefOid": HEAD, "stackEntry": None,
              "baseRef": {"associatedPullRequests": {"totalCount": len(parents), "nodes": parents}}}
        with patch.object(subprocess, "run", side_effect=reply({"data": {"repository": {"pullRequest": pr}}})):
            return stacks.stack_of("owner/repo", 3663)

    def test_a_pr_on_another_open_prs_branch_is_stacked_on_it(self):
        parent = {"number": 3657, "state": "OPEN", "isDraft": False, "baseRefName": "development",
                  "headRefName": "feat-3657", "headRefOid": BASE}
        stack = self.read([parent])
        self.assertEqual(stack["status"], "stacked")
        self.assertEqual(stack["base"], "development")
        self.assertEqual([e["number"] for e in stacks.below(stack, 3663)], [3657])
        self.assertIn("On #3657's branch feat-3657, not a gh stack", stacks.label(stack, 3663))
        self.assertIsNone(self.read([]))


class Git:
    def __init__(self, path):
        self.path = path
        self("init", "-q", "-b", "development")
        for key, value in (("user.email", "a@example.test"), ("user.name", "Author")):
            self("config", key, value)

    def __call__(self, *args):
        result = subprocess.run(["git", *args], cwd=self.path, capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)
        return result.stdout.strip()

    def commit(self, files, message):
        for name, text in files.items():
            (self.path / name).write_text(text)
            self("add", name)
        self("commit", "-qm", message)
        return self("rev-parse", "HEAD")


class RetargetFreshnessTests(unittest.TestCase):
    """#3663 on #3657's branch; #3657 squash-merges and GitHub retargets #3663 to development."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        previous = os.getcwd()
        os.chdir(directory.name)  # the freshness tree check runs git in the repository root
        self.addCleanup(os.chdir, previous)
        self.git = git = Git(Path(directory.name))
        git.commit({"shared.py": "x = 1\n"}, "base")
        git("checkout", "-q", "-b", "feat-3657")
        self.parent = git.commit({"parent.py": "p = 1\n"}, "parent work")
        git("checkout", "-q", "-b", "feat-3663")
        self.head = git.commit({"child.py": "c = 1\n"}, "child work")
        git("checkout", "-q", "development")

    def squash_parent(self, also=None):
        """Squash-merge the parent into development, plus an optional unrelated development commit."""
        if also:
            self.git.commit(also, "development work")
        self.git("merge", "-q", "--squash", "feat-3657")
        return self.git.commit({}, "parent (#3657)") if self.git("status", "--porcelain") else None

    def classify(self, tip):
        saved = assessment(3663, head=self.head, base=self.parent,
                           evidence_inputs={**assessment()["evidence_inputs"], "target": {"ref": "feat-3657", "sha": self.parent}})
        live = {"head": self.head, "base": tip, "forge": REVISION, "conflicting": False,
                "target": {"ref": "development", "sha": tip}}
        with patch.object(freshness, "_api", side_effect=AssertionError("no forge read")):
            return freshness.classify(saved, live, policy=saved["evidence_inputs"]["policy"], repo="owner/repo",
                                      number=3663, writes=[])

    def test_the_same_change_on_the_new_base_carries(self):
        verdict = self.classify(self.squash_parent(also={"docs.md": "d\n"}))
        self.assertIsInstance(verdict, freshness.Benign, verdict)
        self.assertIn("retargeted from feat-3657 to development", verdict.reasons[0])
        self.assertIn("makes the same change the round reviewed", verdict.reasons[0])

    def test_a_different_merged_result_holds(self):
        # development already carries part of the child's change, so merging the head now changes less.
        verdict = self.classify(self.squash_parent(also={"child.py": "c = 1\n"}))
        self.assertIsInstance(verdict, freshness.Stale)
        self.assertIn("changes something other than what the round reviewed", verdict.message())
        # And a conflict with the new base holds too.
        self.git("checkout", "-q", "-b", "other", "development~1")
        tip = self.git.commit({"child.py": "c = 2\n"}, "conflicting")
        self.assertIn("conflicts with development", self.classify(tip).message())

    def test_the_retarget_events_and_the_dismissed_stack_approval_are_benign(self):
        after = lambda kind, **extra: {"event": kind, "created_at": "2026-11-11T21:00:00Z",
                                       "actor": {"login": "IL-AKingcaidOuedraogo", "type": "User"}, **extra}
        rows = [after("automatic_base_change_succeeded"), after("removed_from_stack"),
                after("review_dismissed", dismissed_review={"review_id": 5, "dismissal_message": None})]
        with patch.object(freshness, "_api", return_value=rows):
            stale, benign = freshness._discussion_move(REVISION, "2026-11-11T21:05:00Z", "owner/repo", 3663, [])
        self.assertEqual(stale, [])
        self.assertIn("GitHub dismissing an approval on the automatic retarget", benign[0])
        # Without a retarget, a dismissal is still a person acting.
        with patch.object(freshness, "_api", return_value=rows[2:]):
            stale, _ = freshness._discussion_move(REVISION, "2026-11-11T21:05:00Z", "owner/repo", 3663, [])
        self.assertIn("review_dismissed by IL-AKingcaidOuedraogo", stale[0])

    def test_unknown_mergeability_after_a_base_move_is_read_again_before_it_holds(self):
        saved = assessment(17)
        live = {"head": HEAD, "base": "c" * 40, "forge": REVISION, "conflicting": None,
                "target": {"ref": "main", "sha": "c" * 40}}
        reads = {"files": [{"filename": "src/app.py"}], "compare": {"status": "ahead", "files": [{"filename": "docs/x.md"}]},
                 "pulls/17": {"head": {"sha": HEAD}, "mergeable": True, "mergeable_state": "clean"}}
        api = lambda path, paginate=False: next(v for k, v in reads.items() if k in path)
        with patch.object(freshness, "_api", side_effect=api), patch.object(freshness.time, "sleep") as slept:
            verdict = freshness.classify(saved, live, policy=saved["evidence_inputs"]["policy"], repo="owner/repo",
                                         number=17, writes=[])
        self.assertIsInstance(verdict, freshness.Benign, verdict)
        self.assertEqual(slept.call_count, 1)
        reads["pulls/17"] = {"head": {"sha": HEAD}, "mergeable": None}
        with patch.object(freshness, "_api", side_effect=api), patch.object(freshness.time, "sleep") as slept:
            verdict = freshness.classify(saved, live, policy=saved["evidence_inputs"]["policy"], repo="owner/repo",
                                         number=17, writes=[])
        self.assertIn("has not reported the PR mergeable", verdict.message())
        self.assertEqual(slept.call_count, len(freshness.MERGEABLE_WAITS))


if __name__ == "__main__":
    unittest.main()
