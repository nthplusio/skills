"""Validate the shared-settings scenario corpus; this does not execute an agent."""

import json
from pathlib import Path
import unittest


SKILL = Path(__file__).resolve().parents[1]
LIBRARY = SKILL.parent


class SettingsContractTests(unittest.TestCase):
    def test_scenarios_have_environments_and_observable_assertions(self):
        corpus = json.loads((SKILL / "evals/settings-scenarios.json").read_text())
        self.assertEqual(corpus["kind"], "instruction-scenarios-not-results")
        cases = corpus["scenarios"]
        ids = [case["id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue({"known-chat-no-runtime", "known-caller-refresh",
                         "public-only-no-approval", "html-unavailable",
                         "missing-required-companion", "manual-questionnaire-no-wake",
                         "static-questionnaire-no-companions", "automatic-needs-real-wake",
                         "narrow-lookup-not-contribution"}.issubset(ids))
        for case in cases:
            with self.subTest(case=case["id"]):
                for key in ("environment", "prompt", "expected_output"):
                    self.assertTrue(case[key].strip())
                for key in ("skills", "assertions", "forbidden_actions"):
                    self.assertTrue(case[key])
                    self.assertTrue(all(isinstance(item, str) and item.strip() for item in case[key]))
                for name in case["skills"]:
                    self.assertTrue((LIBRARY / name / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
