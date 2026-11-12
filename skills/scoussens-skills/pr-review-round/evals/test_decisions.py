import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ledger
from decision_fixtures import assessment, bundle, HEAD, BASE, REVISION


class DecisionTests(unittest.TestCase):
    def test_audit_cases_have_distinct_owners_and_unblocks(self):
        for number, kind, owner in [(3397, "code", "Author"), (3341, "evidence", "Operator"),
                                     (3345, "reviewer-incomplete", "Reviewer")]:
            with self.subTest(number=number):
                item = assessment(number, kind, owner)
                ledger.validate_assessment(item)
                self.assertEqual([(d["kind"], d["owner"]) for d in ledger.unresolved(item)], [(kind, owner)])
                self.assertTrue(item["decisions"][0]["unblock"])
                self.assertNotIn("posted_action", item["decisions"][0])

    def test_clean_assessments_persist_even_without_findings(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, XDG_STATE_HOME=tmp):
            ledger.record_assessment("round-1", assessment(), "owner/repo")
            self.assertEqual(ledger.open_findings("owner/repo"), {})
            self.assertEqual(ledger.heads("owner/repo"), {17: HEAD})
            self.assertEqual(ledger.assessments("owner/repo")[17]["base"], BASE)

    def test_changed_evidence_invalidates_unchanged_code_and_waiver_is_scoped(self):
        item = assessment(kind="evidence", owner="Operator")
        inputs = {**item["evidence_inputs"], "issues": "successful-apply-evidence"}
        self.assertFalse(ledger.assessment_current(item, HEAD, BASE, inputs))
        decision = item["decisions"][0]
        decision["waiver"] = {"actor": "Owner", "source": "https://example.test/owner-decision", "at": REVISION,
                              "scope": "Accept apply log instead of actual counts for this criterion",
                              "criterion": decision["criterion"]}
        item["evidence_inputs"] = inputs
        self.assertEqual(ledger.unresolved(item), [])
        changed = copy.deepcopy(item)
        changed["decisions"][0]["criterion"] = "Demonstrate a different workflow"
        with self.assertRaisesRegex(ValueError, "exact criterion"):
            ledger.validate_assessment(changed)
        self.assertFalse(ledger.assessment_current(item, "c" * 40, BASE, inputs))
        self.assertEqual(item["decisions"][0]["waiver"], decision["waiver"])

    def test_incomplete_review_and_code_cannot_be_waived_or_masked_by_ready(self):
        for kind in ("code", "reviewer-incomplete"):
            item = assessment(kind=kind)
            item["decisions"][0]["waiver"] = {"actor": "Owner", "source": "url", "at": REVISION,
                                              "scope": "criterion only", "criterion": "Demonstrate the live workflow"}
            with self.assertRaisesRegex(ValueError, "cannot substitute"):
                ledger.validate_assessment(item)
        item = assessment(kind="code")
        item["decisions"].append({**assessment()["decisions"][0], "id": "ready"})
        with self.assertRaisesRegex(ValueError, "cannot mask"):
            ledger.validate_assessment(item)

    def test_clearance_requires_current_assessment_and_no_unresolved_decisions(self):
        for kind in ("code", "evidence", "decision", "reviewer-incomplete"):
            with self.assertRaisesRegex(ValueError, "unresolved decisions"):
                ledger.check_clearance(bundle(assessment(kind=kind)), "owner/repo", 17, HEAD, BASE, REVISION)
        self.assertEqual(ledger.check_clearance(bundle(), "owner/repo", 17, HEAD, BASE, REVISION)["number"], 17)

    def test_nonblocking_code_advice_is_not_a_landing_blocker(self):
        item = assessment(kind="code")
        item["decisions"][0]["severity"] = "non-blocking"
        self.assertEqual(ledger.unresolved(item), [])
        ledger.check_clearance(bundle(item), "owner/repo", 17, HEAD, BASE, REVISION)

    def test_changed_repository_reference_invalidates_clearance_at_unchanged_head(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                Path("rules.md").write_text("Initial repository convention")
                Path("custom.json").write_text(json.dumps({"schema_version": 1, "references": {
                    "conventions": {"files": ["rules.md"]}}}))
                item = assessment()
                item["evidence_inputs"]["policy"] = ledger.review_config(".", "custom.json")["revision"]
                saved = {**bundle(item), "review_config": "custom.json"}
                ledger.check_clearance(saved, "owner/repo", 17, HEAD, BASE, REVISION)
                Path("rules.md").write_text("A newly required compatibility check")
                with self.assertRaisesRegex(ValueError, "review policy changed"):
                    ledger.check_clearance(saved, "owner/repo", 17, HEAD, BASE, REVISION)
                self.assertFalse(ledger.assessment_current(item, HEAD, BASE, {
                    **item["evidence_inputs"], "policy": ledger.review_config(".", "custom.json")["revision"]}))
            finally:
                os.chdir(previous)
