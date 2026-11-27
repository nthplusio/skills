"""queue.py --next: the work list a settle or watch round acts on, against recorded forge reads and a temporary ledger."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
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


def row(number, head=HEAD, decision="REVIEW_REQUIRED", auto=False, checks=(), node=None):
    return {"number": number, "title": f"PR {number}", "author": {"login": "author"},
            "createdAt": f"2026-11-{number - 10:02d}T12:00:00Z", "isDraft": False, "reviewDecision": decision,
            "headRefOid": head, "baseRefOid": BASE, "updatedAt": REVISION, "mergeStateStatus": "CLEAN",
            "mergeable": "MERGEABLE", "additions": 1, "deletions": 0, "headRefName": f"pr-{number}",
            "isCrossRepository": False, "autoMergeRequest": {"enabledAt": REVISION} if auto else None,
            "_checks": list(checks), **({"id": node} if node else {})}


def evidence(approved_at=None, others=(), timeline=()):
    """The collected reviews: the reviewer's approval at `approved_at`, or none, then `others`; and the timeline."""
    reviews = [{"id": 1, "state": "APPROVED", "user": {"login": "reviewer"}, "submitted_at": REVISION,
                "commit_id": approved_at}] if approved_at else []
    return {"failedFetches": [], "truncatedSources": [], "timeline": list(timeline), "requestedReviewers": [],
            "pr": {"reviews": reviews + list(others)}}


BOT = {"login": "review-bot[bot]", "type": "Bot"}


