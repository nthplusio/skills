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
from decision_fixtures import assessment, HEAD, BASE, REVISION, TARGET
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


def queue_row(**changes):
    return {"number": 17, "title": "Keep saved filters", "author": {"login": "author"},
            "createdAt": "2026-11-01T12:00:00Z", "isDraft": False, "reviewDecision": "REVIEW_REQUIRED",
            "headRefOid": HEAD, "baseRefOid": BASE, "updatedAt": REVISION, "mergeStateStatus": "CLEAN",
            "additions": 8, "deletions": 3, "autoMergeRequest": None, **changes}


def run_queue(reads, raw, *, argv=(), saved=None, login="reviewer", elsewhere=()):
    """Drive queue.main() against recorded reads; returns what it printed.

    `elsewhere` is the last read: open PRs that request the reviewer, on any base."""
    output = io.StringIO()
    with patch.object(sys, "argv", ["queue.py", "main", *argv]), \
            patch.object(queue, "gh_json", side_effect=[*reads, elsewhere if elsewhere is None else list(elsewhere)]), \
            patch.object(queue, "repo_slug", return_value="sample/product"), \
            patch.object(queue, "handled_requests", return_value=[]), \
            patch.object(queue, "assessments", return_value=saved or {}), \
            patch.object(queue, "me", return_value=login), \
            patch.object(queue, "stack_of", return_value=None), \
            patch.object(queue, "collect", side_effect=lambda slug, number: copy.deepcopy(raw)), \
            contextlib.redirect_stdout(output):
        queue.main()
    return output.getvalue()


