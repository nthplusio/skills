"""reapprove.py against real temporary git repositories; no forge calls."""
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
import ledger
import reapprove
from decision_fixtures import assessment, REVISION
from review_config import resolve

LIVE = {"base": "c" * 40, "forge": "2026-11-12T09:00:00Z", "target": {"ref": "main", "sha": "c" * 40}}


class Repository:
    """A repository with `main` and a PR branch `feature`; A is the approved head."""

    def __init__(self, path):
        self.path = path
        self.git("init", "-q", "-b", "main")
        for key, value in (("user.email", "a@example.test"), ("user.name", "Author")):
            self.git("config", key, value)
        self.commit("shared.py", "x = 1\n", "base")
        self.git("checkout", "-q", "-b", "feature")
        self.approved = self.commit("feature.py", "y = 1\n", "feature")

    def git(self, *args, check=True):
        result = subprocess.run(["git", *args], cwd=self.path, capture_output=True, text=True)
        if check and result.returncode:
            raise AssertionError(result.stderr)
        return result.stdout.strip()

    def commit(self, name, text, message):
        (self.path / name).write_text(text)
        self.git("add", name)
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD")

    def on(self, branch, name, text):
        """Commit on another branch and come back to feature."""
        self.git("checkout", "-q", branch)
        sha = self.commit(name, text, f"{branch}: {name}")
        self.git("checkout", "-q", "feature")
        return sha

    def merge(self, branch):
        self.git("merge", "-q", "--no-ff", "--no-edit", branch)
        return self.git("rev-parse", "HEAD")

    def head(self):
        return self.git("rev-parse", "HEAD")

    def decide(self):
        return reapprove.base_only(self.approved, self.head(), self.git("rev-parse", "main"))


class BaseOnlyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        previous = os.getcwd()
        os.chdir(directory.name)  # reapprove.py runs git in the repository root, as from a round
        self.addCleanup(os.chdir, previous)
        self.repo = Repository(Path(directory.name))

    def assertBaseOnly(self, expected, reason=""):
        result = self.repo.decide()
        self.assertEqual(result["base_only"], expected, result["reason"])
        self.assertIn(reason, result["reason"])
        return result

    def test_one_clean_base_merge_is_base_only(self):
        self.repo.on("main", "other.py", "z = 1\n")
        merge = self.repo.merge("main")
        result = self.assertBaseOnly(True, "1 clean base merge")
        self.assertEqual([s["commit"] for s in result["steps"]], [merge])
        self.assertEqual(result["steps"][0]["merge_tree"], result["steps"][0]["tree"])
        self.assertIn("clean, tree matches", "\n".join(reapprove.describe({**result, "approved": "a", "head": "h"})))

    def test_two_successive_base_merges_are_base_only(self):
        self.repo.on("main", "other.py", "z = 1\n")
        self.repo.merge("main")
        self.repo.on("main", "third.py", "w = 1\n")
        self.repo.merge("main")
        self.assertBaseOnly(True, "2 clean base merge")

    def test_a_conflict_resolved_by_hand_is_not_base_only(self):
        self.repo.on("main", "feature.py", "y = 2\n")
        self.repo.git("merge", "-q", "--no-ff", "--no-edit", "main", check=False)  # conflicts
        (self.repo.path / "feature.py").write_text("y = 3\n")
        self.repo.git("add", "feature.py")
        self.repo.git("commit", "-q", "--no-edit")
        result = self.assertBaseOnly(False, "conflicts")
        self.assertIsNone(result["steps"][0]["merge_tree"])

    def test_a_change_slipped_into_a_clean_merge_is_not_base_only(self):
        self.repo.on("main", "other.py", "z = 1\n")
        self.repo.merge("main")
        (self.repo.path / "feature.py").write_text("y = 99\n")
        self.repo.git("commit", "-q", "-a", "--amend", "--no-edit")
        self.assertBaseOnly(False, "differs from a clean merge")

    def test_a_merge_and_an_author_commit_is_not_base_only(self):
        self.repo.on("main", "other.py", "z = 1\n")
        self.repo.merge("main")
        self.repo.commit("feature.py", "y = 2\n", "more work")
        self.assertBaseOnly(False, "author commit")

    def test_a_rebase_onto_the_new_base_is_not_base_only(self):
        self.repo.on("main", "other.py", "z = 1\n")
        self.repo.git("rebase", "-q", "main")
        self.assertBaseOnly(False, "not in the live head's history")

    def test_merging_a_branch_that_is_not_the_base_is_not_base_only(self):
        self.repo.git("branch", "other", "main")
        self.repo.on("other", "other.py", "z = 1\n")
        self.repo.merge("other")
        self.assertBaseOnly(False, "not on the base branch")

    def test_an_unmoved_head_or_unknown_commit_is_not_base_only(self):
        self.assertBaseOnly(False, "has not moved")
        result = reapprove.base_only("e" * 40, self.repo.head(), self.repo.git("rev-parse", "main"))
        self.assertFalse(result["base_only"])
        self.assertIn("not available locally", result["reason"])