def queued_reply(queued):
    """The merge-queue GraphQL read: PR node ids in `queued` have an entry at their head."""
    def run(command, **kwargs):
        node = next(a.split("=", 1)[1] for a in command if a.startswith("id="))
        entry = {"id": "entry", "state": "QUEUED", "position": 1} if node in queued else None
        payload = {"data": {"node": {"headRefOid": HEAD, "mergeQueueEntry": entry}}}
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
    return run


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

    def next_actions(self, rows, scope, reviews=None, base_only=(), policies=None, others=None, timeline=None,
                     queued=()):
        """Run `queue.py main --scope --next --authority` against these listed rows; returns what it printed.
        `others` and `timeline` map a PR to more reviews and to timeline events; `queued` names merge-queue nodes."""
        (self.tmp / "scope.json").write_text(json.dumps(scope))
        record = authority_script.build("owner/repo", scope, {"level": "review", "approvals": True, "mode": "settle",
                                                               "instruction": "settle it", "policies": policies or {}}, {})
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
                patch.object(queue, "collect", side_effect=lambda slug, n: evidence(
                    (reviews or {}).get(n), (others or {}).get(n, ()), (timeline or {}).get(n, ()))), \
                patch.object(subprocess, "run", side_effect=queued_reply(queued)), \
                patch.object(queue, "reapprove_check", side_effect=lambda slug, n, since=None: ({"base_only": n in base_only}, None)), \
                contextlib.redirect_stdout(output):
            queue.main()
        return output.getvalue()

    def sections(self, text):
        work = text.split("Waiting on")[0]
        waiting = text.split("Waiting on someone else:")[1].split("JOINED")[0]
        return work, waiting

    def yours(self, text):
        return text.split("Waiting on you:")[1].split("Waiting on someone else:")[0]

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
        self.assertIn("#20     owner decision adr:183 (Product owner); ask it with ledger.py waiting", self.yours(text))
        self.assertNotIn("#20", waiting)
        self.assertIn("#21     CI pending: 1 check(s); GitHub: auto-merge is on", waiting)
        self.assertIn("JOINED, outside this round until a new intake answer adds them: #22", text)
        self.assertIn("LEFT the queue: #16", text)
        self.assertNotIn("settled", text)

    def test_owner_decisions_split_between_you_and_someone_else_as_ledger_waiting_does(self):
        # Live: Seth's own decisions were listed under "Waiting on someone else". The user is `reviewer`.
        for_me, for_alex = adr_gated(30), adr_gated(31)
        for_me["decisions"][0].update(subject="adr:184", owner_login="reviewer")
        for_alex["decisions"][0].update(subject="adr:185", owner_login="alex")
        self.save(for_me, for_alex)
        text = self.next_actions([row(30), row(31)], [30, 31])
        _, waiting = self.sections(text)
        self.assertIn("#30     owner decision adr:184 (Product owner); ask it with ledger.py waiting", self.yours(text))
        self.assertNotIn("#31", self.yours(text))
        self.assertIn("#31     owner decision adr:185 (Product owner)", waiting)
        self.assertNotIn("#30", waiting)
        self.assertTrue(text.rstrip().endswith("settled: no scoped PR has an action left for the round"), text)

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


    def test_a_bot_comment_at_the_head_over_its_older_changes_request_is_dismiss_bot(self):
        self.save(assessment(23))
        reviews = [{"id": 9, "state": "CHANGES_REQUESTED", "user": BOT, "submitted_at": "2026-11-11T19:00:00Z",
                    "commit_id": "c" * 40},
                   {"id": 10, "state": "COMMENTED", "user": BOT, "submitted_at": "2026-11-11T19:30:00Z", "commit_id": HEAD}]
        rows = [row(23, decision="CHANGES_REQUESTED")]
        work, _ = self.sections(self.next_actions(rows, [23], others={23: reviews},
                                                  policies={"dismiss-bot-review": "auto"}))
        self.assertIn("#23     dismiss-bot: review-bot[bot]'s changes request at ccccccccc still blocks", work)
        self.assertIn("findings.py 23 --draft 9", work)
        # Under the default ask, the round does not list the dismissal as its own work.
        work, waiting = self.sections(self.next_actions(rows, [23], others={23: reviews}))
        self.assertNotIn("dismiss-bot:", work)
        self.assertIn("dismissing it needs the dismiss-bot-review policy", waiting)
        # A changes request at the head is a live verdict, not a stale one.
        live = [{**reviews[0], "commit_id": HEAD}, reviews[1]]
        text = self.next_actions(rows, [23], others={23: live}, policies={"dismiss-bot-review": "auto"})
        self.assertNotIn("dismiss", text)

    def test_the_sweep_skips_a_pr_already_in_the_merge_queue(self):
        self.save(assessment(24), assessment(25))
        rows = [row(24, decision="APPROVED", node="PR_24"), row(25, decision="APPROVED", node="PR_25")]
        work, waiting = self.sections(self.next_actions(rows, [24, 25], queued={"PR_24"}))
        self.assertNotIn("#24", work)
        self.assertIn("#24     GitHub: in the merge queue", waiting)
        self.assertIn("#25     sweep: approved with auto-merge off", work)

    def test_the_same_state_twice_prints_unchanged(self):
        self.save(assessment(19))
        rows = [row(19, decision="APPROVED")]
        first = self.next_actions(rows, [19])
        self.assertIn("#19     sweep", first)
        second = self.next_actions(rows, [19])
        self.assertEqual(second.strip(), "unchanged: the work list matches the last one")

    def test_a_check_that_failed_before_the_base_changed_is_stale_not_red(self):
        # Live #3663: "select" in "Build preview pair" failed before GitHub retargeted the PR.
        self.save(assessment(26))
        failed = {"name": "select", "workflowName": "Build preview pair", "conclusion": "FAILURE",
                  "startedAt": "2026-11-11T19:00:00Z", "detailsUrl": "https://github.com/o/r/actions/runs/77/job/1"}
        moved = [{"event": "base_ref_changed", "created_at": "2026-11-11T19:10:00Z"}]
        text = self.next_actions([row(26, checks=[failed])], [26], timeline={26: moved})
        self.assertIn("stale check: select (Build preview pair) failed before the base changed", text)
        self.assertIn("gh run rerun 77 --failed", text)
        self.assertNotIn("author: red CI", text)
        # The same failure after the base change is red CI.
        text = self.next_actions([row(26, checks=[{**failed, "startedAt": "2026-11-11T19:20:00Z"}])], [26],
                                 timeline={26: moved})
        self.assertIn("author: red CI", text)


    def test_a_pr_the_merge_queue_removed_is_a_flake_requeue_not_a_sweep(self):
        self.save(assessment(27))
        removed = {27: [{"event": "added_to_merge_queue", "created_at": "2026-11-11T19:00:00Z"},
                        {"event": "removed_from_merge_queue", "created_at": "2026-11-11T19:20:00Z"}]}
        rows = [row(27, decision="APPROVED")]
        work, _ = self.sections(self.next_actions(rows, [27], timeline=removed, policies={"requeue-flake": "auto"}))
        self.assertIn("#27     requeue-flake: removed from the merge queue", work)
        self.assertNotIn("sweep", work)
        ledger.record_write("owner/repo", 27, "requeue", HEAD)
        work, waiting = self.sections(self.next_actions(rows, [27], timeline=removed, policies={"requeue-flake": "auto"}))
        self.assertNotIn("#27", work)
        self.assertIn("removed from the merge queue again after the round's one flake requeue", waiting)


if __name__ == "__main__":
    unittest.main()
