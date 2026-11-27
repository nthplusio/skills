"""Local forge doubles only; these tests never contact GitHub."""
import base64
import contextlib
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import authority as authority_script
import branch_rules
import branch_write
import freshness
import land
import ledger
import merge_queue
import review_write
import round_report
from md_to_html import render
from decision_fixtures import assessment, authority, bundle, BASE, REVISION, TARGET

HEAD = "a" * 40
MOVED = {**TARGET, "sha": "f" * 40}
LATER = "2026-11-11T21:00:00Z"
BOT = {"login": "review-bot[bot]", "type": "Bot"}
PERSON = {"login": "alex", "type": "User"}
# Review 9's inline findings from review-bot[bot], and the records an assessment keeps for them.
INLINE = [{"id": 301, "pull_request_review_id": 9, "path": "src/app.py", "line": 12, "body": "Unchecked None"},
          {"id": 302, "pull_request_review_id": 9, "path": "src/db.py", "line": None, "original_line": 40,
           "body": "Possible N+1 query"}]
VERIFIED = [{"comment": 301, "status": "fixed", "file": "src/app.py", "line": 14, "observation": "Guard added"},
            {"comment": 302, "status": "overstated", "file": "src/db.py", "line": 40,
             "observation": "Caller batches the ids"}]
# The base moved without touching the PR's one file.
BENIGN_BASE = {"compare": {"status": "ahead", "files": [{"filename": "docs/other.md"}]},
               "files": [{"filename": "src/app.py"}]}


def freshness_read(reads, command):
    """Answer the freshness check's compare, PR-files and timeline reads; a read not in `reads` fails like the API."""
    for key in ("compare", "files", "timeline"):
        if f"/{key}" in command[2]:
            if key not in reads:
                return subprocess.CompletedProcess(command, 1, "", f"{key} unavailable")
            payload = [reads[key]] if "--slurp" in command else reads[key]
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
    return None


def pull(**changes):
    return {"head": {"sha": HEAD}, "state": "open", "base": {"sha": BASE, "ref": "main"}, "updated_at": REVISION,
            "draft": False, "auto_merge": None, "user": {"login": "author"}, "mergeable": True,
            "mergeable_state": "clean", **changes}


def state(**changes):
    return {"state": "OPEN", "headRefOid": HEAD,
            "baseRefOid": BASE, "baseRefName": "main", "target": TARGET, "updatedAt": REVISION,
            "reviewDecision": "APPROVED", "mergeStateStatus": "CLEAN",
            "queue_state": "not_queued", "isDraft": False, **changes}


