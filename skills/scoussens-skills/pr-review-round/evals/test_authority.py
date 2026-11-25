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
        record, shown = self.init({"level": "review", "approvals": True, "policies": {"dismiss-bot-review": "auto"},
                                   "instruction": words})
        self.assertEqual((record["repository"], record["prs"], record["level"], record["approvals"]),
                         ("owner/repo", [3614, 3620], "review", True))
        self.assertEqual(record["policies"], {"auto-merge-on-approval": "auto", "auto-merge-sweep": "auto",
                                              "dismiss-bot-review": "auto", "dismiss-human-review": "ask",
                                              "own-pr-landing": "ask", "reapprove-base-only": "auto"})
        self.assertEqual(record["sources"], {"level": "answer", "approvals": "answer", "mode": "default", "policies": {
            "auto-merge-on-approval": "default", "auto-merge-sweep": "default", "dismiss-bot-review": "answer",
            "dismiss-human-review": "default", "own-pr-landing": "default", "reapprove-base-only": "default"}})
        self.assertEqual(record["instruction"], words)
        self.assertTrue(record["possible_landing"])
        # The record it wrote is the one the write helpers accept, auto-merge included.
        for action in ("comment", "approve", "enable-auto-merge", "sweep-auto-merge", "dismiss-bot", "reapprove"):
            ledger.check_authority(record, "owner/repo", 3614, action)
        # Letting the round dismiss bots does not let it dismiss people.
        with self.assertRaisesRegex(ValueError, "dismiss-human-review policy is ask"):
            ledger.check_authority(record, "owner/repo", 3614, "dismiss-human")
        with self.assertRaises(ValueError):
            ledger.check_authority(record, "owner/repo", 3699, "comment")
        self.assertEqual(self.run_cli("show", self.tmp / "authority.json"), shown)
        self.assertIn("Work level: review (from your answer).", shown)
        self.assertIn("auto-merge-sweep: yes, without asking (from the default).", shown)

    def test_profile_fills_unanswered_settings_and_the_instruction_names_it(self):
        self.profile({"level": "moderate", "approvals": True, "policies": {"dismiss-human-review": "never"}})
        record, shown = self.init({})
        self.assertEqual((record["level"], record["approvals"], record["policies"]["dismiss-human-review"]),
                         ("moderate", True, "never"))
        self.assertEqual(record["sources"]["level"], "profile")
        self.assertEqual(record["sources"]["policies"]["dismiss-human-review"], "profile")
        self.assertEqual(record["sources"]["policies"]["auto-merge-sweep"], "default")
        self.assertIn(".nthplusio-skills/review.json", record["instruction"])
        self.assertIn("dismiss-human-review: never (from the review profile", shown)
        record, _ = self.init({"policies": {"auto-merge-sweep": "ask"}, "instruction": "ask before sweeping"})
        self.assertEqual((record["level"], record["policies"]["auto-merge-sweep"], record["sources"]["policies"]["auto-merge-sweep"]),
                         ("moderate", "ask", "answer"))

    def test_an_answer_the_level_cannot_support_is_refused(self):
        for answers in ({"level": "assess", "approvals": True, "instruction": "x"},
                        {"level": "review", "approvals": False, "policies": {"auto-merge-sweep": "auto"}, "instruction": "x"},
                        # The kind dismiss-bot-review and dismiss-human-review replaced.
                        {"level": "review", "policies": {"dismiss-review": "auto"}, "instruction": "x"},
                        {"level": "review"}):
            with self.subTest(answers=answers):
                _, error = self.init(answers, ok=False)
                self.assertNotIn("Traceback", error)
                self.assertFalse((self.tmp / "authority.json").exists())

    def test_questions_list_only_what_the_profile_and_answers_leave_open(self):
        every = self.run_cli("questions", "--root", self.root)
        for key in ("level:", "approvals:", "auto-merge-on-approval:", "auto-merge-sweep:", "dismiss-bot-review:",
                    "dismiss-human-review:", "own-pr-landing:", "reapprove-base-only:"):
            self.assertIn(key, every)
        self.assertIn("Recommended: ask.", every)
        self.profile({"level": "review", "approvals": True, "policies": {"auto-merge-sweep": "auto"}})
        (self.tmp / "answers.json").write_text(json.dumps({"policies": {"dismiss-bot-review": "never", "dismiss-human-review": "ask"}, "instruction": "x"}))
        left = self.run_cli("questions", "--root", self.root, "--answers", self.tmp / "answers.json")
        self.assertEqual([line.split(":")[0] for line in left.splitlines() if "Recommended" in line],
                         ["auto-merge-on-approval", "own-pr-landing", "reapprove-base-only", "mode"])
        self.assertIn("From the review profile", left)
        self.assertIn("level review; approvals yes; auto-merge-sweep auto", left)

    def test_run_mode_round_trips_and_is_asked_only_when_unanswered(self):
        asked = self.run_cli("questions", "--root", self.root)
        self.assertIn("mode: Should the round stop after one pass (once)", asked)
        self.assertIn("Recommended: once.", asked)
        record, shown = self.init({"level": "review", "instruction": "review them"})
        self.assertEqual((record["mode"], record["sources"]["mode"]), ("once", "default"))
        self.assertNotIn("until", record)
        self.assertIn("Run mode: once, one pass, then report (from the default).", shown)
        self.assertNotIn("subscribe", shown)
        record, shown = self.init({"level": "review", "mode": "settle", "instruction": "keep going until it settles"})
        self.assertEqual((record["mode"], record["sources"]["mode"]), ("settle", "answer"))
        self.assertIn("Run mode: settle, keep working until no scoped PR has an action left", shown)
        self.assertIn("lets the round subscribe to events on these PRs, or schedule its own wake-ups", shown)
        self.assertEqual(self.run_cli("show", self.tmp / "authority.json"), shown)
        record, shown = self.init({"level": "review", "mode": "watch", "window": "2026-12-01T18:00:00+01:00",
                                   "instruction": "watch until 6pm"})
        self.assertEqual((record["mode"], record["until"]), ("watch", "2026-12-01T17:00:00Z"))
        self.assertIn("Run mode: watch until 2026-12-01T17:00:00Z", self.run_cli("show", self.tmp / "authority.json"))
        record, _ = self.init({"level": "review", "mode": "watch", "window": "4h", "instruction": "watch for 4 hours"})
        self.assertRegex(record["until"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        # A run mode authorizes no write.
        self.assertEqual(record["actions"], ["comment", "request-changes"])
        (self.tmp / "answers.json").write_text(json.dumps({"mode": "settle", "instruction": "settle"}))
        left = self.run_cli("questions", "--root", self.root, "--answers", self.tmp / "answers.json")
        self.assertNotIn("mode:", left)
        for answers in ({"mode": "watch", "instruction": "x"}, {"mode": "settle", "window": "4h", "instruction": "x"},
                        {"mode": "forever", "instruction": "x"},
                        {"mode": "watch", "window": "2020-01-01T00:00:00Z", "instruction": "x"},
                        {"mode": "watch", "window": "tomorrow", "instruction": "x"}):
            with self.subTest(answers=answers):
                _, error = self.init(answers, ok=False)
                self.assertIn("answers.", error)

    def test_never_refuses_ask_names_the_question_and_a_grant_allows_one_pr(self):
        record, _ = self.init({"level": "review", "approvals": True, "instruction": "review with approvals",
                               "policies": {"auto-merge-sweep": "never"}})
        with self.assertRaisesRegex(ValueError, "auto-merge-sweep policy is never"):
            ledger.check_authority(record, "owner/repo", 3614, "sweep-auto-merge")
        with self.assertRaisesRegex(ValueError, "dismiss-bot-review policy is ask. Ask: .*may the round dismiss"):
            ledger.check_authority(record, "owner/repo", 3614, "dismiss-bot")
        self.run_cli("grant", self.tmp / "authority.json", "--pr", 3614, "--action", "dismiss-bot",
                     "--instruction", "dismiss the bot's review on #3614")
        granted = json.loads((self.tmp / "authority.json").read_text())
        ledger.check_authority(granted, "owner/repo", 3614, "dismiss-bot")
        with self.assertRaisesRegex(ValueError, "dismiss-bot-review policy is ask"):
            ledger.check_authority(granted, "owner/repo", 3620, "dismiss-bot")
        with self.assertRaisesRegex(ValueError, "dismiss-human-review policy is ask"):
            ledger.check_authority(granted, "owner/repo", 3614, "dismiss-human")
        self.assertIn('Granted: dismiss-bot on #3614 ("dismiss the bot\'s review on #3614")',
                      self.run_cli("show", self.tmp / "authority.json"))
        # A grant cannot override never, reach outside scope, or add a level action.
        for pr, action in ((3614, "sweep-auto-merge"), (3699, "dismiss-bot")):
            self.run_cli("grant", self.tmp / "authority.json", "--pr", pr, "--action", action, "--instruction", "x", ok=False)
        self.run_cli("grant", self.tmp / "authority.json", "--pr", 3614, "--action", "push-fix", "--instruction", "x", ok=False)

    def test_reapproving_after_base_merges_is_its_own_decision_and_never_leaves_fresh_approval_alone(self):
        record, _ = self.init({"level": "review", "approvals": True, "instruction": "approve, but re-review base merges",
                               "policies": {"reapprove-base-only": "never"}})
        with self.assertRaisesRegex(ValueError, "reapprove-base-only policy is never"):
            ledger.check_authority(record, "owner/repo", 3614, "reapprove")
        ledger.check_authority(record, "owner/repo", 3614, "approve")
        self.run_cli("grant", self.tmp / "authority.json", "--pr", 3614, "--action", "reapprove", "--instruction", "x",
                     ok=False)
        record, _ = self.init({"level": "review", "approvals": True, "instruction": "review with approvals"})
        self.assertEqual(record["policies"]["reapprove-base-only"], "auto")
        ledger.check_authority(record, "owner/repo", 3614, "reapprove")
        # Without approvals the round asks, naming the question.
        record, _ = self.init({"level": "review", "approvals": False, "instruction": "review only"})
        with self.assertRaisesRegex(ValueError, "reapprove-base-only policy is ask. Ask: .*approve it again"):
            ledger.check_authority(record, "owner/repo", 3614, "reapprove")

    def test_level_caps_hold_and_hand_edits_or_old_files_are_refused(self):
        record, _ = self.init({"level": "review", "approvals": True, "policies": {"dismiss-bot-review": "auto"},
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
        # A file written before dismiss-review was split into a bot kind and a person kind.
        split = {"version": 2, "repository": "owner/repo", "prs": [3614], "level": "review", "approvals": True,
                 "policies": {"auto-merge-on-approval": "auto", "auto-merge-sweep": "auto", "dismiss-review": "auto",
                              "reapprove-base-only": "auto"},
                 "instruction": "old", "actions": ["comment", "request-changes", "approve", "enable-auto-merge",
                                                   "sweep-auto-merge", "dismiss", "reapprove"],
                 "possible_landing": True, "grants": []}
        for action in ("dismiss", "dismiss-bot", "comment"):
            with self.subTest(action=action), \
                    self.assertRaisesRegex(ValueError, "mode for every decision kind; regenerate it with authority.py init"):
                ledger.check_authority(split, "owner/repo", 3614, action)
        (self.tmp / "split.json").write_text(json.dumps(split))
        self.assertIn("regenerate it with authority.py init",
                      self.run_cli("grant", self.tmp / "split.json", "--pr", 3614, "--action", "dismiss-bot",
                                   "--instruction", "x", ok=False))


if __name__ == "__main__":
    unittest.main()
