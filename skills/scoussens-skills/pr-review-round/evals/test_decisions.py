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
from decision_fixtures import assessment, bundle, HEAD, BASE, REVISION, TARGET

LIVE = {"head": HEAD, "base": BASE, "forge": REVISION, "target": TARGET, "conflicting": False}


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
            # A boundary keeps only what was recorded before it: this record is stamped with the time of this run.
            self.assertEqual(ledger.heads("owner/repo", before="2999-01-01T00:00:00Z"), {17: HEAD})
            self.assertEqual(ledger.heads("owner/repo", before="2000-01-01T00:00:00Z"), {})
            ledger.record("round-1", [{"pr": 18, "head": BASE, "summary": "Rollback drops rows", "status": "open"}], "owner/repo")
            self.assertEqual(ledger.heads("owner/repo", before="2999-01-01T00:00:00Z"), {17: HEAD, 18: BASE})
            self.assertEqual(ledger.heads("owner/repo", before="2000-01-01T00:00:00Z"), {})
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
                ledger.check_clearance(bundle(assessment(kind=kind)), "owner/repo", 17, LIVE)
        self.assertEqual(ledger.check_clearance(bundle(), "owner/repo", 17, LIVE).record()["verdict"], "fresh")

    def test_nonblocking_code_advice_is_not_a_landing_blocker(self):
        item = assessment(kind="code")
        item["decisions"][0]["severity"] = "non-blocking"
        self.assertEqual(ledger.unresolved(item), [])
        ledger.check_clearance(bundle(item), "owner/repo", 17, LIVE)

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
                ledger.check_clearance(saved, "owner/repo", 17, LIVE)
                Path("rules.md").write_text("A newly required compatibility check")
                with self.assertRaisesRegex(ValueError, "review policy changed"):
                    ledger.check_clearance(saved, "owner/repo", 17, LIVE)
                self.assertFalse(ledger.assessment_current(item, HEAD, BASE, {
                    **item["evidence_inputs"], "policy": ledger.review_config(".", "custom.json")["revision"]}))
            finally:
                os.chdir(previous)


class RelatedTests(unittest.TestCase):
    """A correct PR can still be the wrong one to merge, so the round judges PRs against each other."""

    def test_pairs_come_from_shared_files_and_mentions_of_scoped_prs_only(self):
        import related
        prs = [{"number": 12, "paths": ["src/a.py", "package-lock.json"], "text": "Fix filters\nCloses #45"},
               {"number": 15, "paths": ["src/a.py", "src/b.py"], "text": "Filters, take two"},
               {"number": 20, "paths": ["package-lock.json", "web/x.tsx"], "text": "Supersedes #9"},
               {"number": 21, "paths": ["docs/y.md"], "text": "Replaces #20"}]
        found = related.pairs(prs)
        # A shared lockfile and a mention of an issue or out-of-round PR relate nothing; a one-way mention does.
        self.assertEqual([(e["prs"], e["files"], e["mentions"]) for e in found],
                         [([12, 15], ["src/a.py"], []), ([20, 21], [], ["#21 names #20"])])
        self.assertEqual(related.outside_claims(prs), [(20, "Supersedes #9")])

    def test_base_overlap_names_shared_files_and_the_prs_that_landed_since(self):
        import related
        compare = {"files": ["src/a.py", "yarn.lock", "src/c.py"],
                   "commits": ["Rework filters (#9)", "Merge pull request #11 from team/x", "Mention #7 in docs"]}
        self.assertEqual(related.base_overlap(["src/a.py", "yarn.lock", "src/b.py"], compare),
                         {"files": ["src/a.py"], "prs": [9, 11], "truncated": False})

    def test_superseded_or_duplicate_pr_cannot_be_ready(self):
        for kind in ("superseded-by", "duplicates"):
            with self.subTest(kind=kind):
                relation = [{"pr": 15, "kind": kind, "evidence": "#15 carries every hunk of #17 plus the fix"}]
                with self.assertRaisesRegex(ValueError, "cannot be ready"):
                    ledger.validate_assessment(assessment(relations=relation))
                waived = assessment(kind="decision", owner="Owner", relations=relation)
                waived["decisions"][0]["waiver"] = {"actor": "Owner", "source": "url", "at": REVISION,
                                                    "scope": "keep both", "criterion": "Demonstrate the live workflow"}
                with self.assertRaisesRegex(ValueError, "cannot be ready"):
                    ledger.validate_assessment(waived)
                held = assessment(kind="decision", owner="Author", relations=relation)
                ledger.validate_assessment(held)
                with self.assertRaisesRegex(ValueError, "unresolved decisions"):
                    ledger.check_clearance(bundle(held), "owner/repo", 17, LIVE)
        ledger.validate_assessment(assessment(relations=[{"pr": 15, "kind": "supersedes", "evidence": "x"}]))
        with self.assertRaisesRegex(ValueError, "another PR number"):
            ledger.validate_assessment(assessment(relations=[{"pr": 17, "kind": "independent", "evidence": "x"}]))

    def test_round_holds_until_each_pair_has_a_relation_from_either_side(self):
        pairs = [{"prs": [12, 15], "files": ["src/a.py"], "mentions": []},
                 {"prs": [20, 21], "files": [], "mentions": ["#21 names #20"]}]
        judged = [assessment(21, relations=[{"pr": 20, "kind": "independent", "evidence": "different screens"}]),
                  assessment(12, relations=[{"pr": 99, "kind": "independent", "evidence": "elsewhere"}])]
        self.assertEqual(ledger.relation_blockers(pairs, judged),
                         ["PRs #12 and #15: related (src/a.py) but neither assessment records a relation to the other"])
        # The latest assessment of a PR in the round is the one that counts.
        dropped = judged + [assessment(21)]
        self.assertEqual(len(ledger.relation_blockers(pairs, dropped)), 2)
