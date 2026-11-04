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
              "author": "Maya", "head": head, "state": "OPEN", "verdict": "CHANGES_REQUESTED",
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
        proposals = {"repository": record["repository"], "assessments": [{"number": 482, "head": record["head"],
                     "assessed_at": "2026-11-03T16:00:00Z", "verdict": "APPROVE", "owner": "Maintainer",
                     "blocker": "None verified at the assessed head.", "body": "Rollback verified.",
                     "provenance": "Reused prior-round assessment; probes not rerun."}]}
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
        proposals = {"repository": record["repository"], "assessments": [{"number": 482, "head": record["head"],
                     "assessed_at": "2026-11-03T16:00:00Z", "verdict": "APPROVE", "owner": "Maintainer",
                     "blocker": "None verified at the assessed head.", "body": "Rollback verified."}]}
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

    def test_queue_read_failure_never_looks_like_an_empty_complete_round(self):
        with patch.object(sys, "argv", ["round_report.py", "main", "--since", "2026-11-03T00:00:00Z", "--me", "Alex"]), \
                patch.object(round_report, "repo_slug", return_value="sample/product"), \
                patch.object(round_report, "gh", return_value=None), self.assertRaises(SystemExit):
            round_report.main()


if __name__ == "__main__":
    unittest.main()
