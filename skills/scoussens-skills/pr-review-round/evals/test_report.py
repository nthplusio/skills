import contextlib
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
import ledger
import round_report
from pr_history import normalize
from render_round import render
from decision_fixtures import assessment, REVISION, TARGET


def fixture():
    repo = "sample/product"
    head = "c" * 40
    raw = {"schemaVersion": 1, "repository": repo, "collectedAt": "2026-11-03T16:00:00Z",
           "failedFetches": [], "truncatedSources": [],
           "pr": {"number": 482, "url": "https://example.test/pr/482", "title": "Preserve saved filters during migration",
                  "author": {"login": "Maya"}, "headRefOid": head, "baseRefOid": "d" * 40,
                  "createdAt": "2026-10-30T14:00:00Z", "comments": [], "reviews": [
                      {"id": 10, "state": "CHANGES_REQUESTED", "submittedAt": "2026-11-02T16:00:00Z",
                       "author": {"login": "Alex", "type": "User"}, "commitOid": "a" * 40,
                       "url": "https://example.test/review/10", "body": "Legacy presets lost during migration."},
                      {"id": 11, "state": "CHANGES_REQUESTED", "submittedAt": "2026-11-03T15:20:00Z",
                       "author": {"login": "Alex", "type": "User"}, "commitOid": head,
                       "url": "https://example.test/review/11", "body": "Rollback drops saved filters."}]},
           "threads": [], "timeline": [{"id": 51, "event": "review_requested", "actor": "Maya", "actorType": "User",
                                         "at": "2026-11-02T20:00:00Z", "url": "https://example.test/pr/482"}],
           "ticketEvidence": {"status": "partial", "tickets": [{"id": "APP-217", "state": "In review",
                                 "url": "https://tracker.test/APP-217"}], "events": []}}
    record = {"repository": repo, "number": 482, "title": raw["pr"]["title"], "url": raw["pr"]["url"],
              "author": "Maya", "head": head, "base": "d" * 40,
              "evidence_inputs": assessment()["evidence_inputs"], "state": "OPEN", "verdict": "CHANGES_REQUESTED",
              "reviewed_at": "2026-11-03T15:20:00Z", "reviews": [{"id": 11, "state": "CHANGES_REQUESTED",
              "commit_id": head, "submitted_at": "2026-11-03T15:20:00Z", "body": "Rollback drops saved filters."}],
              "comments": [], "history": normalize(raw)}
    return raw, record


