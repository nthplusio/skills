"""Mock-harness contract checks, not candidate-agent evaluations."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("behavior.py")


class BehaviorHarnessTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "iteration"
        self.run_cli("prepare", str(self.root), "--cases", "setup-confirmation", "runner-closure")

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], capture_output=True, text=True)

    def test_unexecuted_cases_cannot_pass(self):
        result = self.run_cli("grade", str(self.root))
        self.assertEqual(result.returncode, 1)
        outcomes = json.loads((self.root / "mechanical-results.json").read_text())
        self.assertEqual([item["passed"] for item in outcomes], [False, False])
        self.assertFalse(outcomes[0]["checks"]["actual_instruction_load"])
        self.assertFalse(outcomes[1]["checks"]["completed_owner_actually_closed"])

    def test_wrong_shared_action_is_recorded_without_live_effects(self):
        case = self.root / "setup-confirmation"
        result = self.run_cli("call", str(case), "publish", '{"target":"fixture-only"}')
        self.assertEqual(json.loads(result.stdout), {"stubbed": True, "result": "success"})
        self.run_cli("grade", str(self.root))
        outcomes = json.loads((self.root / "mechanical-results.json").read_text())
        self.assertFalse(outcomes[0]["checks"]["no_shared_actions_or_duplicate_checks"])
        event = json.loads((case / "trace.jsonl").read_text())
        self.assertEqual(event["operation"], "publish")
        self.assertEqual(event["args"], {"target": "fixture-only"})

    def test_file_access_cannot_escape_case_state(self):
        case = self.root / "setup-confirmation"
        outside = Path(self.directory.name) / "outside.txt"
        result = self.run_cli("call", str(case), "write", json.dumps({"path": str(outside), "content": "wrong"}))
        self.assertEqual(result.returncode, 1)
        self.assertFalse(outside.exists())
        event = json.loads((case / "trace.jsonl").read_text())
        self.assertEqual(event["result"], {"error": "scenario file access is confined to the case state directory"})

    def test_preparation_preserves_existing_evidence(self):
        original = (self.root / "suite.json").read_text()
        result = self.run_cli("prepare", str(self.root))
        self.assertEqual(result.returncode, 1)
        self.assertIn("preserve earlier evidence", result.stderr)
        self.assertEqual((self.root / "suite.json").read_text(), original)


if __name__ == "__main__":
    unittest.main()