class HandoffTests(unittest.TestCase):
    def setUp(self):
        for name, value in (("me", "reviewer"), ("assessments", {})):
            local = patch.object(queue, name, return_value=value)
            local.start()
            self.addCleanup(local.stop)
        stacks = patch.object(round_report, "stack_of", return_value=None)
        stacks.start()
        self.addCleanup(stacks.stop)
        target = patch.object(round_report, "target_state", return_value=TARGET)
        target.start()
        self.addCleanup(target.stop)

    def test_same_head_rerequest_is_independent_of_conflicts_ci_and_auto_merge(self):
        raw = evidence()
        p = {"number": 17, "title": "Keep saved filters", "author": {"login": "author"},
             "createdAt": "2026-11-01T12:00:00Z", "isDraft": False, "reviewDecision": "CHANGES_REQUESTED",
             "headRefOid": HEAD, "baseRefOid": BASE, "updatedAt": REVISION,
             "mergeStateStatus": "DIRTY", "additions": 8, "deletions": 3, "autoMergeRequest": {"enabledAt": REVISION}}
        output = io.StringIO()
        with patch.object(sys, "argv", ["queue.py", "main"]), \
                patch.object(queue, "gh_json", side_effect=[[p], {"files": [{"path": "src/store.py"}],
                    "statusCheckRollup": [{"conclusion": "FAILURE"}]}, p, []]), \
                patch.object(queue, "repo_slug", return_value="sample/product"), \
                patch.object(queue, "handled_requests", return_value=[]), \
                patch.object(queue, "stack_of", return_value=None), \
                patch.object(queue, "collect", return_value=raw), contextlib.redirect_stdout(output):
            queue.main()
        for text in ("Review requested again", "CHANGES_REQUESTED", "AUTHOR: conflicts", "1 RED", "AUTO",
                     "author -> user:reviewer", "Request 31", "1; unknown coverage on 0",
                     "unhandled; after an earlier CHANGES_REQUESTED review by reviewer"):
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
            # A request that follows any earlier review by its target asks for another look.
            with self.subTest(prior=state):
                asked = {**raw, "pr": {**raw["pr"], "reviews": [{**later, "submitted_at": "2026-11-03T11:00:00Z"}]}}
                again = review_requests.reconcile(asked)["requests"][0]
                self.assertEqual((again["renewed"], again["prior_state"]), (True, state))
                self.assertIn("requested again", queue.request_label(review_requests.reconcile(asked)))
        # A review submitted after the request answers it; it does not make the request a renewal.
        first = {**raw, "pr": {**raw["pr"], "reviews": [{**original, "submitted_at": "2026-11-03T13:00:00Z"}]}}
        self.assertEqual([(r["renewed"], r["prior_state"]) for r in review_requests.reconcile(first)["requests"]],
                         [(False, None)])
        # Team membership is never inferred: only an earlier request to the same team renews one.
        team = {**raw, "requestedReviewers": ["team:data-reviewers"],
                "timeline": [request(34, target="team:data-reviewers")]}
        self.assertFalse(review_requests.reconcile(team)["requests"][0]["renewed"])
        team["timeline"] = [request(34, target="team:data-reviewers", at="2026-11-03T10:00:00Z"),
                            request(35, "review_request_removed", "team:data-reviewers", "2026-11-03T11:00:00Z"),
                            request(36, target="team:data-reviewers"), request(37, target="team:other-reviewers")]
        team["requestedReviewers"].append("team:other-reviewers")
        self.assertEqual([(r["event_id"], r["renewed"]) for r in review_requests.reconcile(team)["requests"]],
                         [("34", False), ("36", True), ("37", False)])
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
        self.assertEqual(round_report.requirement_gaps({"requirements": [source]}),
                         ["requirements-original-source-not-retained:" + source["source"]])
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
        self.assertIn("Merged head has no saved local assessment", source)
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
        # A Spec gap makes the recommendation stale; the request stays handled at its assessed head.
        for text in ("Review again", "0 unhandled", "assessed-locally", "Reviewer to refresh the changed code"):
            self.assertIn(text, source)
        self.assertNotIn("previous local disposition is stale", source)
        del record["requirements_gaps"]
        record["head"] = "f" * 40
        source = render([record], "main", assessments={"repository": record["repository"], "assessments": [item]})
        for text in ("Review again", "1 unhandled", "previous local disposition is stale", "Reviewer to reconcile the outstanding request"):
            self.assertIn(text, source)

    def test_triage_applies_a_saved_disposition_only_at_its_assessed_head(self):
        saved = {"event_id": "31", "target": "user:reviewer", "at": REVISION, "disposition": "assessed-locally",
                 "number": 17, "head": HEAD}
        for live_head, expected, absent in (
                (HEAD, ("user:reviewer at 2026-11-03T12:00:00Z; assessed-locally", "0; unknown coverage on 0"), "Previously handled"),
                ("f" * 40, ("user:reviewer at 2026-11-03T12:00:00Z; unhandled", "Previously handled 31", "head moved",
                            "1; unknown coverage on 0"), "; assessed-locally")):
            p = {"number": 17, "title": "Keep saved filters", "author": {"login": "author"},
                 "createdAt": "2026-11-01T12:00:00Z", "isDraft": False, "reviewDecision": "CHANGES_REQUESTED",
                 "headRefOid": live_head, "baseRefOid": BASE, "updatedAt": "2026-11-12T09:00:00Z",
                 "mergeStateStatus": "CLEAN", "additions": 8, "deletions": 3, "autoMergeRequest": None}
            output = io.StringIO()
            with self.subTest(head=live_head), patch.object(sys, "argv", ["queue.py", "main"]), \
                    patch.object(queue, "gh_json", side_effect=[[p], {"files": [], "statusCheckRollup": []}, p, []]), \
                    patch.object(queue, "repo_slug", return_value="sample/product"), \
                    patch.object(queue, "handled_requests", return_value=[saved]), \
                    patch.object(queue, "stack_of", return_value=None), \
                    patch.object(queue, "collect", return_value=evidence()), contextlib.redirect_stdout(output):
                queue.main()
                for text in expected:
                    self.assertIn(text, output.getvalue())
                self.assertNotIn(absent, output.getvalue())

    def test_disposition_survives_target_and_discussion_changes_but_not_a_new_head(self):
        raw, record = fixture()
        raw["requestedReviewers"] = ["user:Alex"]
        raw["timeline"] = [{**raw["timeline"][0], "at": "2026-11-03T16:00:00Z", "requestedReviewer": "Alex"}]
        marker = {"event_id": "51", "target": "user:Alex", "at": REVISION, "disposition": "assessed-locally"}
        first = assessment(482, head=record["head"], base=record["base"], request_events=[marker])
        first["evidence_inputs"]["target"] = {**TARGET, "sha": "e" * 40}  # the target branch has moved since
        # Re-recorded at the same head without markers, as after a posted action.
        later = assessment(482, head=record["head"], base=record["base"], assessed_at="2026-11-11T21:00:00Z")
        for live_head, disposition, closes in ((record["head"], "assessed-locally", True), ("f" * 40, "unhandled", False)):
            pr = {**raw["pr"], "id": "PR_482", "isDraft": False, "state": "OPEN", "reviewDecision": "CHANGES_REQUESTED",
                  "mergeStateStatus": "CLEAN", "updatedAt": "2026-11-12T09:00:00Z", "headRefOid": live_head}
            output = io.StringIO()
            with self.subTest(head=live_head), tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, XDG_STATE_HOME=tmp), \
                    patch.object(sys, "argv", ["round_report.py", "main", "--since", REVISION, "--me", "Alex"]), \
                    patch.object(round_report, "repo_slug", return_value=record["repository"]), \
                    patch.object(round_report, "gh", side_effect=[[pr], []]), \
                    patch.object(round_report, "queue_state", return_value="not_queued"), \
                    patch.object(round_report, "history_evidence", return_value={**raw, "pr": pr}), \
                    patch.object(round_report, "assessment_history", return_value=[first, later]), \
                    patch("ledger.heads", return_value={}), \
                    contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                round_report.main()
                row = json.loads(output.getvalue())[0]
                self.assertEqual((row["handoffs"]["requests"][0]["disposition"], row["handoffs"]["coverage"]),
                                 (disposition, "complete"))
                # The recommendation is stale either way; only the head decides the handoff.
                for item in (first, later):
                    self.assertFalse(ledger.assessment_current(item, row["head"], row["base"], row["evidence_inputs"]))
                source = render([row], "main")
                self.assertIn("Review again", source)
                self.assertIn(f"{0 if closes else 1} unhandled", source)
                rid = ledger.round_start("main", record["repository"])
                if closes:
                    ledger.round_end(rid, [482], record["repository"], reconciliation=[row])
                    self.assertEqual(ledger.last_round("main", record["repository"])["prs"], [482])
                else:
                    with self.assertRaisesRegex(ValueError, "unhandled request"):
                        ledger.round_end(rid, [482], record["repository"], reconciliation=[row])

    def test_triage_shows_what_changed_since_the_last_look_and_where_my_review_stands(self):
        details = {"files": [{"path": "src/store.py"}], "statusCheckRollup": []}
        mine = lambda state, commit: {"id": 12, "state": state, "user": {"login": "reviewer"},
                                      "submitted_at": "2026-11-04T12:00:00Z", "commit_id": commit}
        moved = "f" * 40
        cases = [
            # live head, my latest decisive review, saved assessment, decision -> shown / not shown
            ("pushed after my approval dismissed it", moved, mine("DISMISSED", HEAD), assessment(), "REVIEW_REQUIRED",
             ("HEAD MOVED", "DISMISSED", "REVIEW: needs review", "Look again", "#17 (HEAD MOVED, DISMISSED)"),
             ("another approver",)),
            ("pushed and my approval still counts", moved, mine("APPROVED", HEAD), assessment(), "APPROVED",
             ("approved at old head", "#17 (HEAD MOVED, approved at old head)"), ("another approver",)),
            ("my changes request predates the head", moved, mine("CHANGES_REQUESTED", HEAD), None, "CHANGES_REQUESTED",
             ("changes-req at old head", "#17 (changes-req at old head)", " new "), ("(HEAD MOVED",)),
            ("approved at head, gate still closed", HEAD, mine("APPROVED", HEAD), assessment(), "REVIEW_REQUIRED",
             ("approved at head", "unchanged", "REVIEW: another approver", "name another approver: #17"),
             ("Look again", "REVIEW: needs review")),
            ("approved at head and cleared", HEAD, mine("APPROVED", HEAD), assessment(), "APPROVED",
             ("approved at head", "-> MERGEABLE NOW"), ("Look again", "another approver")),
            ("same head, later discussion", HEAD, None, assessment(), "REVIEW_REQUIRED",
             ("discussion changed", "REVIEW: needs review"), ("Look again", "another approver")),
        ]
        for name, head, review, saved, decision, shown, hidden in cases:
            with self.subTest(name):
                raw = evidence()
                raw["pr"]["reviews"] = [review] if review else []
                raw["timeline"], raw["requestedReviewers"] = [], []
                updated = "2026-11-12T09:00:00Z" if name == "same head, later discussion" else REVISION
                p = queue_row(headRefOid=head, reviewDecision=decision, updatedAt=updated)
                text = run_queue([[p], details, p], raw, saved={17: saved} if saved else {})
                text = text.split("\nRISK -> depth")[0]  # the legend names every label; judge the rows
                for expected in shown:
                    self.assertIn(expected, text)
                for unexpected in hidden:
                    self.assertNotIn(unexpected, text)
        # Without a readable login the column says so; it never reads as "no review".
        raw = evidence()
        raw["pr"]["reviews"] = [mine("APPROVED", HEAD)]
        p = queue_row()
        text = run_queue([[p], details, p], raw, login=None)
        self.assertIn("reviewer login unavailable", text)
        self.assertNotIn("another approver", text)

    def test_scope_file_is_written_once_and_names_what_joined_and_left(self):
        details = {"files": [{"path": "src/store.py"}], "statusCheckRollup": []}
        raw = evidence()
        raw["timeline"], raw["requestedReviewers"], raw["pr"]["reviews"] = [], [], []
        first, second = queue_row(number=16), queue_row(number=17, createdAt="2026-11-02T12:00:00Z")
        late = queue_row(number=18, createdAt="2026-11-03T12:00:00Z")
        with tempfile.TemporaryDirectory() as tmp:
            scope = Path(tmp) / "scope.json"
            text = run_queue([[first, second], details, details, first, second], raw, argv=["--save-scope", str(scope)])
            self.assertEqual(json.loads(scope.read_text()), [16, 17])
            self.assertIn("2 PR(s)", text)
            # The first snapshot is the round's scope; a second save must not replace it.
            with self.assertRaisesRegex(SystemExit, "already exists"):
                run_queue([[second, late]], raw, argv=["--save-scope", str(scope)])
            self.assertEqual(json.loads(scope.read_text()), [16, 17])
            for departed, why in (({"number": 16, "state": "MERGED", "isDraft": False}, "#16 (merged)"),
                                  ({"number": 16, "state": "OPEN", "isDraft": True}, "#16 (draft)"),
                                  (None, "#16 (state unknown)")):
                with self.subTest(why):
                    text = run_queue([[second, late], details, details, second, late, departed], raw,
                                     argv=["--scope", str(scope)])
                    self.assertIn("JOINED after the scope snapshot: #18 ", text)
                    self.assertIn("LEFT the queue: " + why, text)
            text = run_queue([[first, second], details, details, first, second], raw, argv=["--scope", str(scope)])
            self.assertIn("JOINED after the scope snapshot: none", text)
            self.assertIn("LEFT the queue: none", text)
            scope.write_text('{"prs": [16]}')
            with self.assertRaisesRegex(SystemExit, "scope comparison unknown"):
                run_queue([[first]], raw, argv=["--scope", str(scope)])

    def test_requests_the_base_listing_cannot_show_are_named_and_stay_out_of_scope(self):
        details = {"files": [{"path": "src/store.py"}], "statusCheckRollup": []}
        raw = evidence()
        raw["timeline"], raw["requestedReviewers"], raw["pr"]["reviews"] = [], [], []
        p = queue_row()
        asked = lambda number, base="main", draft=False: {"number": number, "baseRefName": base, "isDraft": draft}
        with tempfile.TemporaryDirectory() as tmp:
            scope = Path(tmp) / "scope.json"
            text = run_queue([[p], details, p], raw, argv=["--save-scope", str(scope)], elsewhere=[
                asked(17), asked(31, "feature/filters"), asked(30, "feature/filters", True), asked(40, draft=True), asked(41)])
            # A request the table already shows is not repeated, and none of these joins the scope.
            self.assertEqual(json.loads(scope.read_text()), [17])
        self.assertIn("1 open non-draft PR(s)", text)
        self.assertIn("not in this round's scope", text)
        self.assertIn("  other base: #30 -> feature/filters (draft), #31 -> feature/filters\n", text)
        self.assertIn("  not listed on main: #40 (draft), #41 (ready since the listing; run queue.py again)\n", text)
        self.assertNotIn("#17 ->", text)
        text = run_queue([[p], details, p], raw, elsewhere=[asked(17)])
        self.assertIn("Review requested from you outside this table: none", text)
        self.assertNotIn("other base", text)
        # A failed or truncated search is unknown, never "none".
        for unread in (None, [asked(n, "feature/filters") for n in range(100, 200)]):
            text = run_queue([[p], details, p], raw, elsewhere=unread)
            self.assertIn("could not list review requests outside this table", text)
            self.assertNotIn("outside this table: none", text)
            self.assertNotIn("other base", text)

    def run_ledger(self, *argv):
        output = io.StringIO()
        code = 0
        with patch.object(sys, "argv", ["ledger.py", *argv]), \
                patch.object(ledger, "repo_slug", return_value="sample/product"), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            try:
                ledger.main()
            except SystemExit as stop:
                code = stop.code
                if isinstance(code, str):
                    output.write(code)
                    code = 1
        return output.getvalue(), code or 0

    def test_round_commands_start_record_and_close_or_name_every_blocker(self):
        marker = {"event_id": "31", "target": "user:reviewer", "at": REVISION, "disposition": "assessed-locally"}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, XDG_STATE_HOME=tmp):
            files = {name: Path(tmp) / f"{name}.json" for name in ("assessments", "scope", "report")}
            files["assessments"].write_text(json.dumps({"repository": "sample/product",
                                                        "assessments": [assessment(request_events=[marker])]}))
            # An invented round id records nothing; the round has to be started.
            text, code = self.run_ledger("record", "any-string", str(files["assessments"]))
            self.assertEqual(code, 1)
            self.assertIn("unknown round", text)
            self.assertEqual(ledger.assessment_history("sample/product"), [])
            rid, code = self.run_ledger("start", "main")
            rid = rid.strip()
            self.assertEqual((code, ledger.open_round("main", "sample/product")["round"]), (0, rid))
            # One invalid assessment records none of the bundle.
            broken = assessment(18)
            del broken["decisions"]
            files["report"].write_text(json.dumps({"repository": "sample/product",
                                                   "assessments": [assessment(), broken]}))
            text, code = self.run_ledger("record", rid, str(files["report"]))
            self.assertEqual((code, ledger.assessment_history("sample/product")), (1, []), text)
            text, code = self.run_ledger("record", rid, str(files["assessments"]))
            self.assertEqual(code, 0, text)
            self.assertEqual([m["event_id"] for m in ledger.handled_requests("sample/product")], ["31"])

            row = lambda number, handoffs: {"repository": "sample/product", "number": number, "handoffs": handoffs}
            handled = review_requests.reconcile(evidence(), [marker])
            files["scope"].write_text("[17, 18]")
            files["report"].write_text(json.dumps([
                row(17, review_requests.reconcile(evidence())),
                row(19, {"coverage": "unknown", "gaps": ["timeline"], "unhandled": 0, "requests": []})]))
            text, code = self.run_ledger("end", rid, "--scope", str(files["scope"]), "--report", str(files["report"]))
            self.assertEqual(code, 1)
            for blocker in ("PR #18: not in the report", "PR #17: 1 unhandled request(s) (31 -> user:reviewer)"):
                self.assertIn(blocker, text)
            self.assertIsNone(ledger.last_round("main", "sample/product"))
            files["report"].write_text(json.dumps([
                row(17, handled), row(18, {"coverage": "unknown", "gaps": ["timeline"], "unhandled": 0, "requests": []})]))
            text, code = self.run_ledger("end", rid, "--scope", str(files["scope"]), "--report", str(files["report"]))
            self.assertEqual(code, 1)
            self.assertIn("PR #18: request coverage unknown (timeline)", text)
            self.assertNotIn("PR #17", text)
            files["report"].write_text(json.dumps([row(17, handled), row(18, review_requests.reconcile(
                {**evidence(), "timeline": [], "requestedReviewers": []})), row(19, handled)]))
            text, code = self.run_ledger("end", "another-id", "--scope", str(files["scope"]), "--report", str(files["report"]))
            self.assertEqual(code, 1)
            self.assertIn("unknown round", text)
            text, code = self.run_ledger("end", rid, "--scope", str(files["scope"]), "--report", str(files["report"]))
            self.assertEqual(code, 0, text)
            self.assertEqual(ledger.last_round("main", "sample/product")["prs"], [17, 18])
            self.assertIsNone(ledger.open_round("main", "sample/product"))


if __name__ == "__main__":
    unittest.main()