class Tags(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.rows = []
        self.open_details = 0
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "article":
            self.rows.append(attrs["data-pr"])
        if tag == "details" and "open" in attrs:
            self.open_details += 1


class ReportTests(unittest.TestCase):
    def setUp(self):
        stacks = patch.object(round_report, "stack_of", return_value=None)
        stacks.start()
        self.addCleanup(stacks.stop)
        target = patch.object(round_report, "target_state", return_value=TARGET)
        target.start()
        self.addCleanup(target.stop)

    def test_renderer_works_from_an_independently_installed_skill(self):
        _, record = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            installed = Path(tmp) / "installed round"
            shutil.copytree(SKILL, installed)
            report = Path(tmp) / "round.json"
            report.write_text(json.dumps([record]))
            result = subprocess.run([sys.executable, "-B", str(installed / "scripts/render_round.py"),
                                     str(report), "--base", "main", "--timezone", "America/Chicago"],
                                    cwd=tmp, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(Tags(result.stdout).rows, ["482"])
            self.assertEqual(Tags(result.stdout).open_details, 0)
            self.assertIn("↩ 2 returns", result.stdout)
            self.assertIn("Nov 03, 09:20 CST", result.stdout)
            self.assertIn("Details · why it went back and review notes", result.stdout)
            self.assertIn("Rollback drops saved filters.", result.stdout)
            self.assertIn("Ticket history partial", result.stdout)

    def test_proposed_verdicts_never_become_posted_and_head_changes_make_them_stale(self):
        _, record = fixture()
        record["reviews"] = []
        record["reviewed_at"] = None
        proposals = {"repository": record["repository"], "assessments": [assessment(482, head=record["head"], base=record["base"],
                     provenance="Reused prior-round assessment; probes not rerun.")]}
        source = render([record], "main", assessments=proposals)
        self.assertIn("Report recommendation, not posted", source)
        self.assertIn("No review or comment posted", source)
        self.assertIn("Reused prior-round assessment; probes not rerun.", source)
        proposals["assessments"][0]["head"] = "e" * 40
        stale = render([record], "main", assessments=proposals)
        self.assertIn("Review again", stale)
        self.assertNotIn("Report recommendation, not posted", stale)
        with self.assertRaises(ValueError):
            render([record, record], "main")
        with self.assertRaises(ValueError):
            render([record], "main", assessments={**proposals, "repository": "other/repo"})
        # An assessment for a PR the report does not hold is named, and the command prints no traceback.
        stray = {**proposals, "assessments": [*proposals["assessments"], assessment(991), assessment(990)]}
        with self.assertRaisesRegex(ValueError, "outside the report: #990, #991. A report covers one base"):
            render([record], "main", assessments=stray)
        with tempfile.TemporaryDirectory() as tmp:
            report, supplied = Path(tmp) / "round.json", Path(tmp) / "assessments.json"
            report.write_text(json.dumps([record]))
            supplied.write_text(json.dumps(stray))
            done = subprocess.run([sys.executable, "-B", str(SKILL / "scripts/render_round.py"), str(report), "--base", "main",
                                   "--assessments", str(supplied)], capture_output=True, text=True)
        self.assertEqual((done.returncode, done.stdout), (1, ""))
        self.assertIn("render_round.py: assessments refer to PR(s) outside the report: #990, #991", done.stderr)
        self.assertIn("Nothing rendered", done.stderr)
        self.assertNotIn("Traceback", done.stderr)

    def test_unstable_snapshot_cannot_present_a_current_proposal(self):
        _, record = fixture()
        record["history"]["gaps"] = ["snapshot-consistency"]
        proposals = {"repository": record["repository"], "assessments": [assessment(482, head=record["head"], base=record["base"])]}
        source = render([record], "main", assessments=proposals)
        self.assertIn("Review again", source)
        self.assertIn("Some PR history is missing", source)
        self.assertNotIn("Report recommendation, not posted", source)

    def test_queue_and_merge_states_remain_distinct(self):
        records = []
        for number, verdict in enumerate(("APPROVED_QUEUED", "MERGED", "APPROVED_QUEUE_UNKNOWN"), 1):
            _, record = fixture()
            record.update(number=number, verdict=verdict, state="MERGED" if verdict == "MERGED" else "OPEN")
            records.append(record)
        source = render(records, "main")
        self.assertEqual(Tags(source).rows, ["1", "2", "3"])
        self.assertIn("1 merged", source)
        self.assertIn("This change has not merged", source)
        self.assertIn("GitHub approved · queue unknown", source)

    def test_status_labels_separate_local_review_from_github_and_merge_gates(self):
        _, record = fixture()
        proposal = assessment(482, head=record["head"], base=record["base"])
        page = render([record], "main", assessments={"repository": record["repository"], "assessments": [proposal]})
        collapsed = page.split('<article class="pr-row"', 1)[1].split('<details class="history-detail">', 1)[0]
        self.assertIn('Source review complete · merge checks pending', collapsed)
        self.assertIn('Observed on GitHub · changes requested', collapsed)
        self.assertIn('Report recommendation, not posted', collapsed)
        for verdict, label in [('APPROVED', 'GitHub approved · not merged'),
                               ('APPROVED_QUEUED', 'Queued · not merged'),
                               ('APPROVED_QUEUE_UNKNOWN', 'GitHub approved · queue unknown')]:
            record['verdict'] = verdict
            self.assertIn(label, render([record], 'main'))
        proposal['evidence_inputs'] = {**proposal['evidence_inputs'], 'target': {**TARGET, 'sha': None}}
        stale = render([record], 'main', assessments={'repository': record['repository'], 'assessments': [proposal]})
        self.assertIn('Review again · inputs changed or incomplete', stale)
        self.assertNotIn('Source review complete · merge checks pending', stale)

    def test_superseded_pr_reads_as_an_owner_decision_naming_the_replacement(self):
        _, record = fixture()
        proposal = assessment(482, kind="decision", owner="Author", head=record["head"], base=record["base"],
                              relations=[{"pr": 490, "kind": "superseded-by", "evidence": "#490 carries this fix and its test"}])
        proposal["decisions"][0]["unblock"] = "Close #482 in favor of #490"
        page = render([record], "main", assessments={"repository": record["repository"], "assessments": [proposal]})
        self.assertIn("Needs owner decision", page)
        self.assertIn("Close #482 in favor of #490", page)
        self.assertIn("Superseded by #490 · #490 carries this fix and its test", page)
        self.assertNotIn("Source review complete · merge checks pending", page)

    def test_dense_row_uses_product_summary_and_keeps_original_evidence_in_details(self):
        _, record = fixture()
        record["summary"] = "Keep saved filters when upgrading"
        source = render([record], "main")
        row = source.split('<article class="pr-row"', 1)[1]
        collapsed, detail = row.split('<details class="history-detail">', 1)
        self.assertIn("Keep saved filters when upgrading", collapsed)
        self.assertIn("GitHub changes requested", collapsed)
        self.assertIn("↩ 2 returns", collapsed)
        self.assertNotIn(record["head"], collapsed)
        self.assertNotIn("Rollback drops saved filters", collapsed)
        self.assertIn(record["title"], detail)
        self.assertIn(record["head"], detail)
        self.assertIn("Rollback drops saved filters", detail)

    def test_round_boundary_filters_my_posts_but_not_lifetime_history(self):
        raw, record = fixture()
        pr = {**raw["pr"], "id": "PR_482", "isDraft": False, "reviewDecision": "CHANGES_REQUESTED",
              "state": "OPEN", "mergeStateStatus": "CLEAN", "mergedAt": None}
        output = io.StringIO()
        with patch.object(sys, "argv", ["round_report.py", "main", "--since", "2026-11-03T00:00:00Z", "--me", "Alex"]), \
                patch.object(round_report, "repo_slug", return_value=record["repository"]), \
                patch.object(round_report, "gh", side_effect=[[pr], []]), \
                patch.object(round_report, "history_evidence", return_value=raw), \
                patch.object(round_report, "queue_state", return_value="not_queued"), \
                contextlib.redirect_stdout(output):
            round_report.main()
        row = json.loads(output.getvalue())[0]
        self.assertEqual([r["id"] for r in row["reviews"]], [11])
        self.assertEqual([e["id"] for e in row["history"]["events"] if e["returned"]], ["review-10", "review-11"])

    def test_prs_merging_between_queue_reads_appear_once_with_the_later_snapshot(self):
        raw, record = fixture()
        opened = {**raw["pr"], "id": "PR_482", "isDraft": False, "reviewDecision": "APPROVED",
                  "state": "OPEN", "mergeStateStatus": "CLEAN", "mergedAt": None}
        still_open = {**opened, "number": 483, "id": "PR_483", "createdAt": "2026-11-01T14:00:00Z"}
        also_merging = {**opened, "number": 484, "id": "PR_484", "createdAt": "2026-11-02T14:00:00Z"}
        draft = {**opened, "number": 485, "id": "PR_485", "isDraft": True}
        merged = {**opened, "state": "MERGED", "mergedAt": "2026-11-03T16:00:00Z", "headRefOid": "e" * 40}
        also_merged = {**also_merging, "state": "MERGED", "mergedAt": "2026-11-03T16:00:01Z"}
        merged_before = {**merged, "number": 481, "id": "PR_481", "createdAt": "2026-10-01T14:00:00Z"}
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["round_report.py", "main", "--since", "2026-11-03T00:00:00Z", "--me", "Alex"]), \
                patch.object(round_report, "repo_slug", return_value=record["repository"]), \
                patch.object(round_report, "gh", side_effect=[
                    [also_merging, still_open, opened, draft], [also_merged, merged, merged_before]]), \
                patch.object(round_report, "history_evidence", side_effect=lambda slug, pr: {**raw, "pr": pr}), \
                patch.object(round_report, "queue_state", return_value="queued"), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            round_report.main()
        rows = json.loads(output.getvalue())
        self.assertEqual([r["number"] for r in rows], [481, 482, 483, 484])
        by_number = {r["number"]: r for r in rows}
        for number, snapshot in ((482, merged), (484, also_merged)):
            with self.subTest(number=number):
                row = by_number[number]
                self.assertEqual((row["state"], row["verdict"], row["queue_state"]),
                                 ("MERGED", "MERGED", "not_queued"))
                self.assertEqual(row["head"], snapshot["headRefOid"])
                self.assertEqual(row["merged_at"], snapshot["mergedAt"])
        self.assertEqual(by_number[483]["verdict"], "APPROVED_QUEUED")
        self.assertIn("4 PR(s) in this round (APPROVED_QUEUED=1 MERGED=3)", errors.getvalue())

    def test_queue_read_failure_never_looks_like_an_empty_complete_round(self):
        with patch.object(sys, "argv", ["round_report.py", "main", "--since", "2026-11-03T00:00:00Z", "--me", "Alex"]), \
                patch.object(round_report, "repo_slug", return_value="sample/product"), \
                patch.object(round_report, "gh", return_value=None), self.assertRaises(SystemExit):
            round_report.main()

    def test_oversized_history_links_evidence_and_preserves_every_row(self):
        records = []
        for number in (3341, 3345, 3397):
            _, record = fixture()
            record["number"] = number
            record["reviews"][0]["body"] = "Original review evidence. " * 30_000
            records.append(record)
        source = render(records, "main")
        self.assertLessEqual(len(source.encode()), 100_000)
        self.assertEqual(Tags(source).rows, ["3341", "3345", "3397"])
        self.assertIn("Full history omitted", source)
        self.assertIn("retained round JSON", source)
        self.assertNotIn("<script", source)

    def test_owned_decisions_do_not_certify_incomplete_review_or_stale_evidence(self):
        records, proposals = [], []
        for number, kind, owner in [(3397, "code", "Author"), (3341, "evidence", "Operator"), (3345, "reviewer-incomplete", "Reviewer")]:
            _, record = fixture()
            record["number"] = number
            records.append(record)
            proposals.append(assessment(number, kind, owner, head=record["head"], base=record["base"]))
        source = render(records, "main", assessments={"repository": records[0]["repository"], "assessments": proposals})
        for label in ("Needs code changes", "Needs evidence", "Review incomplete", "Author ·", "Operator ·", "Reviewer ·"):
            self.assertIn(label, source)
        self.assertIn("Substantive reviews complete: 2", source)
        records[1]["evidence_inputs"]["issues"] = "new-owner-decision"
        source = render(records, "main", assessments={"repository": records[0]["repository"], "assessments": proposals})
        self.assertIn("Review again", source)
        self.assertIn("Substantive reviews complete: 1", source)
        records[0]["evidence_inputs"]["policy"] = "changed-repository-reference"
        source = render(records, "main", assessments={"repository": records[0]["repository"], "assessments": proposals})
        self.assertIn("Substantive reviews complete: 0", source)

    def test_local_posted_claim_requires_current_observed_forge_evidence(self):
        _, record = fixture()
        item = assessment(482, "code", "Author", head=record["head"], base=record["base"])
        item["decisions"][0]["posted_action"] = {"action": "request-changes", "url": "https://example.test/review/11", "at": REVISION}
        proposals = {"repository": record["repository"], "assessments": [item]}
        self.assertNotIn("Action posted on GitHub", render([record], "main", assessments=proposals))
        record["reviews"][0]["url"] = "https://example.test/review/11"
        self.assertIn("Action posted on GitHub", render([record], "main", assessments=proposals))
        record["reviews"][0]["state"] = "DISMISSED"
        self.assertNotIn("Action posted on GitHub", render([record], "main", assessments=proposals))

    def test_scoped_closed_pr_is_retained_and_external_evidence_changes_its_revision(self):
        raw, record = fixture()
        closed = {**raw["pr"], "id": "PR_482", "state": "CLOSED", "isDraft": False,
                  "reviewDecision": "REVIEW_REQUIRED", "updatedAt": REVISION}
        revisions = []
        with tempfile.TemporaryDirectory() as tmp:
            scope = Path(tmp) / "scope.json"
            scope.write_text("[482]")
            for observation in ("Runtime demonstration missing", "Owner accepted apply-log evidence for this criterion"):
                raw["ticketEvidence"]["decision"] = observation
                output = io.StringIO()
                with patch.object(sys, "argv", ["round_report.py", "main", "--scope", str(scope), "--since", REVISION, "--me", "Alex"]), \
                        patch.object(round_report, "repo_slug", return_value=record["repository"]), \
                        patch.object(round_report, "gh", side_effect=[[], [], closed]), \
                        patch.object(round_report, "history_evidence", return_value=raw), \
                        patch("ledger.heads", return_value={}), \
                        contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                    round_report.main()
                rows = json.loads(output.getvalue())
                self.assertEqual([(r["number"], r["verdict"]) for r in rows], [(482, "CLOSED")])
                revisions.append(rows[0]["evidence_inputs"]["issues"])
        self.assertNotEqual(*revisions)

    def collect(self, reads, raw, argv=("--since", "2026-11-03T00:00:00Z"), heads=None, later=None, real_ledger=False):
        """Drive round_report.main() against recorded reads; returns (rows by number, stderr, gh mock).

        `real_ledger` reads saved assessments and heads from the ledger under XDG_STATE_HOME."""
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as stack:
            if not real_ledger:
                stack.enter_context(patch.object(round_report, "assessment_history", return_value=[]))
                stack.enter_context(patch("ledger.heads", return_value=heads or {}))
            with patch.object(sys, "argv", ["round_report.py", "main", "--me", "Alex", *argv]), \
                    patch.object(round_report, "repo_slug", return_value="sample/product"), \
                    patch.object(round_report, "gh", side_effect=reads) as gh, \
                    patch.object(round_report, "history_evidence", side_effect=lambda slug, pr: {**raw, "pr": {**raw["pr"], **pr, **(later or {})}}), \
                    patch.object(round_report, "queue_state", return_value="not_queued"), \
                    patch.object(round_report, "target_state", return_value=TARGET), \
                    patch.object(round_report, "stack_of", return_value=None), \
                    patch.object(round_report, "gate_lines", side_effect=lambda repo, base, who, branches:
                                 [f"rules for {repo}@{base}, {who}, {branches}"]), \
                    contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                round_report.main()
        return {r["number"]: r for r in json.loads(output.getvalue())}, errors.getvalue(), gh

    def test_an_assessment_saved_in_this_round_is_not_called_an_earlier_round(self):
        raw, record = fixture()
        head, moved = record["head"], "e" * 40
        opened = lambda number=482, **changes: {
            **raw["pr"], "number": number, "id": f"PR_{number}", "isDraft": False, "state": "OPEN", "reviews": [],
            "mergeStateStatus": "BLOCKED", "mergedAt": None, "reviewDecision": "REVIEW_REQUIRED", **changes}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, XDG_STATE_HOME=tmp):
            # Both records are stamped with the time of this test run, so the boundary decides which round they are in.
            ledger.record_assessment("round-1", assessment(482, head=head, base=record["base"]), "sample/product")
            ledger.record("round-1", [{"pr": 483, "head": head, "summary": "Rollback drops rows", "status": "open"}],
                          "sample/product")
            run = lambda since, **changes: self.collect([[opened(**changes), opened(483)], []], raw,
                                                        argv=("--since", since), real_ledger=True)[1]
            now = run("2000-01-01T00:00:00Z")
            self.assertIn("ASSESSED IN THIS ROUND, NO REVIEW OR COMMENT POSTED IN IT FROM Alex: "
                          "#482 (assessed at ccccccccc, head unchanged)\n", now)
            self.assertIn("a local record, not a posted review", now)
            self.assertIn("NO POSTED REVIEW OR COMMENT FROM Alex IN THIS ROUND: #483\n", now)
            self.assertNotIn("EARLIER ROUND", now)
            self.assertIn("#482 (assessed at ccccccccc, HEAD MOVED to eeeeeeeee)", run("2000-01-01T00:00:00Z", headRefOid=moved))
            earlier = run("2999-01-01T00:00:00Z")
            self.assertIn("REVIEWED IN AN EARLIER ROUND, not this one: #482 (last head ccccccccc, head unchanged), "
                          "#483 (last head ccccccccc, head unchanged)\n", earlier)
            self.assertNotIn("ASSESSED IN THIS ROUND", earlier)
            self.assertNotIn("NO POSTED REVIEW", earlier)

    def test_assessments_for_a_pr_outside_the_report_are_named_and_nothing_is_reported(self):
        raw, record = fixture()
        opened = {**raw["pr"], "id": "PR_482", "isDraft": False, "state": "OPEN", "reviews": [],
                  "mergeStateStatus": "BLOCKED", "mergedAt": None, "reviewDecision": "REVIEW_REQUIRED"}
        mine = assessment(482, head=record["head"], base=record["base"])
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, XDG_STATE_HOME=tmp):
            supplied = Path(tmp) / "assessments.json"
            argv = ("--since", "2026-11-03T00:00:00Z", "--assessments", str(supplied))
            # #990 and #991 target another base, so neither listing returns them.
            supplied.write_text(json.dumps({"repository": "sample/product", "assessments": [mine, assessment(991), assessment(990)]}))
            output = io.StringIO()
            with self.assertRaises(SystemExit) as stop, contextlib.redirect_stdout(output):
                self.collect([[opened], []], raw, argv=argv)
            message = str(stop.exception.code)
            self.assertIn(f"{supplied} holds assessments for PR(s) outside this report: #990, #991. ", message)
            self.assertIn("The report covers PRs on main", message)
            self.assertIn("`ledger.py start <that base>`", message)
            self.assertIn("Nothing reported", message)
            self.assertEqual(output.getvalue(), "")
            # The same file without them reports, and its assessment counts as this round's.
            supplied.write_text(json.dumps({"repository": "sample/product", "assessments": [mine]}))
            # It was also assessed in an earlier round, at another head; this round's assessment is the one named.
            rows, errors, _ = self.collect([[opened], []], raw, argv=argv, heads={482: "a" * 40})
            self.assertEqual(rows[482]["assessment"]["head"], record["head"])
            self.assertIn("ASSESSED IN THIS ROUND, NO REVIEW OR COMMENT POSTED IN IT FROM Alex: "
                          "#482 (assessed at ccccccccc, head unchanged)", errors)
            self.assertNotIn("EARLIER ROUND", errors)
            # A scoped PR that closed stays in the report, so its assessment is accepted.
            closed, scope = {**opened, "state": "CLOSED"}, Path(tmp) / "scope.json"
            scope.write_text("[482]")
            rows, _, _ = self.collect([[], [], closed], raw, argv=(*argv, "--scope", str(scope)))
            self.assertEqual(rows[482]["verdict"], "CLOSED")
            with self.assertRaises(SystemExit) as stop:
                self.collect([[], []], raw, argv=argv)
            self.assertIn("outside this report: #482. ", str(stop.exception.code))
            self.assertIn("--scope (which keeps a PR that closed or returned to draft)", str(stop.exception.code))

    def test_review_that_no_longer_covers_the_head_is_named_instead_of_counted(self):
        raw, record = fixture()
        head, old = record["head"], "a" * 40
        mine = lambda state, commit, at="2026-11-03T15:20:00Z": [{
            "id": 12, "state": state, "submittedAt": at, "author": {"login": "Alex", "type": "User"},
            "commitOid": commit, "url": "https://example.test/review/12", "body": "Verified the migration."}]
        opened = lambda **changes: {**raw["pr"], "id": "PR_482", "isDraft": False, "state": "OPEN",
                                    "mergeStateStatus": "BLOCKED", "mergedAt": None, "headRefName": "filters",
                                    "isCrossRepository": False, "reviewDecision": "REVIEW_REQUIRED", **changes}
        # A push dismissed the approval: it is in the round's reviews, and it must not read as current.
        rows, errors, _ = self.collect([[opened(reviews=mine("DISMISSED", old))], []], raw)
        row = rows[482]
        self.assertEqual(row["my_review"], {"state": "DISMISSED", "commit_id": old, "at_head": False,
                                            "dismissed": True, "submitted_at": "2026-11-03T15:20:00Z"})
        self.assertEqual((row["verdict"], row["reviewed_at"]), ("NEEDS_REVIEW", "2026-11-03T15:20:00Z"))
        self.assertIn("YOUR REVIEW NO LONGER COVERS THE HEAD: #482 (DISMISSED; reviewed aaaaaaaaa, head ccccccccc)", errors)
        self.assertIn("that review was dismissed", render([row], "main"))
        # Approved in an earlier round, pushed since: the saved head is compared for you.
        rows, errors, _ = self.collect([[opened(reviews=mine("APPROVED", old, "2026-11-01T10:00:00Z"))], []], raw,
                                       heads={482: old})
        self.assertEqual(rows[482]["reviews"], [])
        self.assertIn("#482 (APPROVED at an earlier commit; reviewed aaaaaaaaa, head ccccccccc)", errors)
        self.assertIn("#482 (last head aaaaaaaaa, HEAD MOVED to ccccccccc)", errors)
        rows, errors, _ = self.collect([[opened(reviews=mine("APPROVED", head, "2026-11-01T10:00:00Z"))], []], raw,
                                       heads={482: head})
        self.assertIn("#482 (last head ccccccccc, head unchanged)", errors)
        # In force at head and GitHub still requires a review: the next reviewer is someone else.
        self.assertEqual(rows[482]["verdict"], "APPROVED_NEEDS_ANOTHER_REVIEWER")
        self.assertIn("APPROVED BY YOU AT HEAD AND STILL REVIEW_REQUIRED: #482\n"
                      "  -> rules for sample/product@main, Alex, {482: 'filters'}\n"
                      "  -> GitHub does not report which rule holds the gate", errors)
        self.assertNotIn("detect_setup.sh", errors)
        self.assertNotIn("NO LONGER COVERS", errors)
        # A fork's head branch is not a branch of this repository.
        fork = opened(reviews=mine("APPROVED", head, "2026-11-01T10:00:00Z"), isCrossRepository=True)
        self.assertIn("  -> rules for sample/product@main, Alex, {}\n", self.collect([[fork], []], raw)[1])
        source = render([rows[482]], "main")
        self.assertIn("Another eligible approver to review", source)
        self.assertIn("GitHub still requires another review", source)
        self.assertNotIn("Reviewer to check this change", source)
        # An approval that cleared the gate, and a merged PR reviewed at an earlier commit, raise nothing.
        cleared = opened(reviews=mine("APPROVED", head), reviewDecision="APPROVED", mergeStateStatus="CLEAN")
        landed = opened(reviews=mine("APPROVED", old), state="MERGED", mergedAt="2026-11-03T16:00:00Z")
        for reads in ([[cleared], []], [[], [landed]]):
            rows, errors, _ = self.collect(reads, raw)
            self.assertNotIn("NO LONGER COVERS", errors)
            self.assertNotIn("STILL REVIEW_REQUIRED", errors)
            self.assertNotIn("rules for", errors)
            self.assertNotIn("dismissed", render([rows[482]], "main"))
        # Unreadable reviews are unknown, never "no review".
        rows, _, _ = self.collect([[opened(reviews=mine("APPROVED", head))], []], {**raw, "failedFetches": ["reviews"]})
        self.assertIsNone(rows[482]["my_review"])
        self.assertEqual(rows[482]["verdict"], "NEEDS_REVIEW")

    def test_gated_approval_with_a_ready_assessment_hands_off_to_another_approver(self):
        _, record = fixture()
        item = assessment(482, head=record["head"], base=record["base"])
        proposals = {"repository": record["repository"], "assessments": [item]}
        record["verdict"] = "APPROVED_NEEDS_ANOTHER_REVIEWER"
        source = render([record], "main", assessments=proposals)
        self.assertIn("<strong>Next</strong> Another eligible approver to review", source)
        record["verdict"] = "NEEDS_REVIEW"
        self.assertNotIn("Another eligible approver", render([record], "main", assessments=proposals))

    def test_scope_marks_late_prs_and_a_pr_that_returned_to_draft(self):
        raw, _ = fixture()
        opened = {**raw["pr"], "id": "PR_482", "isDraft": False, "reviewDecision": "REVIEW_REQUIRED",
                  "state": "OPEN", "mergeStateStatus": "BLOCKED", "mergedAt": None}
        late = {**opened, "number": 483, "id": "PR_483", "createdAt": "2026-11-01T14:00:00Z"}
        landed_late = {**opened, "number": 484, "id": "PR_484", "createdAt": "2026-11-02T14:00:00Z",
                       "state": "MERGED", "mergedAt": "2026-11-03T16:00:00Z"}
        redrafted = {**opened, "number": 485, "id": "PR_485", "createdAt": "2026-11-02T15:00:00Z", "isDraft": True}
        with tempfile.TemporaryDirectory() as tmp:
            scope = Path(tmp) / "scope.json"
            scope.write_text("[482, 485]")
            # The open listing drops drafts; the scope file is what keeps #485 in the report.
            rows, errors, _ = self.collect([[opened, late, redrafted], [landed_late], opened, redrafted], raw,
                                           argv=("--since", "2026-11-03T00:00:00Z", "--scope", str(scope)))
            self.assertEqual({n: r["in_scope"] for n, r in rows.items()}, {482: True, 483: False, 484: False, 485: True})
            self.assertEqual((rows[485]["verdict"], rows[485]["is_draft"], rows[482]["is_draft"]), ("DRAFT", True, False))
            self.assertIn("JOINED AFTER THE SCOPE SNAPSHOT: #483, #484 (merged)", errors)
            self.assertNotIn("NO --scope", errors)
            source = render([rows[485]], "main")
            self.assertIn("Developer to mark the change ready for review", source)
            scope.write_text('{"prs": [482]}')
            with self.assertRaisesRegex(SystemExit, "not a JSON list of PR numbers"):
                self.collect([[opened], []], raw, argv=("--scope", str(scope), "--since", REVISION))
        # A PR that returns to draft between the listing and its collection reports the later state.
        rows, _, _ = self.collect([[{**opened}], []], raw, later={"isDraft": True})
        self.assertEqual((rows[482]["verdict"], rows[482]["is_draft"]), ("DRAFT", True))
        # Without a scope file membership is unknown, and the report says so.
        rows, errors, _ = self.collect([[opened, late], []], raw)
        self.assertEqual([r["in_scope"] for r in rows.values()], [None, None])
        self.assertIn("NO --scope", errors)
        self.assertNotIn("JOINED AFTER", errors)

    def test_reviews_posted_outside_the_round_helper_are_labelled_and_named(self):
        raw, _ = fixture()
        opened = {**raw["pr"], "id": "PR_482", "isDraft": False, "reviewDecision": "CHANGES_REQUESTED",
                  "state": "OPEN", "mergeStateStatus": "CLEAN", "mergedAt": None,
                  "comments": [{"id": 70, "author": {"login": "Alex", "type": "User"}, "body": "Checked the rollback.",
                                "createdAt": "2026-11-03T15:40:00Z", "url": "https://example.test/comment/70"},
                               {"id": 71, "author": {"login": "Maya", "type": "User"}, "body": "Thanks.",
                                "createdAt": "2026-11-03T15:45:00Z", "url": "https://example.test/comment/71"}]}
        named = "POSTED FROM Alex'S ACCOUNT IN THIS ROUND'S WINDOW, NOT RECORDED BY review_write.py"
        label = "Not posted through this round's helper"
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, XDG_STATE_HOME=tmp):
            # Nothing recorded: the review and the comment from this account came from somewhere else.
            rows, errors, _ = self.collect([[opened], []], raw)
            row = rows[482]
            self.assertEqual([(r["id"], r["posted_by"]) for r in row["reviews"]], [(11, "outside the round")])
            self.assertEqual([c["posted_by"] for c in row["comments"]], ["outside the round"])
            # With no post recorded in the window, one line says so instead of listing every item.
            self.assertIn("review_write.py RECORDED NO POST IN THIS ROUND'S WINDOW: all 2 review(s) and comment(s) from Alex", errors)
            self.assertNotIn(named, errors)
            # A post recorded before the window is not one of this round's either.
            ledger.record_write("sample/product", 400, "comment", "e" * 40, "https://example.test/comment/1")
            with patch.object(ledger, "_now", return_value="2026-11-01T00:00:00Z"):
                ledger.record_write("sample/product", 401, "comment", "e" * 40, "https://example.test/comment/2")
            ledger_file = Path(tmp) / "pr-review-round/sample__product/writes.jsonl"
            earlier = [line for line in ledger_file.read_text().splitlines() if "comment/2" in line]
            ledger_file.write_text("\n".join(earlier) + "\n")
            _, errors, _ = self.collect([[opened], []], raw)
            self.assertIn("RECORDED NO POST IN THIS ROUND'S WINDOW", errors)
            # Once the helper posted in the window, each outside item is named.
            ledger.record_write("sample/product", 400, "comment", "e" * 40, "https://example.test/comment/1")
            _, errors, _ = self.collect([[opened], []], raw)
            self.assertNotIn("RECORDED NO POST", errors)
            self.assertIn(named + ": #482 CHANGES_REQUESTED https://example.test/review/11, "
                          "#482 comment https://example.test/comment/70", errors)
            self.assertNotIn("comment/71", errors)
            self.assertEqual(render([row], "main").replace("&#x27;", "'").count(label), 2)
            # Dismissing a review through the helper does not make the helper its author.
            ledger.record_write("sample/product", 482, "dismiss", row["head"], "https://example.test/review/11")
            rows, _, _ = self.collect([[opened], []], raw)
            self.assertEqual([r["posted_by"] for r in rows[482]["reviews"]], ["outside the round"])
            # The helper recorded the review; only the hand-posted comment is left.
            ledger.record_write("sample/product", 482, "request-changes", row["head"], "https://example.test/review/11")
            rows, errors, _ = self.collect([[opened], []], raw)
            row = rows[482]
            self.assertEqual([r["posted_by"] for r in row["reviews"]], ["round"])
            self.assertIn(named + ": #482 comment https://example.test/comment/70", errors)
            self.assertNotIn("review/11", errors.split(named)[1].split("\n")[0])
            self.assertEqual(render([row], "main").replace("&#x27;", "'").count(label), 1)
            ledger.record_write("sample/product", 482, "comment", row["head"], "https://example.test/comment/70")
            rows, errors, _ = self.collect([[opened], []], raw)
            self.assertNotIn(named, errors)
            self.assertNotIn(label, render([rows[482]], "main").replace("&#x27;", "'"))
        # Report JSON written before this field existed renders without a guess.
        _, record = fixture()
        self.assertNotIn(label, render([record], "main").replace("&#x27;", "'"))

    def test_open_round_start_bounds_the_report_before_the_clock_fallback(self):
        raw, _ = fixture()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, XDG_STATE_HOME=tmp), \
                patch.object(ledger, "repo_slug", return_value="sample/product"):
            _, errors, gh = self.collect([[], []], raw, argv=())
            self.assertIn("falling back to a 12h window", errors)
            rid = ledger.round_start("main", "sample/product")
            ledger.round_start("release", "sample/product")
            _, errors, gh = self.collect([[], []], raw, argv=())
            self.assertIn(f"start of the open round ({rid})", errors)
            self.assertIn(f"merged:>={rid}", gh.call_args_list[1][0][0])
            # A completed round is still the better boundary.
            ledger.round_end(rid, [], "sample/product", reconciliation=[])
            ended = ledger.last_round("main", "sample/product")["ended_at"]
            ledger.round_start("main", "sample/product")
            _, errors, gh = self.collect([[], []], raw, argv=())
            self.assertIn(f"previous round ended {ended}", errors)


if __name__ == "__main__":
    unittest.main()
