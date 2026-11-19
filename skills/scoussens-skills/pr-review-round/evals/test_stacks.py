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
        self.assertIsNone(self.read({"errors": [{"extensions": {"code": "undefinedField", "fieldName": "stackEntry"}}]}))
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


if __name__ == "__main__":
    unittest.main()
