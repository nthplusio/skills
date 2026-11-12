import contextlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
import round_report
from pr_history import normalize
from render_round import render
from decision_fixtures import assessment, REVISION


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
        self.assertIn("Approved · merge queue unknown", source)

    def test_dense_row_uses_product_summary_and_keeps_original_evidence_in_details(self):
        _, record = fixture()
        record["summary"] = "Keep saved filters when upgrading"
        source = render([record], "main")
        row = source.split('<article class="pr-row"', 1)[1]
        collapsed, detail = row.split('<details class="history-detail">', 1)
        self.assertIn("Keep saved filters when upgrading", collapsed)
        self.assertIn("Changes requested", collapsed)
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


if __name__ == "__main__":
    unittest.main()
