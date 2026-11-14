"""Recorded forge-response cases; no live API calls or writes."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
import ledger
import review_requests
import round_report
import stale_sweep
import findings
import prstate
from render_round import render
from decision_fixtures import assessment, HEAD, BASE, REVISION
from test_report import fixture

spec = importlib.util.spec_from_file_location("round_queue", SKILL / "scripts/queue.py")
queue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(queue)


def request(identity=31, event="review_requested", target="user:reviewer", at="2026-11-03T12:00:00Z"):
    return {"id": identity, "event": event, "actor": {"login": "author"}, "created_at": at,
            "requested_reviewer": {"login": target[5:]} if target.startswith("user:") else None,
            "requested_team": {"slug": target[5:]} if target.startswith("team:") else None}


def evidence():
    return {"pr": {"number": 17, "headRefOid": HEAD, "reviews": [
        {"id": 10, "state": "CHANGES_REQUESTED", "user": {"login": "reviewer"},
         "submitted_at": "2026-11-02T12:00:00Z", "commit_id": HEAD}]},
        "requestedReviewers": ["user:reviewer"], "timeline": [request()], "failedFetches": []}


class HandoffTests(unittest.TestCase):
    def test_same_head_rerequest_is_independent_of_conflicts_ci_and_auto_merge(self):
        raw = evidence()
        p = {"number": 17, "title": "Keep saved filters", "author": {"login": "author"},
             "createdAt": "2026-11-01T12:00:00Z", "isDraft": False, "reviewDecision": "CHANGES_REQUESTED",
             "headRefOid": HEAD, "baseRefOid": BASE, "updatedAt": REVISION,
             "mergeStateStatus": "DIRTY", "additions": 8, "deletions": 3, "autoMergeRequest": {"enabledAt": REVISION}}
        output = io.StringIO()
        with patch.object(sys, "argv", ["queue.py", "main"]), \
                patch.object(queue, "gh_json", side_effect=[[p], {"files": [{"path": "src/store.py"}],
                    "statusCheckRollup": [{"conclusion": "FAILURE"}]}, p]), \
                patch.object(queue, "repo_slug", return_value="sample/product"), \
                patch.object(queue, "handled_requests", return_value=[]), \
                patch.object(queue, "collect", return_value=raw), contextlib.redirect_stdout(output):
            queue.main()
        for text in ("Review requested again", "CHANGES_REQUESTED", "AUTHOR: conflicts", "1 RED", "AUTO",
                     "author -> user:reviewer", "Request 31", "1; unknown coverage on 0"):
            self.assertIn(text, output.getvalue())
        self.assertEqual(review_requests.reconcile(raw)["unhandled"], 1)
        raw["timeline"] = []
        raw["requestedReviewers"] = []
        self.assertNotIn("requested again", queue.request_label(review_requests.reconcile(raw)))

    def test_approval_dismissal_and_comments_fold_without_erasing_history(self):
        raw = evidence()
        original = raw["pr"]["reviews"][0]
        for state in ("APPROVED", "DISMISSED", "COMMENTED"):
            later = {**original, "id": 11, "state": state, "submitted_at": "2026-11-03T13:00:00Z"}
            raw["pr"]["reviews"] = [later, original]
            effective = review_requests.effective_reviews(raw["pr"]["reviews"])
            self.assertEqual(effective["reviewer"]["state"], "CHANGES_REQUESTED" if state == "COMMENTED" else state)
            self.assertEqual(len(raw["pr"]["reviews"]), 2)
        # The actual sweep must ignore a superseded return, not just the pure fold.
        p = {"number": 17, "headRefOid": HEAD, "createdAt": REVISION, "isDraft": False}
        output = io.StringIO()
        approval = {**original, "id": 11, "state": "APPROVED", "submitted_at": REVISION}
        with patch.object(sys, "argv", ["stale_sweep.py", "main"]), \
                patch.object(stale_sweep, "gh", side_effect=["sample/product", [p], [[original], [approval]]]), \
                patch.object(stale_sweep, "have", return_value=True), \
                patch.object(stale_sweep.subprocess, "run"), contextlib.redirect_stdout(output):
            stale_sweep.main()
        self.assertIn("no blocker:   1", output.getvalue())
        self.assertNotIn("reviewed at head --", output.getvalue())

    def test_per_pr_views_fold_reviews_and_keep_fetch_failures_unknown(self):
        raw = evidence()
        original = raw["pr"]["reviews"][0]
        approval = {**original, "id": 11, "state": "APPROVED", "submitted_at": REVISION}
        pr = {"number": 17, "headRefOid": HEAD, "headRefName": "feature", "baseRefName": "main",
              "author": {"login": "author"}, "additions": 2, "deletions": 1, "title": "Example",
              "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN", "reviewDecision": "APPROVED",
              "url": "https://example.test/pr/17"}
        for module, reads in ((findings, ["sample/product", [[original], [approval]]]),
                              (prstate, ["sample/product", pr, [[original], [approval]]])):
            output = io.StringIO()
            with patch.object(sys, "argv", [module.__name__ + ".py", "17"]), \
                    patch.object(module, "gh", side_effect=reads), contextlib.redirect_stdout(output):
                module.main()
            self.assertIn("no blocking reviews", output.getvalue())
            self.assertNotIn("BLOCKING review(s)", output.getvalue())
        for missing in (None, "permission denied"):
            with patch.object(sys, "argv", ["findings.py", "17"]), \
                    patch.object(findings, "gh", side_effect=["sample/product", [[original]], missing]), \
                    self.assertRaisesRegex(SystemExit, "coverage unknown"):
                findings.main()

    def test_removal_second_request_team_and_duplicate_event_id(self):
        raw = evidence()
        raw["timeline"] += [request(32, "review_request_removed", at="2026-11-03T13:00:00Z"),
                            request(33, at="2026-11-03T14:00:00Z"),
                            request(34, target="team:data-reviewers", at="2026-11-03T15:00:00Z")]
        raw["timeline"].append(copy.deepcopy(raw["timeline"][-1]))
        raw["requestedReviewers"].append("team:data-reviewers")
        state = review_requests.reconcile(raw)
        self.assertEqual([(r["event_id"], r["disposition"]) for r in state["requests"]],
                         [("31", "removed"), ("33", "unhandled"), ("34", "unhandled")])
        self.assertEqual(state["unhandled"], 2)
        self.assertEqual(state["coverage"], "complete")
        raw["timeline"] = [request(), request(33, at="2026-11-03T14:00:00Z")]
        raw["requestedReviewers"] = ["user:reviewer"]
        self.assertEqual(review_requests.reconcile(raw)["requests"][0]["disposition"], "superseded")

    def test_ledger_marker_is_event_scoped_local_and_never_an_approval(self):
        item = assessment()
        marker = {"event_id": "31", "target": "user:reviewer", "at": REVISION, "disposition": "assessed-locally"}
        item["request_events"] = [marker]
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, XDG_STATE_HOME=tmp):
            ledger.record_assessment("round-1", item, "sample/product")
            saved = ledger.assessments("sample/product")[17]
            ledger.record_assessment("round-2", assessment(), "sample/product")
            remembered = ledger.handled_requests("sample/product")
            self.assertEqual([(m["number"], m["target"], m["event_id"], m["head"]) for m in remembered],
                             [(17, "user:reviewer", "31", HEAD)])
        state = review_requests.reconcile(evidence(), saved["request_events"])
        self.assertEqual(state["requests"][0]["disposition"], "assessed-locally")
        self.assertTrue(state["requests"][0]["outstanding"])
        raw = evidence()
        raw["timeline"].append(request(33, at="2026-11-03T14:00:00Z"))
        self.assertEqual(review_requests.reconcile(raw, saved["request_events"])["unhandled"], 1)
        marker["disposition"] = "answered"
        with self.assertRaisesRegex(ValueError, "forge responses"):
            ledger.validate_assessment(item)

    def test_observed_response_and_request_absence_are_not_local_approval(self):
        raw = evidence()
        raw["requestedReviewers"] = []
        response = {"id": 11, "state": "COMMENTED", "user": {"login": "reviewer"},
                    "submitted_at": "2026-11-03T14:00:00Z", "html_url": "https://example.test/review/11"}
        raw["pr"]["reviews"].append(response)
        state = review_requests.reconcile(raw)
        self.assertEqual(state["requests"][0]["disposition"], "answered")
        self.assertEqual(state["effectiveReviews"]["reviewer"], "CHANGES_REQUESTED")
        self.assertEqual(state["requests"][0]["response_urls"], [response["html_url"]])
        raw["requestedReviewers"] = ["user:reviewer"]
        self.assertEqual(review_requests.reconcile(raw)["unhandled"], 1)

    def test_unknown_coverage_never_claims_no_request(self):
        for gap in ("timeline", "reviews", "review-requests", "snapshot-consistency", "pagination-limit"):
            raw = evidence()
            raw["failedFetches"] = [gap]
            raw["requestedReviewers"] = None
            state = review_requests.reconcile(raw)
            self.assertEqual(state["coverage"], "unknown")
            self.assertIn("UNKNOWN", queue.request_label(state))
            self.assertNotIn("No request", queue.request_label(state))
        raw = evidence()
        raw["timeline"] = []
        self.assertEqual(review_requests.reconcile(raw)["gaps"], ["request-event-missing:user:reviewer"])

    def test_round_cannot_close_with_dropped_or_unhandled_requests_or_unknown_coverage(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, XDG_STATE_HOME=tmp):
            rid = ledger.round_start("main", "sample/product")
            for rows in ([], [{"number": 17, "handoffs": review_requests.reconcile(evidence())}],
                         [{"number": 17, "handoffs": {"coverage": "unknown", "unhandled": 0}}]):
                with self.assertRaises(ValueError):
                    ledger.round_end(rid, [17], "sample/product", reconciliation=rows)
                self.assertIsNone(ledger.last_round("main", "sample/product"))
            marker = {"event_id": "31", "target": "user:reviewer", "at": REVISION, "disposition": "reviewer-incomplete"}
            rows = [{"number": 17, "handoffs": review_requests.reconcile(evidence(), [marker])}]
            ledger.round_end(rid, [17], "sample/product", reconciliation=rows)
            self.assertEqual(ledger.last_round("main", "sample/product")["prs"], [17])

    def test_direct_requirements_cannot_disappear_from_spec_matrix(self):
        text = "\n".join(f"- Requirement {i}" for i in range(1, 9))
        source = {"source": "https://tracker.test/item", "retrieved_at": REVISION,
                  "acceptance_text": text, "criteria": [], "matrix": []}
        self.assertIn("requirements-extraction-mismatch:" + source["source"],
                      round_report.requirement_gaps({"requirements": [source]}))
        source["criteria"] = [{"id": str(i), "quote": f"Requirement {i}"} for i in range(1, 9)]
        self.assertTrue(round_report.requirement_gaps({"requirements": [source]}))
        source["matrix"] = [{"criterion_id": str(i), "result": "missing evidence"} for i in range(1, 9)]
        self.assertEqual(round_report.requirement_gaps({"requirements": [source]}), [])
        source["criteria"][0]["quote"] = "Invented requirement"
        self.assertTrue(round_report.requirement_gaps({"requirements": [source]}))

    def test_collection_joins_saved_assessments_and_flags_only_unassessed_merged_heads(self):
        raw, record = fixture()
        raw["requestedReviewers"] = []
        raw["timeline"] = []
        older = assessment(482, "code", "Author", head="e" * 40, base=record["base"])
        merged = {**raw["pr"], "isDraft": False, "state": "MERGED", "reviewDecision": "APPROVED",
                  "mergeStateStatus": "CLEAN", "mergedAt": REVISION}
        for seen_head, expected in (("e" * 40, True), (record["head"], False)):
            saved = {**older, "head": seen_head}
            output = io.StringIO()
            with patch.object(sys, "argv", ["round_report.py", "main", "--since", REVISION, "--me", "reviewer"]), \
                    patch.object(round_report, "repo_slug", return_value=record["repository"]), \
                    patch.object(round_report, "gh", side_effect=[[], [merged]]), \
                    patch.object(round_report, "history_evidence", return_value={**raw, "pr": merged}), \
                    patch.object(round_report, "assessment_history", return_value=[saved]), \
                    patch("ledger.heads", return_value={482: seen_head}), \
                    contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                round_report.main()
            row = json.loads(output.getvalue())[0]
            self.assertEqual(row["merge_review_gap"], expected)
            self.assertEqual(row["assessment"]["decisions"], older["decisions"])
            self.assertIn(older["decisions"][0]["unblock"], render([row], "main"))

    def test_report_retains_unposted_findings_on_unreviewed_merge_and_human_gate(self):
        raw, record = fixture()
        item = assessment(482, "code", "Author", head=record["head"], base=record["base"])
        record.update(state="MERGED", verdict="MERGED", merge_review_gap=True, assessment=item)
        item["head"] = "a" * 40
        item["approval_gate"] = {"owner": "Human approver", "reason": "Exceeds configured automation size limit",
                                 "source": ".github/review-policy.yml"}
        source = render([record], "main")
        self.assertIn("Merged · head not assessed by this round", source)
        self.assertIn(item["decisions"][0]["unblock"], source)
        self.assertIn("Proposed, not posted", source)
        self.assertIn("Human approver: Exceeds configured automation size limit", source)
        self.assertNotIn("No review action needed.", source)

    def test_report_mismatch_prevents_complete_spec_and_changed_head_prevents_current_marker(self):
        _, record = fixture()
        item = assessment(482, head=record["head"], base=record["base"])
        record["handoffs"] = review_requests.reconcile(evidence(), [{"event_id": "31", "target": "user:reviewer",
                         "at": REVISION, "disposition": "assessed-locally"}])
        record["requirements_gaps"] = ["requirements-extraction-mismatch:ticket"]
        source = render([record], "main", assessments={"repository": record["repository"], "assessments": [item]})
        self.assertIn("Spec coverage incomplete", source)
        self.assertIn("Substantive reviews complete: 0", source)
        self.assertIn("1 unhandled", source)
        del record["requirements_gaps"]
        record["head"] = "f" * 40
        source = render([record], "main", assessments={"repository": record["repository"], "assessments": [item]})
        self.assertIn("Review again", source)
        self.assertIn("previous local disposition is stale", source)


if __name__ == "__main__":
    unittest.main()