class CarryTests(unittest.TestCase):
    A, H = "a" * 40, "d" * 40
    BASE_ONLY = {"base_only": True, "reason": "1 clean base merge(s)", "approved": A, "head": H,
                 "steps": [{"commit": H, "second_parent": "c" * 40, "merge_tree": "t" * 40, "tree": "t" * 40}]}

    def carry(self, earlier, result=None, discussion=([], []), policy=None):
        return reapprove.carry(earlier, result or self.BASE_ONLY, LIVE, policy=policy or resolve(".")["revision"],
                               discussion=discussion, at=REVISION)

    def test_a_clean_assessment_moves_to_the_new_head_and_keeps_its_review(self):
        earlier = assessment()
        carried = self.carry(earlier, discussion=([], ["GitHub dismissing this round's approval on a push"]))
        ledger.validate_assessment(carried)
        self.assertEqual((carried["head"], carried["base"]), (self.H, LIVE["base"]))
        self.assertEqual((carried["assessed_at"], carried["decisions"]), (earlier["assessed_at"], earlier["decisions"]))
        self.assertEqual(carried["evidence_inputs"]["forge"], LIVE["forge"])
        self.assertEqual(carried["evidence_inputs"]["target"], LIVE["target"])
        self.assertEqual((carried["carried"]["from_head"], carried["carried"]["commits"]), (self.A, [self.H]))
        for text in (self.A, self.H, "git merge-tree --write-tree"):
            self.assertIn(text, carried["provenance"])
        self.assertEqual(ledger.unresolved(carried), [])

    def test_nothing_changed_or_unreviewed_is_carried(self):
        cases = [
            ("not base-only", dict(result={**self.BASE_ONLY, "base_only": False, "reason": "an author commit"}),
             "not base-only"),
            ("another head", dict(earlier=assessment(head="b" * 40)), "not the carried-from head"),
            ("policy", dict(policy="other-revision"), "review policy changed"),
            ("a person spoke", dict(discussion=(["reviewed by alex (CHANGES_REQUESTED) since the assessment"], [])),
             "discussion"),
        ]
        for name, changes, message in cases:
            with self.subTest(name):
                earlier = changes.pop("earlier", assessment())
                with self.assertRaisesRegex(ValueError, message):
                    self.carry(earlier, **changes)

    def test_unresolved_decisions_are_carried_and_still_block(self):
        carried = self.carry(assessment(kind="code", owner="Author"))
        self.assertEqual([d["owner"] for d in ledger.unresolved(carried)], ["Author"])

    def test_a_carried_record_must_name_its_check_and_heads(self):
        carried = self.carry(assessment())
        for broken in ({**carried, "carried": {**carried["carried"], "head": "e" * 40}},
                       {**carried, "carried": {**carried["carried"], "commits": []}},
                       {k: v for k, v in carried.items() if k != "provenance"}):
            with self.subTest(broken=broken.get("carried")), self.assertRaisesRegex(ValueError, "carried requires"):
                ledger.validate_assessment(broken)