class Elements(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.tags = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class LandingTests(unittest.TestCase):
    def run_land(self, states, args=None, failure=False, item=None, permission=None, reads=None, prior=(),
                 rules=(), pusher=None, checks=(), reviews=(), codeowners=None):
        """The last five answer an own-PR landing's reads: the base's rulesets, the branch's last pusher,
        `gh pr checks --required`, the PR's reviews, and the base's CODEOWNERS (None: no file). The
        authenticated user is `reviewer`."""
        output = io.StringIO()
        snapshots = iter(states)
        writes = []
        current = {}

        def forge(command, **kwargs):
            nonlocal current
            if command[0] == "git":
                return subprocess.CompletedProcess(command, 128, "", "fatal: not a git repository")
            if command[:3] == ["gh", "pr", "view"]:
                current = next(snapshots, current)
                payload = {"id": "PR_fixture", **current}
            elif command[:2] == ["gh", "api"] and "/git/ref/heads/" in command[2]:
                target = current.get("target") or {}
                payload = {"ref": "refs/heads/main", "object": {"type": "commit", "sha": target.get("sha")}}
            elif command[:3] == ["gh", "api", "user"]:
                payload = {"login": "reviewer"}
            elif command[:2] == ["gh", "api"] and "/rules/branches/" in command[2]:
                payload = list(rules)
            elif command[:2] == ["gh", "api"] and "/activity?" in command[2]:
                payload = [{"actor": {"login": pusher}}] if pusher else []
            elif command[:3] == ["gh", "pr", "checks"]:
                payload = list(checks)
            elif command[:2] == ["gh", "api"] and "/pulls/17/reviews?" in command[2]:
                payload = [list(reviews)]
            elif command[:2] == ["gh", "api"] and command[2] == "repos/owner/repo/pulls/17":
                payload = {"user": current.get("author"), "base": {"ref": "main"},
                           "head": {"ref": "feature", "repo": {"full_name": "owner/repo"}}}
            elif command[:2] == ["gh", "api"] and "/pulls/17/files?" in command[2] and "files" not in (reads or {}):
                payload = [[{"filename": "src/app.py"}]]
            elif command[:2] == ["gh", "api"] and "/contents/" in command[2]:
                if codeowners is None or not command[2].startswith("repos/owner/repo/contents/CODEOWNERS?"):
                    return subprocess.CompletedProcess(command, 1, "", "gh: Not Found (HTTP 404)")
                payload = {"content": base64.b64encode(codeowners.encode()).decode()}
            elif command[:2] == ["gh", "api"] and freshness_read(reads or {}, command):
                return freshness_read(reads or {}, command)
            elif command[:3] == ["gh", "api", "graphql"] and "stackEntry" in command[4]:
                payload = {"data": {"repository": {"pullRequest": {"stackEntry": current.get("stack_entry")}}}}
            elif command[:3] == ["gh", "api", "graphql"]:
                if current.get("queue_state") == "unknown":
                    return subprocess.CompletedProcess(command, 1, "", "queue unavailable")
                payload = {"data": {"node": {
                    "headRefOid": current.get("headRefOid"),
                    "mergeQueueEntry": {"id": "entry"} if current.get("queue_state") == "queued" else None,
                }}}
            elif command[:3] == ["gh", "pr", "merge"]:
                writes.append(command)
                return subprocess.CompletedProcess(command, int(failure), "", "denied" if failure else "")
            else:
                raise AssertionError(command)
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

        with tempfile.TemporaryDirectory() as tmp:
            assessment_file = Path(tmp) / "assessments.json"
            authority_file = Path(tmp) / "authority.json"
            assessment_file.write_text(json.dumps(bundle(item)))
            authority_file.write_text(json.dumps(permission or authority()))
            argv = args or ["--enqueue", f"17:{HEAD}"]
            if {"--enqueue", "--enable-auto-merge", "--requeue-flake"} & set(argv):
                argv = [*argv, "--repo", "owner/repo", "--authority", str(authority_file),
                        "--assessments", str(assessment_file)]
            with patch.object(sys, "argv", ["land.py", *argv]), \
                patch.object(subprocess, "run", side_effect=forge), \
                patch.dict(os.environ, XDG_STATE_HOME=tmp), \
                patch.object(land.time, "sleep"), patch.object(land, "MAX_POLLS", 2), \
                patch.object(freshness.time, "sleep"), contextlib.redirect_stdout(output):
                for write in prior:
                    ledger.record_write("owner/repo", 17, write, HEAD)
                code = land.main()
                self.recorded = ledger.writes("owner/repo")
        for command in writes:
            self.assertEqual(command[:8], ["gh", "pr", "merge", "17", "--repo", "owner/repo", "--match-head-commit", HEAD])
        return len(writes), output.getvalue(), code

    def test_revoked_approval_stops_enqueue(self):
        writes, output, code = self.run_land([state(), state(reviewDecision="CHANGES_REQUESTED")])
        self.assertEqual(writes, 1, output)
        self.assertIn("post-write head or approval changed", output)
        self.assertEqual(code, 1)

    def test_accepted_landing_requests_are_recorded_and_refused_ones_are_not(self):
        self.run_land([state(), state(state="MERGED")])
        self.assertEqual([(w["number"], w["action"], w["head"], w["url"]) for w in self.recorded],
                         [(17, "enqueue", HEAD, None)])
        self.run_land([state(), state(state="MERGED")], ["--enable-auto-merge", f"17:{HEAD}"])
        self.assertEqual([w["action"] for w in self.recorded], ["enable-auto-merge"])
        self.run_land([state(), state()], failure=True)
        self.assertEqual(self.recorded, [])
        self.run_land([state(headRefOid="b" * 40)])
        self.assertEqual(self.recorded, [])
        self.run_land([state()], ["--watch", "17"])
        self.assertEqual(self.recorded, [])

    def test_a_flaky_removal_from_the_merge_queue_is_requeued_once(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            (root / ".nthplusio-skills").mkdir()
            (root / ".nthplusio-skills/review.json").write_text(json.dumps(
                {"schema_version": 1, "references": {"flakes": {"files": ["flakes.md"]}}}))
            (root / "flakes.md").write_text("- INT-2911: `test_preview_pair_timeout` times out under load\n")
            log = root / "failed.log"
            previous = os.getcwd()
            os.chdir(root)  # the profile is read from the repository root, as from a round
            self.addCleanup(os.chdir, previous)
            item = assessment(evidence_inputs={**assessment()["evidence_inputs"],
                                               "policy": ledger.review_config(".")["revision"]})
            permission = authority(grants=(), policies={"requeue-flake": "auto"})
            run = lambda text, prior=(): (log.write_text(text), self.run_land(
                [state(), state(queue_state="queued")], ["--requeue-flake", "--failure-log", str(log), f"17:{HEAD}"],
                item=item, permission=permission, prior=prior))[1]
            flaky = "FAILED tests/test_preview.py::test_preview_pair_timeout - TimeoutError"
            writes, output, _ = run(flaky)
            self.assertEqual(writes, 1, output)
            self.assertEqual([(w["action"], w.get("conditions")) for w in self.recorded],
                             [("requeue", {"flake": "INT-2911"})])
            # A second removal holds: the ledger already records the one requeue.
            writes, output, _ = run(flaky, prior=("requeue",))
            self.assertEqual(writes, 0, output)
            self.assertIn("already requeued this PR once", output)
            # A failure that is not a listed flake is real.
            writes, output, _ = run("FAILED tests/test_store.py::test_rollback - AssertionError")
            self.assertEqual(writes, 0, output)
            self.assertIn("names no test the profile's flakes reference lists", output)

    def test_conflict_is_not_landed(self):
        _, output, code = self.run_land([state(), state(mergeStateStatus="DIRTY")])
        self.assertNotIn("all watched PRs landed", output)
        self.assertIn("CONFLICTING, author action", output)
        self.assertEqual(code, 1)

    def test_changed_head_blocks_initial_and_retry_writes(self):
        for snapshots, expected_writes in [([state(headRefOid="b" * 40)], 0),
                                           ([state(), state(headRefOid="b" * 40)], 1)]:
            with self.subTest(expected_writes=expected_writes):
                writes, output, code = self.run_land(snapshots)
                self.assertEqual(writes, expected_writes, output)
                self.assertTrue("review again" in output or "reconcile before further writes" in output, output)
                self.assertEqual(code, 1)

    def test_watch_and_default_never_write_or_invent_queue_membership(self):
        for args in [["17"], ["--watch", "17"]]:
            with self.subTest(args=args):
                writes, output, code = self.run_land([state()] * 3, args)
                self.assertEqual(writes, 0)
                self.assertIn("queue=not_queued", output)
                self.assertNotIn("still queued", output)
                self.assertNotIn("will land", output)
                self.assertEqual(code, 1)

    def test_actual_membership_and_unknown_both_prevent_enqueue(self):
        for queue in ["queued", "unknown"]:
            with self.subTest(queue=queue):
                writes, output, code = self.run_land([state(queue_state=queue)] * 3)
                self.assertEqual(writes, 0)
                self.assertIn(f"queue={queue}", output)
                self.assertEqual(code, 1)
        # A retry finds the PR already queued: it says so instead of looking stuck.
        _, output, _ = self.run_land([state(queue_state="queued")] * 3)
        self.assertIn("#17 already in the merge queue at the reviewed head; no merge request sent", output)
        _, output, _ = self.run_land([state(queue_state="queued")] * 3, ["--watch", "17"])
        self.assertNotIn("already in the merge queue", output)

    def test_accepted_request_is_not_retried_without_new_authority_and_reconciliation(self):
        writes, output, code = self.run_land([state(), state(), state(state="MERGED")])
        self.assertEqual(writes, 1)
        self.assertIn("all watched PRs landed", output)
        self.assertEqual(code, 0)

    def test_closed_draft_unapproved_and_unreadable_states_do_not_write(self):
        for snapshot in [state(state="CLOSED"), state(isDraft=True),
                         state(reviewDecision="REVIEW_REQUIRED"), {}]:
            with self.subTest(snapshot=snapshot):
                writes, output, code = self.run_land([snapshot])
                self.assertEqual(writes, 0)
                self.assertNotIn("all watched PRs landed", output)
                self.assertEqual(code, 1)

    def test_failed_write_is_held_without_retry(self):
        writes, output, code = self.run_land([state()], failure=True)
        self.assertEqual(writes, 1)
        self.assertIn("inspect before retry", output)
        self.assertEqual(code, 1)

    def test_enqueue_requires_a_full_reviewed_head(self):
        with patch.object(sys, "argv", ["land.py", "--enqueue", "17"]), \
                patch.object(subprocess, "run", side_effect=AssertionError("unexpected forge access")), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            land.main()
        self.assertEqual(error.exception.code, 2)

    def test_auto_merge_first_attempt_and_retry_reject_all_missing_gates(self):
        for mode in ("--enqueue", "--enable-auto-merge"):
            for snapshot, item, permission in [
                (state(), assessment(kind="evidence", owner="Operator"), authority()),
                (state(), assessment(kind="decision", owner="Owner"), authority()),
                (state(), assessment(kind="reviewer-incomplete"), authority()),
                (state(reviewDecision="REVIEW_REQUIRED"), assessment(), authority()),
                (state(headRefOid="c" * 40), assessment(), authority()),
                (state(queue_state="unknown"), assessment(), authority()),
                (state(), assessment(), authority(prs=[99])),
                # Without approvals or a one-PR grant, nothing covers the landing.
                (state(), assessment(), authority(grants=(), approvals=False)),
                (state(updatedAt="new discussion"), assessment(), authority()),
                (state(target={**TARGET, "sha": "f" * 40}), assessment(), authority()),
                (state(target={**TARGET, "sha": None}), assessment(), authority()),
                (state(), assessment(evidence_inputs={"forge": REVISION, "issues": "issue-revision-1", "policy": "outdated-rules"}), authority()),
            ]:
                # Each invocation represents a first attempt or a later fresh retry.
                for attempt in range(2):
                    with self.subTest(mode=mode, snapshot=snapshot, kind=item["decisions"][0]["kind"], attempt=attempt):
                        writes, output, code = self.run_land([snapshot] * 3, [mode, f"17:{HEAD}"], item=item, permission=permission)
                        self.assertEqual(writes, 0, output)
                        self.assertEqual(code, 1)

    def test_auto_merge_turns_on_while_checks_run_and_counts_as_handed_to_github(self):
        auto = {"enabledAt": REVISION}
        for merge_state in ("BLOCKED", "UNSTABLE", "BEHIND"):
            with self.subTest(merge_state=merge_state):
                writes, output, code = self.run_land(
                    [state(mergeStateStatus=merge_state), state(mergeStateStatus=merge_state, autoMergeRequest=auto)],
                    ["--enable-auto-merge", f"17:{HEAD}"])
                self.assertEqual((writes, code), (1, 0), output)
                self.assertIn("AUTO-MERGE ENABLED, not merged", output)
        # A direct merge still waits for CLEAN, and an author's auto-merge needs no second request.
        writes, output, code = self.run_land([state(mergeStateStatus="BLOCKED")] * 3)
        self.assertEqual((writes, code), (0, 1), output)
        writes, output, code = self.run_land([state(autoMergeRequest=auto)], ["--enable-auto-merge", f"17:{HEAD}"])
        self.assertEqual((writes, code), (0, 0), output)
        self.assertIn("already on at the reviewed head, so no request was sent", output)
        self.assertEqual(self.recorded, [])
        # "With approvals" covers auto-merge with no grant; without approvals it is held.
        writes, output, code = self.run_land([state(mergeStateStatus="BLOCKED"), state(autoMergeRequest=auto)],
                                             ["--enable-auto-merge", f"17:{HEAD}"], permission=authority(grants=()))
        self.assertEqual((writes, code), (1, 0), output)
        writes, output, code = self.run_land([state(mergeStateStatus="BLOCKED")], ["--enable-auto-merge", f"17:{HEAD}"],
                                             permission=authority(grants=(), approvals=False))
        self.assertEqual((writes, code), (0, 1), output)
        self.assertIn("auto-merge-sweep policy is ask", output)

    def test_auto_merge_on_a_merge_queue_base_finishes_once_the_pr_is_queued(self):
        # Live: GitHub queued the PR straight away and the helper polled about 40 minutes for a merge.
        writes, output, code = self.run_land([state(mergeStateStatus="BLOCKED"), state(queue_state="queued")],
                                             ["--enable-auto-merge", f"17:{HEAD}"])
        self.assertEqual((writes, code), (1, 0), output)
        self.assertIn("#17 QUEUED, not merged; the merge queue merges it when its checks pass", output)
        self.assertNotIn("timed out", output)
        # Already queued at the reviewed head: no request, and still finished.
        writes, output, code = self.run_land([state(queue_state="queued")], ["--enable-auto-merge", f"17:{HEAD}"])
        self.assertEqual((writes, code), (0, 0), output)
        self.assertIn("#17 QUEUED, not merged; in the merge queue at the reviewed head, so no request was sent", output)

    def test_a_killed_run_has_already_printed_what_it_saw(self):
        # Live: `timeout 150 land.py --enable-auto-merge ...` exited 124 and printed nothing.
        with tempfile.TemporaryDirectory() as tmp:
            gh = Path(tmp) / "gh"  # answers `gh pr view` with an open PR; every other read fails
            gh.write_text("#!/bin/sh\n[ \"$1 $2\" = \"pr view\" ] || exit 1\n"
                          f"echo '{json.dumps(state(mergeStateStatus='BLOCKED'))}'\n")
            gh.chmod(0o755)
            env = {k: v for k, v in os.environ.items() if k != "PYTHONUNBUFFERED"}
            env.update(PATH=f"{tmp}:{env['PATH']}", XDG_STATE_HOME=tmp, PYTHONDONTWRITEBYTECODE="1")
            with self.assertRaises(subprocess.TimeoutExpired) as killed:
                subprocess.run([sys.executable, str(Path(land.__file__)), "--watch", "17"], env=env, cwd=tmp,
                               capture_output=True, timeout=5)
        self.assertIn("#17 pending -- state=OPEN / merge=BLOCKED", (killed.exception.stdout or b"").decode())

    def test_sweep_turns_on_auto_merge_for_a_pr_someone_else_approved_and_holds_without_approval(self):
        auto = {"enabledAt": REVISION}
        sweep = ["--enable-auto-merge", f"17:{HEAD}"]
        # No approval by this round at the head: another reviewer's approval, under the auto-merge-sweep policy.
        writes, output, code = self.run_land([state(mergeStateStatus="BLOCKED"), state(autoMergeRequest=auto)], sweep,
                                             permission=authority(grants=()))
        self.assertEqual((writes, code), (1, 0), output)
        self.assertIn("AUTO-MERGE ENABLED, not merged", output)
        for decision in ("REVIEW_REQUIRED", "CHANGES_REQUESTED", None):
            with self.subTest(decision=decision):
                writes, output, code = self.run_land([state(reviewDecision=decision)] * 3, sweep, permission=authority(grants=()))
                self.assertEqual((writes, code), (0, 1), output)
                self.assertIn("current approval not confirmed", output)
        # The two kinds are separate: sweep never holds another's approval, not the round's own.
        never = authority(grants=(), policies={"auto-merge-sweep": "never"})
        writes, output, code = self.run_land([state(mergeStateStatus="BLOCKED")], sweep, permission=never)
        self.assertEqual((writes, code), (0, 1), output)
        self.assertIn("auto-merge-sweep policy is never", output)
        writes, output, code = self.run_land([state(mergeStateStatus="BLOCKED"), state(autoMergeRequest=auto)], sweep,
                                             permission=never, prior=["approve"])
        self.assertEqual((writes, code), (1, 0), output)

    def test_landing_goes_ahead_on_a_benign_base_move_and_holds_when_it_overlaps(self):
        moved = state(target=MOVED, baseRefOid=MOVED["sha"], mergeable="MERGEABLE")
        writes, output, code = self.run_land([moved, {**moved, "state": "MERGED"}], reads=BENIGN_BASE)
        self.assertEqual((writes, code), (1, 0), output)
        self.assertIn("#17 accepted moved inputs: main moved", output)
        self.assertEqual(self.recorded[0]["accepted"]["target"], MOVED)
        overlap = {**BENIGN_BASE, "compare": {"status": "ahead", "files": [{"filename": "src/app.py"}]}}
        writes, output, code = self.run_land([moved] * 3, reads=overlap)
        self.assertEqual((writes, code), (0, 1), output)
        self.assertIn("base changed files this PR changes: src/app.py", output)

    def test_own_pr_lands_under_auto_only_when_every_condition_holds_and_records_them(self):
        auto = {"enabledAt": REVISION}
        mine = state(reviewDecision="REVIEW_REQUIRED", mergeStateStatus="BLOCKED", author={"login": "reviewer"})
        green = [{"name": "ci", "bucket": "pass"}, {"name": "docs", "bucket": "skipping"}]
        bot_review = [{"id": 5, "user": BOT, "state": "COMMENTED", "submitted_at": REVISION}]
        allowed = authority(grants=(), policies={"own-pr-landing": "auto"})
        for mode in ("--enable-auto-merge", "--enqueue"):
            with self.subTest(mode=mode):
                writes, output, code = self.run_land([mine, {**mine, "autoMergeRequest": auto, "state": "MERGED"}],
                                                     [mode, f"17:{HEAD}"], permission=allowed, checks=green,
                                                     reviews=bot_review)
                self.assertEqual((writes, code), (1, 0), output)
                [write] = self.recorded
                self.assertEqual((write["action"], write["head"]), ("land-own-pr", HEAD))
                self.assertEqual(write["conditions"], {
                    "own": "reviewer authored it", "assessment": f"saved at {HEAD} with nothing unresolved",
                    "checks": "ci pass, docs skipping", "bot_review": "review-bot[bot]", "changes_requested": "none"})
        # The user's last push under a last-push rule makes another author's PR theirs too.
        pushed = {**mine, "author": {"login": "alex"}, "headRepositoryOwner": {"login": "owner"},
                  "headRepository": {"name": "repo"}, "headRefName": "feature"}
        last_push = [{"type": "pull_request", "parameters": {"require_last_push_approval": True}}]
        writes, output, code = self.run_land([pushed, {**pushed, "autoMergeRequest": auto}], ["--enable-auto-merge",
                                             f"17:{HEAD}"], permission=allowed, checks=green, reviews=bot_review,
                                             rules=last_push, pusher="reviewer")
        self.assertEqual((writes, code), (1, 0), output)
        self.assertIn("reviewer pushed the last commit", self.recorded[0]["conditions"]["own"])
        # Each failed condition holds without writing and is named.
        person = {"id": 6, "user": PERSON, "state": "CHANGES_REQUESTED", "submitted_at": REVISION}
        for name, changes, held in [
            ("red check", {"checks": [{"name": "ci", "bucket": "fail"}]}, "required checks not green: ci fail"),
            ("pending check", {"checks": [{"name": "ci", "bucket": "pending"}]}, "required checks not green: ci pending"),
            ("no required checks", {"checks": []}, "required checks unknown or none reported"),
            ("no bot review", {"reviews": [{**bot_review[0], "user": PERSON}]}, "no review bot has reviewed this PR"),
            ("changes requested", {"reviews": [*bot_review, person]}, "changes requested by alex"),
            ("unresolved assessment", {"item": assessment(kind="evidence", owner="Operator")}, "unresolved decisions"),
        ]:
            with self.subTest(failed=name):
                kwargs = {"permission": allowed, "checks": green, "reviews": bot_review, **changes}
                writes, output, code = self.run_land([mine] * 3, ["--enable-auto-merge", f"17:{HEAD}"], **kwargs)
                self.assertEqual((writes, code), (0, 1), output)
                self.assertIn(held, output)
                self.assertEqual(self.recorded, [])
        # Someone else's unapproved PR is not an own PR.
        writes, output, code = self.run_land([{**mine, "author": {"login": "alex"}}] * 3, ["--enable-auto-merge",
                                             f"17:{HEAD}"], permission=allowed, checks=green, reviews=bot_review)
        self.assertEqual((writes, code), (0, 1), output)
        self.assertIn("current approval not confirmed", output)

    def test_own_pr_landing_asks_naming_approvers_and_reports_a_refusal_without_bypassing(self):
        mine = state(reviewDecision="REVIEW_REQUIRED", mergeStateStatus="BLOCKED", author={"login": "reviewer"})
        green = [{"name": "ci", "bucket": "pass"}]
        bot_review = [{"id": 5, "user": BOT, "state": "COMMENTED", "submitted_at": REVISION}]
        writes, output, code = self.run_land([mine] * 3, ["--enable-auto-merge", f"17:{HEAD}"],
                                             permission=authority(grants=()), checks=green, reviews=bot_review,
                                             codeowners="* @carol @reviewer\n")
        self.assertEqual((writes, code), (0, 1), output)
        self.assertIn("own-pr-landing policy is ask", output)
        self.assertIn("@carol  owns src/app.py", output)
        self.assertIn("left out @reviewer: author", output)
        # A yes for this PR lets it through, and a GitHub refusal names the head-bound command for a person.
        writes, output, code = self.run_land([mine] * 3, ["--enable-auto-merge", f"17:{HEAD}"], failure=True,
                                             permission=authority(grants=("land-own-pr",)), checks=green,
                                             reviews=bot_review)
        self.assertEqual((writes, code), (1, 1), output)
        self.assertIn(f"a person with that right can run: gh pr merge 17 --repo owner/repo --match-head-commit {HEAD} "
                      "--auto", output)
        self.assertNotIn("--admin", output)
        self.assertEqual(self.recorded, [])
        writes, output, code = self.run_land([mine] * 3, ["--enable-auto-merge", f"17:{HEAD}"], checks=green,
                                             reviews=bot_review,
                                             permission=authority(grants=(), policies={"own-pr-landing": "never"}))
        self.assertEqual((writes, code), (0, 1), output)
        self.assertIn("own-pr-landing policy is never", output)

    def test_authorized_auto_merge_is_a_landing_write_and_reads_back_uncertainty(self):
        writes, output, code = self.run_land([state(), state(state="MERGED")], ["--enable-auto-merge", f"17:{HEAD}"])
        self.assertEqual((writes, code), (1, 0), output)
        self.assertIn("post-write:", output)
        writes, output, code = self.run_land([state(), state(queue_state="unknown")], failure=True)
        self.assertEqual((writes, code), (1, 1), output)
        self.assertIn("queue=unknown", output)


class QueueReportTests(unittest.TestCase):
    def test_verdict_uses_membership_not_cleanliness(self):
        for snapshot, expected in [
            (state(), "APPROVED"),
            (state(queue_state="queued", mergeStateStatus="BLOCKED"), "APPROVED_QUEUED"),
            (state(queue_state="unknown"), "APPROVED_QUEUE_UNKNOWN"),
            (state(mergeStateStatus="DIRTY"), "APPROVED_CONFLICTING"),
            (state(mergeStateStatus="DIRTY", reviewDecision="REVIEW_REQUIRED"), "CONFLICTING"),
            (state(state="MERGED"), "MERGED"), (state(state="CLOSED"), "CLOSED"),
            # A PR that went back to draft is not waiting on a reviewer.
            (state(isDraft=True, reviewDecision="REVIEW_REQUIRED"), "DRAFT"),
            (state(isDraft=True, state="MERGED"), "MERGED"),
            # Your approval in force at head, and GitHub still wants a review: someone else is next.
            (state(reviewDecision="REVIEW_REQUIRED", my_review={"state": "APPROVED", "at_head": True}),
             "APPROVED_NEEDS_ANOTHER_REVIEWER"),
            (state(reviewDecision="REVIEW_REQUIRED", my_review={"state": "APPROVED", "at_head": False}), "NEEDS_REVIEW"),
            (state(reviewDecision="REVIEW_REQUIRED", my_review={"state": "DISMISSED", "at_head": True}), "NEEDS_REVIEW"),
            (state(reviewDecision="REVIEW_REQUIRED", my_review=None), "NEEDS_REVIEW"),
            (state(reviewDecision="CHANGES_REQUESTED", my_review={"state": "APPROVED", "at_head": True}), "CHANGES_REQUESTED"),
        ]:
            with self.subTest(snapshot=snapshot):
                self.assertEqual(round_report.verdict_of(snapshot), expected)

    def test_queue_api_preserves_unknown_and_head_races(self):
        for payload, expected in [
            ({"data": {"node": {"headRefOid": HEAD, "mergeQueueEntry": None}}}, "not_queued"),
            ({"data": {"node": {"headRefOid": HEAD, "mergeQueueEntry": {"id": "entry"}}}}, "queued"),
            ({"data": {"node": {"headRefOid": "b" * 40, "mergeQueueEntry": None}}}, "unknown"),
            ({"data": {"node": {"headRefOid": HEAD}}}, "unknown"),
            ({"errors": [{"message": "unavailable"}], "data": {"node": None}}, "unknown"),
            ({}, "unknown"),
        ]:
            with self.subTest(payload=payload), patch.object(subprocess, "run", return_value=
                    subprocess.CompletedProcess([], 0, json.dumps(payload), "")):
                self.assertEqual(merge_queue.queue_state("PR_fixture", HEAD), expected)


class ReviewWriteTests(unittest.TestCase):
    def run_write(self, action, *, flags=(), snapshots=None, failure=False, author="author", item=None, permission=None,
                  target=TARGET, after=None, rules=None, pusher=None, reads=None, prior=(), reviews=None,
                  lost_reply=False, dismissed=PERSON, inline=()):
        """`reviews` is the PR's review list on GitHub; pass the same list to two runs to model a retry.
        `lost_reply` posts the review but returns an error, like a timeout after GitHub accepted it.
        `dismissed` is the author GitHub reports for review 9, the one a dismissal targets, and `inline`
        the PR's inline review comments."""
        writes = []
        reviews = [] if reviews is None else reviews
        snapshots = iter(snapshots or [{"head": {"sha": HEAD}, "state": "open",
                                      "base": {"sha": BASE, "ref": "main"}, "updated_at": REVISION,
                                      "draft": False, "auto_merge": None, "user": {"login": author}}] * 2)

        def forge(command, **kwargs):
            if command[0] == "git":
                return subprocess.CompletedProcess(command, 128, "", "fatal: not a git repository")
            if "/git/ref/heads/" in command[2]:
                payload = {"ref": "refs/heads/main", "object": {"type": "commit", "sha": (target or {}).get("sha")}}
                return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
            if command[2].startswith("repos/owner/repo/pulls/17/reviews?"):
                # --paginate --slurp: one array per page.
                return subprocess.CompletedProcess(command, 0, json.dumps([reviews[:1], reviews[1:]]), "")
            if freshness_read(reads or {}, command):
                return freshness_read(reads or {}, command)
            if command[2].startswith("repos/owner/repo/pulls/17/comments?"):
                return subprocess.CompletedProcess(command, 0, json.dumps([list(inline)]), "")
            if command[2] == "repos/owner/repo/pulls/17/reviews/9":
                if dismissed is None:
                    return subprocess.CompletedProcess(command, 1, "", "HTTP 502")
                payload = {"id": 9, "user": dismissed, "state": "CHANGES_REQUESTED", "commit_id": "c" * 40}
                return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
            method = command[command.index("--method") + 1]
            if method != "GET":
                payload = json.loads(kwargs["input"])
                writes.append((command[2], payload))
                if command[2].endswith("/reviews") and (lost_reply or not failure):
                    number = 100 + len(reviews)
                    reviews.append({"id": number, "user": {"login": "reviewer"}, "commit_id": payload["commit_id"],
                                    "state": {"APPROVE": "APPROVED", "REQUEST_CHANGES": "CHANGES_REQUESTED",
                                              "COMMENT": "COMMENTED"}[payload["event"]],
                                    "body": payload["body"], "html_url": f"https://example.test/review/{number}"})
                return subprocess.CompletedProcess(command, int(failure or lost_reply),
                                                   '{"id": 42, "html_url": "https://example.test/posted/42"}',
                                                   "timed out" if lost_reply else "denied" if failure else "")
            payload = {"login": "reviewer"} if command[2] == "user" else next(snapshots)
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

        with tempfile.TemporaryDirectory() as directory:
            body = Path(directory) / "review.md"
            body.write_text("Verified store.py:42 reads the corrected key.")
            assessment_file = Path(directory) / "assessments.json"
            assessment_file.write_text(json.dumps(bundle(item or (assessment(kind="code", owner="Author") if action == "request-changes" else assessment()))))
            authority_file = Path(directory) / "authority.json"
            authority_file.write_text(json.dumps(permission or authority()))
            output = io.StringIO()
            with patch.object(sys, "argv", ["review_write.py", action, "17", "--repo", "owner/repo",
                                           "--head", HEAD, "--body-file", str(body),
                                           "--review-id", "9", "--authority", str(authority_file),
                                           "--assessments", str(assessment_file), *flags]), \
                    patch.object(subprocess, "run", side_effect=forge), patch.object(freshness.time, "sleep"), \
                    patch.dict(os.environ, XDG_STATE_HOME=directory), \
                    patch.object(review_write, "state_of", return_value=after or state()), \
                    patch.object(review_write, "review_rules", return_value=rules), \
                    patch.object(review_write, "last_pusher", return_value=pusher), contextlib.redirect_stdout(output):
                for write in prior:
                    ledger.record_write("owner/repo", **write)
                code = review_write.main()
                self.recorded = ledger.writes("owner/repo")
        return writes, output.getvalue(), code

    def test_assessment_mode_and_changed_heads_never_mutate(self):
        for action in ["approve", "request-changes", "comment", "dismiss"]:
            with self.subTest(action=action):
                writes, output, code = self.run_write(action)
                self.assertEqual(writes, [])
                self.assertIn("no write authorized", output)
                self.assertEqual(code, 0)
                writes, output, code = self.run_write(action, flags=["--write"],
                                                     snapshots=[{"head": {"sha": "b" * 40}}])
                self.assertEqual(writes, [])
                self.assertIn("head changed", output)
                self.assertEqual(code, 1)

    def test_authorized_writes_carry_reviewed_head_and_evidence(self):
        for action in ["approve", "request-changes", "comment", "dismiss"]:
            with self.subTest(action=action):
                writes, _, code = self.run_write(action, flags=["--write"])
                self.assertEqual(code, 0)
                self.assertEqual(len(writes), 1)
                path, payload = writes[0]
                self.assertIn("owner/repo/", path)
                self.assertIn(HEAD, payload.get("body", payload.get("message")))
                self.assertIn("store.py:42", payload.get("body", payload.get("message")))
                if action in ["approve", "request-changes"]:
                    self.assertEqual(payload["commit_id"], HEAD)
                    self.assertEqual(payload["event"], "APPROVE" if action == "approve" else "REQUEST_CHANGES")
                if action == "request-changes":
                    self.assertIn("## Unblock\n- Author:", payload["body"])
                    self.assertIn("one workflow", payload["body"])

    def test_auto_merge_requires_landing_authority_for_clearance(self):
        pr = {"head": {"sha": HEAD}, "state": "open", "draft": False,
              "base": {"sha": BASE, "ref": "main"}, "updated_at": REVISION,
              "auto_merge": {"enabled_by": "author"}, "user": {"login": "author"}}
        # Approving to merge covers auto-merge when the user chose approvals.
        writes, output, code = self.run_write("approve", flags=["--write"], snapshots=[pr, pr])
        self.assertEqual((len(writes), code), (1, 0), output)
        writes, output, code = self.run_write("approve", flags=["--write"], snapshots=[pr],
                                              permission=authority(approvals=False))
        self.assertEqual((writes, code), ([], 1), output)
        self.assertIn("without approvals", output)
        # Dismissing a person's review is the dismiss-human-review kind: ask (the default) holds it and names
        # the question, a one-PR grant lets it through, and never refuses it even with a grant on file.
        writes, output, code = self.run_write("dismiss", flags=["--write"], snapshots=[pr], permission=authority(grants=()))
        self.assertEqual((writes, code), ([], 1), output)
        self.assertIn("dismiss-human-review policy is ask", output)
        self.assertIn("may the round dismiss", output)
        writes, output, code = self.run_write("dismiss", flags=["--write"], snapshots=[pr, pr])
        self.assertEqual((len(writes), code), (1, 0), output)
        writes, output, code = self.run_write("dismiss", flags=["--write"], snapshots=[pr],
                                              permission={**authority(), "policies": {**authority()["policies"],
                                                                                      "dismiss-human-review": "never"}})
        self.assertEqual((writes, code), ([], 1), output)

    def test_a_bot_review_is_dismissed_only_when_every_inline_finding_is_verified_at_the_head(self):
        bots_only = authority(grants=(), policies={"dismiss-bot-review": "auto"})
        # The bot's two findings, a reply in one of its threads, and a finding from another review.
        inline = [*INLINE, {**INLINE[0], "id": 303, "in_reply_to_id": 301},
                  {**INLINE[1], "id": 304, "pull_request_review_id": 8}]
        writes, output, code = self.run_write("dismiss", flags=["--write"], permission=bots_only, dismissed=BOT,
                                              inline=inline, item=assessment(verified_findings=VERIFIED))
        self.assertEqual((len(writes), code), (1, 0), output)
        message = writes[0][1]["message"]
        self.assertIn(f"## Findings verified at `{HEAD}`", message)
        self.assertIn("- `src/app.py:12` (comment 301): fixed, checked at `src/app.py:14`. Guard added", message)
        self.assertIn("- `src/db.py:40` (comment 302): overstated, checked at `src/db.py:40`. Caller", message)
        self.assertNotIn("comment 303", message)
        self.assertNotIn("comment 304", message)
        # One finding without a record holds the dismissal and names it.
        writes, output, code = self.run_write("dismiss", flags=["--write"], permission=bots_only, dismissed=BOT,
                                              inline=inline, item=assessment(verified_findings=VERIFIED[:1]))
        self.assertEqual((writes, code), ([], 1), output)
        self.assertIn("no fixed or overstated record for src/db.py:40 (comment 302)", output)
        self.assertNotIn("comment 301", output)
        # A record that is not fixed or overstated is not a verification.
        writes, output, code = self.run_write("dismiss", flags=["--write"], permission=bots_only, dismissed=BOT,
                                              inline=inline, item=assessment(verified_findings=[
                                                  VERIFIED[0], {**VERIFIED[1], "status": "open"}]))
        self.assertEqual((writes, code), ([], 1), output)
        # A bot review with no inline findings leaves nothing to verify: auto holds, a one-PR grant may dismiss it.
        writes, output, code = self.run_write("dismiss", flags=["--write"], permission=bots_only, dismissed=BOT)
        self.assertEqual((writes, code), ([], 1), output)
        self.assertIn("no inline findings", output)
        writes, output, code = self.run_write("dismiss", flags=["--write"], dismissed=BOT,
                                              permission=authority(grants=("dismiss-bot",)))
        self.assertEqual((len(writes), code), (1, 0), output)
        # A person's review keeps its own policy and free-text evidence.
        writes, output, code = self.run_write("dismiss", flags=["--write"], dismissed=PERSON, inline=inline)
        self.assertEqual((len(writes), code), (1, 0), output)
        self.assertNotIn("Findings verified", writes[0][1]["message"])

    def test_whose_review_a_dismissal_targets_comes_from_github_and_picks_the_policy(self):
        bots_only = authority(grants=(), policies={"dismiss-bot-review": "auto", "dismiss-human-review": "ask"})
        verified = assessment(verified_findings=[VERIFIED[0]])
        for user in (BOT, {"login": "review-bot[bot]", "type": "User"}, {"login": "linter", "type": "Bot"}):
            with self.subTest(user=user):
                writes, output, code = self.run_write("dismiss", flags=["--write"], permission=bots_only, dismissed=user,
                                                      inline=INLINE[:1], item=verified)
                self.assertEqual((len(writes), code), (1, 0), output)
                self.assertTrue(writes[0][0].endswith("/reviews/9/dismissals"))
        writes, output, code = self.run_write("dismiss", flags=["--write"], permission=bots_only, dismissed=PERSON)
        self.assertEqual((writes, code), ([], 1), output)
        self.assertIn("dismiss-human-review policy is ask", output)
        # A caller's claim that the review is a bot's changes nothing: a dismiss-bot grant does not cover a
        # person's review, and the helper has no action or flag that names the author type.
        claimed = authority(grants=("dismiss-bot",))
        writes, output, code = self.run_write("dismiss", flags=["--write"], permission=claimed, dismissed=PERSON)
        self.assertEqual((writes, code), ([], 1), output)
        self.assertIn("dismiss-human-review policy is ask", output)
        for argv in (["dismiss-bot"], ["dismiss", "--bot"]):
            with self.subTest(argv=argv), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()), \
                    patch.object(sys, "argv", ["review_write.py", *argv[:1], "17", *argv[1:], "--repo", "owner/repo",
                                               "--head", HEAD, "--body-file", "x", "--review-id", "9", "--write"]), \
                    patch.object(subprocess, "run", side_effect=AssertionError("unexpected forge access")):
                review_write.main()
        # An unreadable author holds the dismissal rather than guessing.
        writes, output, code = self.run_write("dismiss", flags=["--write"], permission=bots_only, dismissed=None)
        self.assertEqual(writes, [], output)
        self.assertIn("could not read review 9 to tell a bot from a person", output)

    def test_self_approval_and_uncertain_writes_are_held(self):
        writes, output, code = self.run_write("approve", flags=["--write"], author="reviewer")
        self.assertEqual(writes, [])
        self.assertIn("cannot approve", output)
        self.assertEqual(code, 1)
        writes, output, code = self.run_write("comment", flags=["--write"], failure=True)
        self.assertEqual(len(writes), 1)
        self.assertIn("inspect remote state", output)
        self.assertEqual(code, 1)

    def test_only_accepted_writes_are_recorded_for_the_report(self):
        for action in ("approve", "request-changes", "comment", "dismiss"):
            with self.subTest(action=action):
                self.run_write(action, flags=["--write"])
                self.assertEqual([{k: w[k] for k in ("number", "action", "head", "url")} for w in self.recorded],
                                 [{"number": 17, "action": action, "head": HEAD, "url": "https://example.test/posted/42"}])
                self.assertRegex(self.recorded[0]["at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        # Held, unauthorized and refused actions posted nothing, so they record nothing.
        self.run_write("approve")
        self.assertEqual(self.recorded, [])
        self.run_write("approve", flags=["--write"], author="reviewer")
        self.assertEqual(self.recorded, [])
        self.run_write("comment", flags=["--write"], failure=True)
        self.assertEqual(self.recorded, [])
        # An approval that posts and leaves the gate closed still exists on GitHub.
        self.run_write("approve", flags=["--write"], after=state(reviewDecision="REVIEW_REQUIRED"))
        self.assertEqual(len(self.recorded), 1)

    def test_approval_that_cannot_clear_the_review_gate_is_held_or_reported(self):
        rules = {"require_last_push_approval": True, "require_code_owner_review": True}
        # The reviewer pushed the last commit: their approval cannot satisfy the last-push rule.
        writes, output, code = self.run_write("approve", flags=["--write"], rules=rules, pusher="reviewer")
        self.assertEqual((writes, code), ([], 1), output)
        self.assertIn("you pushed the last commit", output)
        for options in ({"rules": rules, "pusher": "author"}, {"rules": rules, "pusher": None},
                        {"rules": {"require_code_owner_review": True}, "pusher": "reviewer"},
                        {"rules": None, "pusher": "reviewer"}):
            with self.subTest(options=options):
                writes, output, code = self.run_write("approve", flags=["--write"], **options)
                self.assertEqual((len(writes), code), (1, 0), output)
                self.assertNotIn("REVIEW GATE", output)
        # Posted, and GitHub still requires a review: say so instead of exiting clean.
        writes, output, code = self.run_write("approve", flags=["--write"], rules=rules, pusher="author",
                                             after=state(reviewDecision="REVIEW_REQUIRED"))
        self.assertEqual((len(writes), code), (1, 1), output)
        for text in ("APPROVAL POSTED BUT THE REVIEW GATE DID NOT CLEAR", "GitHub reports REVIEW_REQUIRED",
                     "a code owner must approve", "do not post it again"):
            self.assertIn(text, output)
        writes, output, code = self.run_write("approve", flags=["--write"], after=state(reviewDecision="REVIEW_REQUIRED"))
        self.assertEqual((len(writes), code), (1, 1), output)
        self.assertIn("review rules unreadable", output)
        # Only an approval is expected to clear the gate.
        for action in ("comment", "request-changes"):
            writes, output, code = self.run_write(action, flags=["--write"], rules=rules, pusher="reviewer",
                                                 after=state(reviewDecision="CHANGES_REQUESTED"))
            self.assertEqual((len(writes), code), (1, 0), output)
            self.assertNotIn("REVIEW GATE", output)

    def test_a_base_move_that_cannot_change_the_verdict_lets_every_write_through_and_says_why(self):
        moved = pull(base={"sha": MOVED["sha"], "ref": "main"})
        for action in ("approve", "dismiss", "comment", "request-changes"):
            with self.subTest(action=action):
                writes, output, code = self.run_write(action, flags=["--write"], snapshots=[moved, moved],
                                                     target=MOVED, reads=BENIGN_BASE)
                self.assertEqual((len(writes), code), (1, 0), output)
                self.assertIn("Accepted moved inputs: main moved", output)
                accepted = self.recorded[0]["accepted"]
                self.assertEqual((accepted["target"], accepted["base"]), (MOVED, MOVED["sha"]))
                self.assertIn("none changed by this PR", accepted["reasons"][0])

    def test_a_base_move_holds_on_overlap_conflict_or_anything_unreadable(self):
        moved = pull(base={"sha": MOVED["sha"], "ref": "main"})
        many = [{"filename": f"docs/{n}.md"} for n in range(300)]
        for case, snapshot, target, reads, reason in [
            ("overlap", moved, MOVED, {**BENIGN_BASE, "compare": {"status": "ahead", "files": [{"filename": "src/app.py"}]}},
             "base changed files this PR changes: src/app.py"),
            ("renamed overlap", moved, MOVED, {**BENIGN_BASE, "compare": {"status": "ahead", "files": [
                {"filename": "src/main.py", "previous_filename": "src/app.py"}]}}, "base changed files this PR changes"),
            ("mergeability unknown", {**moved, "mergeable": None}, MOVED, BENIGN_BASE, "has not reported the PR mergeable"),
            ("unreadable target", pull(), {**TARGET, "sha": None}, BENIGN_BASE, "actual target ref unavailable"),
            ("unreadable base change", moved, MOVED, {"files": BENIGN_BASE["files"]}, "unreadable, truncated or rewritten"),
            ("truncated base change", moved, MOVED, {**BENIGN_BASE, "compare": {"status": "ahead", "files": many}},
             "unreadable, truncated or rewritten"),
            ("rewritten base", moved, MOVED, {**BENIGN_BASE, "compare": {"status": "diverged", "files": []}},
             "unreadable, truncated or rewritten"),
            ("unreadable PR files", moved, MOVED, {"compare": BENIGN_BASE["compare"]}, "files are unreadable"),
        ]:
            for action in ("approve", "comment"):
                with self.subTest(case=case, action=action):
                    writes, output, code = self.run_write(action, flags=["--write"], snapshots=[snapshot, snapshot],
                                                         target=target, reads=reads)
                    self.assertEqual((writes, code), ([], 1), output)
                    self.assertIn(reason, output)
                    self.assertEqual(self.recorded, [])

    def test_a_conflicting_pr_gets_its_review_and_a_dismissal_still_holds(self):
        # Live #3735: the code was cleared, the branch conflicted, and the approval was held.
        conflicting = pull(base={"sha": MOVED["sha"], "ref": "main"}, mergeable=False, mergeable_state="dirty")
        for action in ("approve", "comment", "request-changes"):
            with self.subTest(action=action):
                writes, output, code = self.run_write(action, flags=["--write"], snapshots=[conflicting, conflicting],
                                                     target=MOVED, reads=BENIGN_BASE)
                self.assertEqual(len(writes), 1, output)
                self.assertIn(f"Accepted moved inputs: main moved ({BASE[:9]}..{MOVED['sha'][:9]}", output)
                self.assertIn("GitHub reports the PR conflicting with it", output)
        writes, output, code = self.run_write("dismiss", flags=["--write"], snapshots=[conflicting, conflicting],
                                             target=MOVED, reads=BENIGN_BASE)
        self.assertEqual((writes, code), ([], 1), output)
        self.assertIn("conflicting", output)

    def test_discussion_from_bots_automation_and_this_round_is_benign_and_people_are_not(self):
        talked = pull(updated_at=LATER)
        before = {"event": "commented", "created_at": "2026-11-11T19:00:00Z", "actor": PERSON}
        ours = {"number": 17, "action": "comment", "head": HEAD, "url": "https://example.test/posted/7"}
        for case, events, prior, reason in [
            ("bot comment", [before, {"event": "commented", "created_at": "2026-11-11T20:30:00Z", "actor": BOT, "user": BOT},
                             {"event": "labeled", "created_at": "2026-11-11T20:31:00Z", "actor": PERSON}], (), None),
            ("bot comment review", [{"event": "reviewed", "submitted_at": "2026-11-11T20:30:00Z", "state": "commented",
                                     "user": BOT}], (), None),
            ("this round's comment", [{"event": "commented", "created_at": "2026-11-11T20:30:00Z",
                                       "actor": {"login": "reviewer", "type": "User"}, "html_url": ours["url"]}], (ours,), None),
            ("person comment", [{"event": "commented", "created_at": "2026-11-11T20:30:00Z", "actor": PERSON, "user": PERSON}],
             (), "commented by alex"),
            ("person review", [{"event": "reviewed", "submitted_at": "2026-11-11T20:30:00Z", "state": "commented",
                                "user": PERSON}], (), "reviewed by alex (COMMENTED)"),
            ("bot changes request", [{"event": "reviewed", "submitted_at": "2026-11-11T20:30:00Z",
                                      "state": "changes_requested", "user": BOT}], (), "(CHANGES_REQUESTED)"),
            ("GitHub dismissing this round's approval on a push",
             [{"event": "review_dismissed", "created_at": "2026-11-11T20:30:00Z", "actor": PERSON,
               "dismissed_review": {"state": "approved", "review_id": 51, "dismissal_message": None,
                                    "dismissal_commit_id": "c" * 40}}],
             ({**ours, "action": "approve", "url": "https://example.test/pull/17#pullrequestreview-51"},), None),
            ("a person dismissing this round's approval",
             [{"event": "review_dismissed", "created_at": "2026-11-11T20:30:00Z", "actor": PERSON,
               "dismissed_review": {"state": "approved", "review_id": 51, "dismissal_message": "not yet",
                                    "dismissal_commit_id": None}}],
             ({**ours, "action": "approve", "url": "https://example.test/pull/17#pullrequestreview-51"},),
             "review_dismissed by alex"),
            ("a push dismissing someone else's approval",
             [{"event": "review_dismissed", "created_at": "2026-11-11T20:30:00Z", "actor": PERSON,
               "dismissed_review": {"state": "approved", "review_id": 52, "dismissal_message": None,
                                    "dismissal_commit_id": "c" * 40}}],
             ({**ours, "action": "approve", "url": "https://example.test/pull/17#pullrequestreview-51"},),
             "review_dismissed by alex"),
            ("unreadable timeline", None, (), "timeline is unreadable"),
        ]:
            for action in ("approve", "comment"):
                with self.subTest(case=case, action=action):
                    writes, output, code = self.run_write(action, flags=["--write"], snapshots=[talked, talked], prior=prior,
                                                         reads={} if events is None else {"timeline": events})
                    if reason:
                        self.assertEqual((writes, code), ([], 1), output)
                        self.assertIn(reason, output)
                    else:
                        self.assertEqual((len(writes), code), (1, 0), output)
                        self.assertIn("Accepted moved inputs: discussion moved only by", output)

    def test_a_new_head_is_stale_before_any_read_even_when_everything_else_is_benign(self):
        live = {"head": "c" * 40, "base": BASE, "forge": REVISION, "target": TARGET, "conflicting": False}
        with patch.object(subprocess, "run", side_effect=AssertionError("unexpected forge access")):
            verdict = freshness.classify(assessment(), live, policy=assessment()["evidence_inputs"]["policy"],
                                         repo="owner/repo", number=17, writes=[])
        self.assertEqual(verdict, freshness.Stale(("head changed",)))

    def test_head_movement_during_dismissal_is_not_reported_as_clearance(self):
        pr = {"head": {"sha": HEAD}, "base": {"sha": BASE, "ref": "main"}, "updated_at": REVISION,
              "state": "open", "draft": False, "auto_merge": None}
        writes, output, code = self.run_write("dismiss", flags=["--write"],
                                             snapshots=[pr, {"head": {"sha": "b" * 40}}])
        self.assertEqual(len(writes), 1)
        self.assertIn("HEAD MOVED during write", output)
        self.assertEqual(code, 1)

    def test_clearance_and_changes_requested_respect_owned_decisions(self):
        for action in ("approve", "dismiss"):
            for kind in ("code", "evidence", "decision", "reviewer-incomplete"):
                with self.subTest(action=action, kind=kind):
                    writes, output, code = self.run_write(action, flags=["--write"], item=assessment(kind=kind))
                    self.assertEqual((writes, code), ([], 1), output)
        for kind in ("evidence", "reviewer-incomplete"):
            writes, output, code = self.run_write("request-changes", flags=["--write"], item=assessment(kind=kind))
            self.assertEqual((writes, code), ([], 1), output)
        writes, output, code = self.run_write("comment", flags=["--write"], permission=authority(prs=[99]))
        self.assertEqual((writes, code), ([], 1), output)

    def test_an_owner_answer_unblocks_the_normal_approval_and_a_stale_verdict_still_holds_it(self):
        gated = assessment(kind="decision", owner="Product owner")
        gated["decisions"][0]["subject"] = "adr:183"
        writes, output, code = self.run_write("approve", flags=["--write"], item=gated)
        self.assertEqual((writes, code), ([], 1), output)
        self.assertIn("unresolved decisions", output)
        with tempfile.TemporaryDirectory() as state, patch.dict(os.environ, XDG_STATE_HOME=state):
            ledger.record_assessment("round-1", gated, "owner/repo")
            answered = {"repository": "owner/repo", "assessments": [gated]}
            ledger.decide("adr:183", "accept", "Accept ADR 183; approve what that unblocks", repo="owner/repo",
                          bundle=answered)
        unblocked = answered["assessments"][0]
        writes, output, code = self.run_write("approve", flags=["--write"], item=unblocked)
        self.assertEqual((len(writes), code), (1, 0), output)
        self.assertEqual(writes[0][1]["event"], "APPROVE")
        # A person commented after the assessment: the answer does not make a stale review current.
        talked = pull(updated_at=LATER)
        person = [{"event": "commented", "created_at": "2026-11-11T20:30:00Z", "actor": PERSON, "user": PERSON}]
        writes, output, code = self.run_write("approve", flags=["--write"], item=unblocked, snapshots=[talked, talked],
                                              reads={"timeline": person})
        self.assertEqual((writes, code), ([], 1), output)
        self.assertIn("commented by alex", output)
        # Nor a moved head.
        writes, output, code = self.run_write("approve", flags=["--write"], item=unblocked,
                                              snapshots=[pull(head={"sha": "c" * 40})])
        self.assertEqual((writes, code), ([], 1), output)

    def test_a_carried_assessment_reapproves_under_its_own_policy_and_a_fresh_approval_does_not_need_it(self):
        approved = "c" * 40
        carried = assessment(carried={"from_head": approved, "head": HEAD, "check": "git merge-tree --write-tree",
                                      "commits": [HEAD], "at": REVISION},
                             provenance=f"Carried from {approved} to {HEAD}")
        prior = ({"number": 17, "action": "approve", "head": approved, "url": "https://example.test/review/1"},)
        writes, output, code = self.run_write("reapprove", flags=["--write"], item=carried, prior=prior)
        self.assertEqual((len(writes), code), (1, 0), output)
        self.assertEqual((writes[0][1]["event"], writes[0][1]["commit_id"]), ("APPROVE", HEAD))
        self.assertEqual([w["action"] for w in self.recorded], ["approve", "reapprove"])
        never = authority(grants=(), policies={"reapprove-base-only": "never"})
        writes, output, code = self.run_write("reapprove", flags=["--write"], item=carried, prior=prior, permission=never)
        self.assertEqual((writes, code), ([], 1), output)
        self.assertIn("reapprove-base-only policy is never", output)
        writes, output, code = self.run_write("approve", flags=["--write"], permission=never)
        self.assertEqual((len(writes), code), (1, 0), output)
        # Each action needs its own kind of assessment, and a re-approval needs the round's own earlier approval.
        # Carried from an assessment the round never approved: an ordinary approval of the carried review.
        writes, output, code = self.run_write("approve", flags=["--write"], item=carried)
        self.assertEqual((len(writes), code), (1, 0), output)
        for action, item, held, message in (("approve", carried, prior, "carried from the round's approval"),
                                            ("reapprove", assessment(), prior, "reapprove needs an assessment"),
                                            ("reapprove", carried, (), "the ledger records none"),
                                            ("reapprove", carried, ({**prior[0], "head": "e" * 40},), "at eeeeeeeee")):
            with self.subTest(action=action, message=message):
                writes, output, code = self.run_write(action, flags=["--write"], item=item, prior=held)
                self.assertEqual((writes, code), ([], 1), output)
                self.assertIn(message, output)

    def test_a_retry_at_the_same_head_does_not_post_the_verdict_twice(self):
        for action in ("approve", "request-changes"):
            with self.subTest(action=action):
                reviews = []
                first, _, code = self.run_write(action, flags=["--write"], reviews=reviews)
                self.assertEqual((len(first), code), (1, 0))
                again, output, code = self.run_write(action, flags=["--write"], reviews=reviews)
                self.assertEqual((again, code), ([], 0), output)
                self.assertIn("already exists", output)
                self.assertIn(reviews[0]["html_url"], output)
                self.assertEqual(self.recorded, [])
        # A comment after the approval, such as a note about a conflict, does not replace the verdict.
        approved = {"id": 1, "user": {"login": "reviewer"}, "commit_id": HEAD, "state": "APPROVED", "body": "ok"}
        writes, output, code = self.run_write("approve", flags=["--write"],
                                              reviews=[approved, {**approved, "id": 2, "state": "COMMENTED"}])
        self.assertEqual((writes, code), ([], 0), output)

    def test_a_verdict_at_an_older_head_or_since_replaced_is_posted_again(self):
        old = {"id": 1, "user": {"login": "reviewer"}, "commit_id": "b" * 40, "state": "APPROVED", "body": "ok"}
        someone = {**old, "user": {"login": "someone"}, "commit_id": HEAD}
        dismissed = {**old, "id": 2, "commit_id": HEAD, "state": "DISMISSED"}
        for existing in ([old], [someone], [{**old, "commit_id": HEAD}, dismissed],
                         [{**old, "commit_id": HEAD, "state": "CHANGES_REQUESTED"}]):
            with self.subTest(existing=existing):
                writes, output, code = self.run_write("approve", flags=["--write"], reviews=list(existing))
                self.assertEqual((len(writes), code), (1, 0), output)

    def test_a_comment_is_a_head_bound_review_and_is_not_posted_twice(self):
        reviews = []
        writes, output, code = self.run_write("comment", flags=["--write"], reviews=reviews)
        self.assertEqual(code, 0, output)
        [(path, payload)] = writes
        self.assertEqual(path, "repos/owner/repo/pulls/17/reviews")
        self.assertEqual((payload["event"], payload["commit_id"]), ("COMMENT", HEAD))
        self.assertIn("store.py:42", payload["body"])
        again, output, code = self.run_write("comment", flags=["--write"], reviews=reviews)
        self.assertEqual((again, code), ([], 0), output)
        self.assertIn("already exists", output)
        # A different comment, or the same one at an older head, is new.
        for existing in ({**reviews[0], "body": "Reviewed head: something else"}, {**reviews[0], "commit_id": "b" * 40}):
            with self.subTest(existing=existing):
                writes, output, code = self.run_write("comment", flags=["--write"], reviews=[existing])
                self.assertEqual((len(writes), code), (1, 0), output)

    def test_an_errored_write_that_posted_is_read_back_as_posted_and_not_retried(self):
        for action in ("approve", "request-changes", "comment"):
            with self.subTest(action=action):
                reviews = []
                writes, output, code = self.run_write(action, flags=["--write"], reviews=reviews, lost_reply=True)
                self.assertEqual((len(writes), code), (1, 0), output)
                self.assertIn(f"Submitted {action}: {reviews[0]['html_url']}", output)
                self.assertNotIn("uncertain", output)
                self.assertEqual([w["url"] for w in self.recorded], [reviews[0]["html_url"]])
                again, output, code = self.run_write(action, flags=["--write"], reviews=reviews)
                self.assertEqual((again, code), ([], 0), output)
        # Nothing at the head after the error: still reported as a failed write, once.
        writes, output, code = self.run_write("approve", flags=["--write"], failure=True)
        self.assertEqual((len(writes), code), (1, 1), output)
        self.assertIn("inspect remote state", output)

    def test_existing_review_lookup_runs_after_every_check(self):
        approved = [{"id": 1, "user": {"login": "reviewer"}, "commit_id": HEAD, "state": "APPROVED", "body": "ok"}]
        writes, output, code = self.run_write("approve", flags=["--write"], reviews=approved, permission=authority(prs=[99]))
        self.assertEqual((writes, code), ([], 1), output)
        self.assertNotIn("already exists", output)

    def test_changed_review_policy_blocks_every_posted_action(self):
        item = assessment(kind="code")
        item["evidence_inputs"]["policy"] = "outdated-rules"
        for action in ("approve", "dismiss", "request-changes", "comment"):
            with self.subTest(action=action):
                writes, output, code = self.run_write(action, flags=["--write"], item=item)
                self.assertEqual((writes, code), ([], 1), output)
                self.assertIn("review policy changed", output)


class BranchRuleTests(unittest.TestCase):
    def reply(self, payload, code=0):
        text = payload if isinstance(payload, str) else json.dumps(payload)
        return patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], code, text, ""))

    def test_rules_merge_across_rulesets_and_an_unreadable_answer_is_not_an_empty_one(self):
        payload = [
            # The stricter ruleset comes first: a later, looser one must not relax it.
            {"type": "pull_request", "parameters": {"required_approving_review_count": 2,
                                                    "require_code_owner_review": True, "require_last_push_approval": True}},
            {"type": "pull_request", "parameters": {"required_approving_review_count": 1, "require_code_owner_review": False}},
            {"type": "deletion"}]
        with self.reply(payload) as run:
            rules = branch_rules.review_rules("owner/repo", "release/1.0")
        self.assertEqual(run.call_args[0][0], ["gh", "api", "repos/owner/repo/rules/branches/release%2F1.0?per_page=100"])
        self.assertEqual(rules, {"required_approving_review_count": 2, "require_code_owner_review": True,
                                 "require_last_push_approval": True})
        self.assertEqual(branch_rules.describe(rules), [
            "2 approval(s) required", "a code owner must approve",
            "the last push must be approved by someone other than its pusher"])
        for payload, code in (("denied", 1), ("not json", 0), ({"message": "Not Found"}, 0), ([{"type": "pull_request"}] * 100, 0)):
            with self.subTest(payload=str(payload)[:20]), self.reply(payload, code):
                self.assertIsNone(branch_rules.review_rules("owner/repo", "main"))
        self.assertEqual(branch_rules.describe(None), ["review rules unreadable"])
        self.assertIn("classic branch protection is not readable", branch_rules.describe({})[0])

    def test_a_gated_approval_is_explained_by_the_rules_and_the_reviewers_own_last_push(self):
        rules = {"required_approving_review_count": 1, "require_code_owner_review": True, "require_last_push_approval": True}
        pushed = {"feature/a": "reviewer", "feature/b": "author", "feature/c": "reviewer"}
        branches = {19: "feature/c", 17: "feature/a", 18: "feature/b"}
        with patch.object(branch_rules, "review_rules", return_value=rules) as read, \
                patch.object(branch_rules, "last_pusher", side_effect=lambda repo, branch: pushed.get(branch)) as pusher:
            lines = branch_rules.gate_lines("owner/repo", "main", "reviewer", branches)
            self.assertEqual(lines, [
                "review rules on main: 1 approval(s) required; a code owner must approve; "
                "the last push must be approved by someone other than its pusher",
                "reviewer pushed the last commit on #17, #19: the last-push rule needs an approval from someone else there"])
            read.assert_called_once_with("owner/repo", "main")
            self.assertEqual(pusher.call_args_list[0][0], ("owner/repo", "feature/a"))
            # Nobody's last push was the reviewer's: the rules are still named, and nothing is claimed about a push.
            self.assertEqual(len(branch_rules.gate_lines("owner/repo", "main", "someone-else", branches)), 1)
        # Without a last-push rule the pusher is not read; unreadable rules say so and are not "no rule".
        for unread, text in (({"require_code_owner_review": True}, "review rules on main: a code owner must approve"),
                             (None, "review rules on main: review rules unreadable")):
            with patch.object(branch_rules, "review_rules", return_value=unread), \
                    patch.object(branch_rules, "last_pusher") as pusher:
                self.assertEqual(branch_rules.gate_lines("owner/repo", "main", "reviewer", branches), [text])
                pusher.assert_not_called()

    def test_last_pusher_is_the_latest_branch_activity_or_unknown(self):
        with self.reply([{"actor": {"login": "reviewer"}}]) as run:
            self.assertEqual(branch_rules.last_pusher("fork/repo", "feature/x"), "reviewer")
        self.assertIn("repos/fork/repo/activity?ref=refs/heads/feature/x", run.call_args[0][0][2])
        for payload, code in (([], 0), ("denied", 1), ([{"actor": None}], 0)):
            with self.reply(payload, code):
                self.assertIsNone(branch_rules.last_pusher("fork/repo", "feature/x"))
        self.assertIsNone(branch_rules.last_pusher(None, "feature/x"))


