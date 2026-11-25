"""authority.py's public CLI and ledger.check_authority; temporary repositories only, no forge calls."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ledger

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "authority.py"


class AuthorityTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.tmp = Path(directory.name)
        self.root = self.tmp / "repository"
        self.root.mkdir()
        (self.tmp / "scope.json").write_text("[3614, 3620]\n")

    def profile(self, round_):
        path = self.root / ".nthplusio-skills" / "review.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"schema_version": 1, "round": round_}))

    def run_cli(self, *args, ok=True):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, args)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0 if ok else 2, result.stdout + result.stderr)
        return result.stdout if ok else result.stderr

    def init(self, answers, ok=True):
        (self.tmp / "answers.json").write_text(json.dumps(answers))
        out = self.tmp / "authority.json"
        out.unlink(missing_ok=True)
        text = self.run_cli("init", "--repo", "owner/repo", "--scope", self.tmp / "scope.json", "--answers",
                            self.tmp / "answers.json", "--root", self.root, "--out", out, ok=ok)
        return (json.loads(out.read_text()) if ok else None), text

    def test_answers_and_scope_round_trip_with_their_sources(self):
        words = "review with approvals, and dismiss bot reviews you verified"
        record, shown = self.init({"level": "review", "approvals": True, "policies": {"dismiss-review": "auto"},
                                   "instruction": words})
        self.assertEqual((record["repository"], record["prs"], record["level"], record["approvals"]),
                         ("owner/repo", [3614, 3620], "review", True))
        self.assertEqual(record["policies"], {"auto-merge-on-approval": "auto", "auto-merge-sweep": "auto",
                                              "dismiss-review": "auto"})
        self.assertEqual(record["sources"], {"level": "answer", "approvals": "answer", "policies": {
            "auto-merge-on-approval": "default", "auto-merge-sweep": "default", "dismiss-review": "answer"}})
        self.assertEqual(record["instruction"], words)
        self.assertTrue(record["possible_landing"])
        # The record it wrote is the one the write helpers accept, auto-merge included.
        for action in ("comment", "approve", "enable-auto-merge", "sweep-auto-merge", "dismiss"):
            ledger.check_authority(record, "owner/repo", 3614, action)
        with self.assertRaises(ValueError):
            ledger.check_authority(record, "owner/repo", 3699, "comment")
        self.assertEqual(self.run_cli("show", self.tmp / "authority.json"), shown)
        self.assertIn("Work level: review (from your answer).", shown)
        self.assertIn("auto-merge-sweep: yes, without asking (from the default).", shown)

    def test_profile_fills_unanswered_settings_and_the_instruction_names_it(self):
        self.profile({"level": "moderate", "approvals": True, "policies": {"dismiss-review": "never"}})
        record, shown = self.init({})
        self.assertEqual((record["level"], record["approvals"], record["policies"]["dismiss-review"]),
                         ("moderate", True, "never"))
        self.assertEqual(record["sources"]["level"], "profile")
        self.assertEqual(record["sources"]["policies"]["dismiss-review"], "profile")
        self.assertEqual(record["sources"]["policies"]["auto-merge-sweep"], "default")
        self.assertIn(".nthplusio-skills/review.json", record["instruction"])
        self.assertIn("dismiss-review: never (from the review profile", shown)
        record, _ = self.init({"policies": {"auto-merge-sweep": "ask"}, "instruction": "ask before sweeping"})
        self.assertEqual((record["level"], record["policies"]["auto-merge-sweep"], record["sources"]["policies"]["auto-merge-sweep"]),
                         ("moderate", "ask", "answer"))

    def test_an_answer_the_level_cannot_support_is_refused(self):
        for answers in ({"level": "assess", "approvals": True, "instruction": "x"},
                        {"level": "review", "approvals": False, "policies": {"auto-merge-sweep": "auto"}, "instruction": "x"},
                        {"level": "review", "policies": {"dismiss-bot-review": "auto"}, "instruction": "x"},
                        {"level": "review"}):
            with self.subTest(answers=answers):
                _, error = self.init(answers, ok=False)
                self.assertNotIn("Traceback", error)
                self.assertFalse((self.tmp / "authority.json").exists())

    def test_questions_list_only_what_the_profile_and_answers_leave_open(self):
        every = self.run_cli("questions", "--root", self.root)
        for key in ("level:", "approvals:", "auto-merge-on-approval:", "auto-merge-sweep:", "dismiss-review:"):
            self.assertIn(key, every)
        self.assertIn("Recommended: ask.", every)
        self.profile({"level": "review", "approvals": True, "policies": {"auto-merge-sweep": "auto"}})
        (self.tmp / "answers.json").write_text(json.dumps({"policies": {"dismiss-review": "never"}, "instruction": "x"}))
        left = self.run_cli("questions", "--root", self.root, "--answers", self.tmp / "answers.json")
        self.assertEqual([line.split(":")[0] for line in left.splitlines() if "Recommended" in line],
                         ["auto-merge-on-approval"])
        self.assertIn("From the review profile", left)
        self.assertIn("level review; approvals yes; auto-merge-sweep auto", left)

    def test_never_refuses_ask_names_the_question_and_a_grant_allows_one_pr(self):
        record, _ = self.init({"level": "review", "approvals": True, "instruction": "review with approvals",
                               "policies": {"auto-merge-sweep": "never"}})
        with self.assertRaisesRegex(ValueError, "auto-merge-sweep policy is never"):
            ledger.check_authority(record, "owner/repo", 3614, "sweep-auto-merge")
        with self.assertRaisesRegex(ValueError, "dismiss-review policy is ask. Ask: .*may the round dismiss"):
            ledger.check_authority(record, "owner/repo", 3614, "dismiss")
        self.run_cli("grant", self.tmp / "authority.json", "--pr", 3614, "--action", "dismiss",
                     "--instruction", "dismiss the bot's review on #3614")
        granted = json.loads((self.tmp / "authority.json").read_text())
        ledger.check_authority(granted, "owner/repo", 3614, "dismiss")
        with self.assertRaisesRegex(ValueError, "dismiss-review policy is ask"):
            ledger.check_authority(granted, "owner/repo", 3620, "dismiss")
        self.assertIn('Granted: dismiss on #3614 ("dismiss the bot\'s review on #3614")',
                      self.run_cli("show", self.tmp / "authority.json"))
        # A grant cannot override never, reach outside scope, or add a level action.
        for pr, action in ((3614, "sweep-auto-merge"), (3699, "dismiss")):
            self.run_cli("grant", self.tmp / "authority.json", "--pr", pr, "--action", action, "--instruction", "x", ok=False)
        self.run_cli("grant", self.tmp / "authority.json", "--pr", 3614, "--action", "push-fix", "--instruction", "x", ok=False)

    def test_level_caps_hold_and_hand_edits_or_old_files_are_refused(self):
        record, _ = self.init({"level": "review", "approvals": True, "policies": {"dismiss-review": "auto"},
                               "instruction": "review with approvals"})
        for action in ("push-fix", "update-branch", "delegate"):
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, "outside the review level"):
                ledger.check_authority(record, "owner/repo", 3614, action)
        edited = {**record, "actions": [*record["actions"], "push-fix"]}
        with self.assertRaisesRegex(ValueError, "edited by hand"):
            ledger.check_authority(edited, "owner/repo", 3614, "push-fix")
        old = {"repository": "owner/repo", "prs": [3614], "level": "review", "approvals": True,
               "actions": ["dismiss"], "instruction": "old", "possible_landing": True}
        with self.assertRaisesRegex(ValueError, "regenerate it with authority.py init"):
            ledger.check_authority(old, "owner/repo", 3614, "dismiss")


if __name__ == "__main__":
    unittest.main()