class CarryCommandTests(unittest.TestCase):
    """`reapprove.py --carry` against a real repository, with the forge reads recorded."""
    LATER = "2026-11-12T09:00:00Z"

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        previous = os.getcwd()
        os.chdir(directory.name)
        self.addCleanup(os.chdir, previous)
        self.repo = Repository(Path(directory.name))
        self.state = Path(directory.name) / ".state"

    def run_carry(self, timeline=(), read=None):
        """Carry the assessment at the feature commit to the live head; returns (code, stdout, stderr)."""
        head, tip = self.repo.head(), self.repo.git("rev-parse", "main")
        item = assessment(17, head=self.repo.approved, base=self.repo.git("rev-parse", "main~0"))
        if head == self.repo.approved:  # nothing pushed: the base did not move either
            item["base"] = tip
            item["evidence_inputs"] = {**item["evidence_inputs"], "target": {"ref": "main", "sha": tip}}
        self.other = assessment(18)  # another PR in the round's file
        path = self.repo.path / "assessments.json"
        path.write_text(json.dumps({"repository": "owner/repo", "assessments": [item, self.other]}))
        pr = {"head": {"sha": head}, "base": {"ref": "main", "sha": tip}, "updated_at": self.LATER,
              "mergeable": True, "mergeable_state": "clean"}
        api = lambda route, paginate=False: list(timeline) if "timeline" in route else pr
        out, err = io.StringIO(), io.StringIO()
        argv = ["reapprove.py", "17", "--repo", "owner/repo", "--carry", str(path), *(["--read", read] if read else [])]
        with patch.object(sys, "argv", argv), patch.dict(os.environ, XDG_STATE_HOME=str(self.state)), \
                patch.object(reapprove, "_api", side_effect=api), patch.object(freshness, "_api", side_effect=api), \
                patch.object(reapprove, "target_state", return_value={"ref": "main", "sha": tip}), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = reapprove.main()
        return code, out.getvalue(), err.getvalue()

    def saved(self):
        """The round's assessments file, by PR number."""
        bundle = json.loads((self.repo.path / "assessments.json").read_text())
        return {a["number"]: a for a in bundle["assessments"]}

    def test_a_carry_saves_into_the_round_file_and_keeps_every_other_pr(self):
        # Live: the carried bundle went to stdout, and the round overwrote its file with it once.
        self.repo.on("main", "other.py", "z = 1\n")
        head = self.repo.merge("main")
        code, out, err = self.run_carry()
        self.assertEqual(code, 0, err)
        saved = self.saved()
        self.assertEqual(sorted(saved), [17, 18])
        self.assertEqual((saved[17]["head"], saved[17]["carried"]["from_head"]), (head, self.repo.approved))
        self.assertEqual(saved[18], self.other)
        self.assertIn(f"#17 carried from {self.repo.approved[:9]} to {head[:9]}", out)
        # A refused carry leaves the file as it was.
        self.repo.commit("test_feature.py", "assert True\n", "add a test")
        code, out, err = self.run_carry()
        self.assertEqual(code, 1, err)
        self.assertEqual(self.saved()[17]["head"], self.repo.approved)

    def test_a_carry_names_the_assessment_it_carried_from_not_an_approval(self):
        self.repo.on("main", "other.py", "z = 1\n")
        self.repo.merge("main")
        code, out, err = self.run_carry()
        self.assertEqual(code, 0, err)
        self.assertIn("1 clean base merge(s) since the saved assessment", err)
        self.assertIn(f"head at the saved assessment (A): {self.repo.approved}", err)
        self.assertNotIn("approval", err)

    def test_a_base_only_merge_carries_an_assessment_the_round_never_approved(self):
        self.repo.on("main", "other.py", "z = 1\n")
        head = self.repo.merge("main")
        code, out, err = self.run_carry()
        self.assertEqual(code, 0, err)
        carried = self.saved()[17]
        self.assertEqual((carried["head"], carried["carried"]["from_head"]), (head, self.repo.approved))
        self.assertEqual(carried["evidence_inputs"]["forge"], self.LATER)
        self.assertIn("1 base merge(s)", carried["carried"]["reason"])

    def test_a_code_push_is_refused_naming_the_files_it_changed(self):
        self.repo.on("main", "other.py", "z = 1\n")
        self.repo.merge("main")
        self.repo.commit("test_feature.py", "assert True\n", "add a test")
        code, out, err = self.run_carry()
        self.assertEqual((code, out), (1, ""), err)
        self.assertIn("not carried: not base-only", err)
        self.assertIn("Changed beyond the base: test_feature.py", err)
        self.assertNotIn("other.py", err.split("Changed beyond the base:")[1])

    def test_a_person_s_comment_carries_only_after_the_round_read_it(self):
        comment = [{"event": "commented", "created_at": "2026-11-12T08:00:00Z",
                    "actor": {"login": "alex", "type": "User"}, "user": {"login": "alex", "type": "User"}}]
        code, out, err = self.run_carry(comment)
        self.assertEqual(code, 1, err)
        self.assertIn("commented by alex", err)
        self.assertIn("--read", err)
        code, out, err = self.run_carry(comment, read="alex asks about naming; no change to the verdict")
        self.assertEqual(code, 0, err)
        carried = self.saved()[17]
        self.assertEqual((carried["head"], carried["carried"]["commits"]), (self.repo.approved, []))
        self.assertEqual(carried["evidence_inputs"]["forge"], self.LATER)
        self.assertIn("read by the round: commented by alex", carried["provenance"])
        self.assertIn("no change to the verdict", carried["provenance"])


if __name__ == "__main__":
    unittest.main()
