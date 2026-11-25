"""queue.py --next: the work list a settle or watch round acts on, against recorded forge reads and a temporary ledger."""
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
import authority as authority_script
import ledger
from decision_fixtures import assessment, HEAD, BASE, REVISION
from test_owner_decisions import adr_gated

spec = importlib.util.spec_from_file_location("round_queue", SKILL / "scripts/queue.py")
queue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(queue)

PENDING = [{"name": "test", "status": "IN_PROGRESS", "conclusion": None}]


def row(number, head=HEAD, decision="REVIEW_REQUIRED", auto=False, checks=()):
    return {"number": number, "title": f"PR {number}", "author": {"login": "author"},
            "createdAt": f"2026-11-{number - 10:02d}T12:00:00Z", "isDraft": False, "reviewDecision": decision,
            "headRefOid": head, "baseRefOid": BASE, "updatedAt": REVISION, "mergeStateStatus": "CLEAN",
            "mergeable": "MERGEABLE", "additions": 1, "deletions": 0, "headRefName": f"pr-{number}",
            "isCrossRepository": False, "autoMergeRequest": {"enabledAt": REVISION} if auto else None,
            "_checks": list(checks)}


def evidence(approved_at=None):
    """The collected reviews: the reviewer's approval at `approved_at`, or none."""
    reviews = [{"id": 1, "state": "APPROVED", "user": {"login": "reviewer"}, "submitted_at": REVISION,
                "commit_id": approved_at}] if approved_at else []
    return {"failedFetches": [], "truncatedSources": [], "timeline": [], "requestedReviewers": [],
            "pr": {"reviews": reviews}}


class NextActionTests(unittest.TestCase):
    def setUp(self):
        state = tempfile.TemporaryDirectory()
        self.addCleanup(state.cleanup)
        self.tmp = Path(state.name)
        for active in (patch.dict(os.environ, XDG_STATE_HOME=state.name),
                       patch.object(ledger, "repo_slug", return_value="owner/repo")):
            active.start()
            self.addCleanup(active.stop)
        self.round = ledger.round_start("main", "owner/repo")

    def save(self, *items):
        for item in items:
            ledger.record_assessment(self.round, item, "owner/repo")

    def next_actions(self, rows, scope, reviews=None, base_only=()):
        """Run `queue.py main --scope --next --authority` against these listed rows; returns what it printed."""
        (self.tmp / "scope.json").write_text(json.dumps(scope))
        record = authority_script.build("owner/repo", scope, {"level": "review", "approvals": True,
                                                               "mode": "settle", "instruction": "settle it"}, {})
        (self.tmp / "authority.json").write_text(json.dumps(record))
        scoped = [r for r in rows if r["number"] in scope]
        reads = [copy.deepcopy(rows)]
        reads += [{"files": [{"path": "src/app.py"}], "statusCheckRollup": r["_checks"], "body": ""} for r in scoped]
        reads += [{k: r[k] for k in ("headRefOid", "baseRefOid", "updatedAt")} for r in scoped]
        output = io.StringIO()
        with patch.object(sys, "argv", ["queue.py", "main", "--scope", str(self.tmp / "scope.json"), "--next",
                                        "--authority", str(self.tmp / "authority.json")]), \
                patch.object(queue, "gh_json", side_effect=reads), \
                patch.object(queue, "repo_slug", return_value="owner/repo"), \
                patch.object(queue, "handled_requests", return_value=[]), \
                patch.object(queue, "me", return_value="reviewer"), \
                patch.object(queue, "stack_of", return_value=None), \
                patch.object(queue, "collect", side_effect=lambda slug, n: evidence((reviews or {}).get(n))), \
                patch.object(queue, "reapprove_check", side_effect=lambda slug, n: ({"base_only": n in base_only}, None)), \
                contextlib.redirect_stdout(output):
            queue.main()
        return output.getvalue()

    def sections(self, text):
        work = text.split("Waiting on someone else:")[0]
        waiting = text.split("Waiting on someone else:")[1].split("JOINED")[0]
        return work, waiting

    def mixed_queue(self):
        self.save(assessment(17), assessment(18), assessment(19), adr_gated(20), assessment(21))
        return [row(16 + 6, head="e" * 40),  # #22 opened after the scope snapshot
                row(17, head="c" * 40), row(18, head="d" * 40), row(19, decision="APPROVED"), row(20),
                row(21, decision="APPROVED", auto=True, checks=PENDING)]

    def test_round_actions_and_waits_in_a_mixed_queue(self):
        text = self.next_actions(self.mixed_queue(), [16, 17, 18, 19, 20, 21],
                                 reviews={17: HEAD, 18: HEAD, 21: HEAD}, base_only={18})
        work, waiting = self.sections(text)
        self.assertIn("Round work on 3 of 6 scoped PR(s), run mode settle:", work)
        self.assertIn("#17     review at new head ccccccccc", work)
        self.assertIn("#18     reapprove: only clean base merges since the round's approval", work)
        self.assertIn("#19     sweep: approved with auto-merge off", work)
        self.assertNotIn("#20", work)
        self.assertNotIn("#21", work)
        self.assertIn("#20     owner decision adr:183 (Product owner); ask it with ledger.py waiting", waiting)
        self.assertIn("#21     CI pending: 1 check(s); GitHub: auto-merge is on", waiting)
        self.assertIn("JOINED, outside this round until a new intake answer adds them: #22", text)
        self.assertIn("LEFT the queue: #16", text)
        self.assertNotIn("settled", text)

    def test_settled_when_only_others_have_work_and_an_answer_makes_work_again(self):
        rows = self.mixed_queue()
        text = self.next_actions(rows, [20, 21], reviews={21: HEAD})
        self.assertIn("Round work on 0 of 2 scoped PR(s)", text)
        self.assertTrue(text.rstrip().endswith("settled: no scoped PR has an action left for the round"), text)
        ledger.decide("adr:183", "accept", "Accept ADR 183", repo="owner/repo")
        text = self.next_actions(rows, [20, 21], reviews={21: HEAD})
        work, waiting = self.sections(text)
        self.assertIn("#20     decision answered: approve, then auto-merge", work)
        self.assertNotIn("#20", waiting)
        self.assertNotIn("settled", text)


if __name__ == "__main__":
    unittest.main()