class RenderingTests(unittest.TestCase):
    def test_link_cannot_add_attributes(self):
        source = render('[proof](https://example.test/"data-audit="injected)')
        anchors = [attrs for tag, attrs in Elements(source).tags if tag == "a"]
        self.assertEqual(len(anchors), 1, source)
        self.assertEqual(set(anchors[0]), {"href"}, source)
        self.assertEqual(anchors[0]["href"], 'https://example.test/"data-audit="injected')

    def test_formatted_labels_do_not_format_or_double_escape_urls(self):
        url = 'https://example.test/_path_/**glob**?a=1&b="two"'
        source = render(f'[**proof** `store.py:42`]({url})')
        anchors = [attrs for tag, attrs in Elements(source).tags if tag == "a"]
        self.assertEqual(anchors, [{"href": url}])
        self.assertIn("<strong>proof</strong> <code>store.py:42</code>", source)

    def test_raw_markup_code_entities_and_unsafe_schemes_stay_inert(self):
        source = render('`<img src=x>` <script>alert</script> [bad](javascript:alert)\n\n'
                        '[quoted](https://example.test/`"data-audit="injected`)\n\n'
                        'https://example.test/a?x=1&y=2\n\n'
                        '[entity](https://example.test/&quot;data-audit=&quot;injected)')
        for tag, attrs in Elements(source).tags:
            self.assertNotIn(tag, ["script", "img"])
            if tag == "a":
                self.assertEqual(set(attrs), {"href"})
                self.assertTrue(attrs["href"].startswith("https://"))
        self.assertIn('href="https://example.test/a?x=1&amp;y=2"', source)



class WorkLevelTests(unittest.TestCase):
    """The level the user picked caps every write, and branch writes stay bound to the reviewed head."""

    def test_levels_cap_actions_and_approval_is_its_own_choice(self):
        cases = [("assess", True, "comment", False), ("assess", True, "approve", False),
                 ("review", False, "approve", False), ("review", True, "approve", True),
                 ("review", True, "push-fix", False), ("moderate", False, "update-branch", True),
                 ("moderate", True, "delegate", False), ("major", False, "delegate", True),
                 ("assess", False, "enqueue", True), (None, True, "comment", False)]
        for level, approvals, action, allowed in cases:
            with self.subTest(level=level, approvals=approvals, action=action):
                try:  # authority.py refuses a level that cannot hold the answer, so no file exists to write with
                    permission = authority(grants=(), level=level, approvals=approvals)
                    if action == "enqueue":
                        permission = authority_script.grant(permission, 17, action, "merge #17")
                except ValueError:
                    self.assertFalse(allowed)
                    continue
                if allowed:
                    ledger.check_authority(permission, "owner/repo", 17, action)
                else:
                    with self.assertRaises(ValueError):
                        ledger.check_authority(permission, "owner/repo", 17, action)

    def run_branch(self, action, *, lines=3, level="moderate", github_head=None, fork=False, race=False):
        with tempfile.TemporaryDirectory() as tmp:
            remote = Path(tmp) / "owner" / "repo.git"
            work = Path(tmp) / "work"
            sh = lambda *a, cwd=work: subprocess.run(a, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()
            remote.mkdir(parents=True)
            sh("git", "init", "-q", "--bare", cwd=remote)
            sh("git", "init", "-q", "-b", "fix", str(work), cwd=tmp)
            for key, value in (("user.email", "r@example.test"), ("user.name", "Reviewer")):
                sh("git", "config", key, value)
            (work / "a.py").write_text("x = 1\n")
            sh("git", "add", "."); sh("git", "commit", "-qm", "base")
            sh("git", "remote", "add", "origin", str(remote)); sh("git", "push", "-q", "origin", "fix")
            reviewed = sh("git", "rev-parse", "HEAD")
            if race:  # someone else pushes after GitHub was read
                sh("git", "commit", "-q", "--allow-empty", "-m", "theirs"); sh("git", "push", "-q", "origin", "fix")
                sh("git", "reset", "-q", "--hard", reviewed)
            (work / "a.py").write_text("".join(f"y{i} = {i}\n" for i in range(lines)))
            sh("git", "commit", "-qam", "fix")
            local = sh("git", "rev-parse", "HEAD")
            heads = iter([github_head or reviewed, local])
            calls = []

            def api(path, method="GET", payload=None):
                calls.append((path, method, payload))
                if method != "GET":
                    return {"message": "Updating pull request branch."}
                return {"state": "open", "head": {"sha": next(heads), "ref": "fix",
                                                  "repo": {"full_name": "someone/repo" if fork else "owner/repo"}}}

            permission = Path(tmp) / "authority.json"
            permission.write_text(json.dumps(authority(grants=(), level=level)))
            output = io.StringIO()
            previous = os.getcwd()
            os.chdir(work)
            try:
                with patch.object(sys, "argv", ["branch_write.py", action, "17", "--repo", "owner/repo", "--head", reviewed,
                                                "--authority", str(permission), "--write"]), \
                        patch.object(branch_write, "api", side_effect=api), \
                        patch.dict(os.environ, XDG_STATE_HOME=tmp), contextlib.redirect_stdout(output):
                    code = branch_write.main()
                    written = ledger.writes("owner/repo")
            finally:
                os.chdir(previous)
            pushed = sh("git", "rev-parse", "fix", cwd=remote)
            return code, output.getvalue(), calls, written, pushed == local, reviewed

    def test_minor_fix_is_pushed_with_a_lease_on_the_reviewed_head(self):
        code, output, _, written, pushed, _ = self.run_branch("push-fix")
        self.assertEqual((code, pushed, [w["action"] for w in written]), (0, True, ["push-fix"]), output)
        self.assertIn("You pushed last", output)

    def test_branch_writes_hold_on_size_level_moved_head_fork_and_a_racing_push(self):
        for changes, message in (({"lines": 60}, "more than a minor fix"),
                                 ({"level": "review"}, "outside the review level"),
                                 ({"github_head": "c" * 40}, "head changed"),
                                 ({"fork": True}, "lives in a fork"),
                                 ({"race": True}, "git push failed")):
            with self.subTest(**changes):
                code, output, _, written, pushed, _ = self.run_branch("push-fix", **changes)
                self.assertEqual((code, pushed, written), (1, False, []), output)
                self.assertIn(message, output)
        code, output, _, _, pushed, _ = self.run_branch("push-fix", lines=60, level="major")
        self.assertEqual((code, pushed), (0, True), output)

    def test_base_merge_asks_github_to_refuse_a_moved_head(self):
        code, output, calls, written, _, reviewed = self.run_branch("update-branch")
        self.assertEqual(code, 0, output)
        self.assertEqual(calls[-1], ("repos/owner/repo/pulls/17/update-branch", "PUT", {"expected_head_sha": reviewed}))
        self.assertEqual([w["action"] for w in written], ["update-branch"])


if __name__ == "__main__":
    unittest.main()
