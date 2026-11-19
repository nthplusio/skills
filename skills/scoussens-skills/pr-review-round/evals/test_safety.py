"""Local forge doubles only; these tests never contact GitHub."""
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
import branch_rules
import land
import ledger
import merge_queue
import review_write
import round_report
from md_to_html import render
from decision_fixtures import assessment, authority, bundle, BASE, REVISION, TARGET

HEAD = "a" * 40


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
    def run_land(self, states, args=None, failure=False, item=None, permission=None):
        output = io.StringIO()
        snapshots = iter(states)
        writes = []
        current = {}

        def forge(command, **kwargs):
            nonlocal current
            if command[:3] == ["gh", "pr", "view"]:
                current = next(snapshots, current)
                payload = {"id": "PR_fixture", **current}
            elif command[:2] == ["gh", "api"] and "/git/ref/heads/" in command[2]:
                target = current.get("target") or {}
                payload = {"ref": "refs/heads/main", "object": {"type": "commit", "sha": target.get("sha")}}
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
            if "--enqueue" in argv or "--enable-auto-merge" in argv:
                argv = [*argv, "--repo", "owner/repo", "--authority", str(authority_file),
                        "--assessments", str(assessment_file)]
            with patch.object(sys, "argv", ["land.py", *argv]), \
                patch.object(subprocess, "run", side_effect=forge), \
                patch.dict(os.environ, XDG_STATE_HOME=tmp), \
                patch.object(land.time, "sleep"), patch.object(land, "MAX_POLLS", 2), \
                contextlib.redirect_stdout(output):
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
                (state(), assessment(), authority(possible_landing=False)),
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
                  target=TARGET, after=None, rules=None, pusher=None):
        writes = []
        snapshots = iter(snapshots or [{"head": {"sha": HEAD}, "state": "open",
                                      "base": {"sha": BASE, "ref": "main"}, "updated_at": REVISION,
                                      "draft": False, "auto_merge": None, "user": {"login": author}}] * 2)

        def forge(command, **kwargs):
            if "/git/ref/heads/" in command[2]:
                payload = {"ref": "refs/heads/main", "object": {"type": "commit", "sha": (target or {}).get("sha")}}
                return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
            method = command[command.index("--method") + 1]
            if method != "GET":
                writes.append((command[2], json.loads(kwargs["input"])))
                return subprocess.CompletedProcess(command, int(failure),
                                                   '{"id": 42, "html_url": "https://example.test/posted/42"}',
                                                   "denied" if failure else "")
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
                    patch.object(subprocess, "run", side_effect=forge), \
                    patch.dict(os.environ, XDG_STATE_HOME=directory), \
                    patch.object(review_write, "state_of", return_value=after or state()), \
                    patch.object(review_write, "review_rules", return_value=rules), \
                    patch.object(review_write, "last_pusher", return_value=pusher), contextlib.redirect_stdout(output):
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
        for action in ["approve", "dismiss"]:
            with self.subTest(action=action):
                writes, output, code = self.run_write(action, flags=["--write"], snapshots=[pr])
                self.assertEqual(writes, [])
                self.assertIn("merge authority required", output)
                self.assertEqual(code, 1)
                writes, _, code = self.run_write(action, flags=["--write", "--allow-landing"], snapshots=[pr, pr])
                self.assertEqual(len(writes), 1)
                self.assertEqual(code, 0)

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

    def test_changed_or_unknown_actual_target_blocks_all_review_writes(self):
        for action in ("approve", "dismiss", "comment", "request-changes"):
            for target in ({**TARGET, "sha": "f" * 40}, {**TARGET, "sha": None}):
                with self.subTest(action=action, target=target):
                    writes, output, code = self.run_write(action, flags=["--write"], target=target)
                    self.assertEqual((writes, code), ([], 1), output)
                    self.assertIn("actual target ref changed or unavailable", output)

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


if __name__ == "__main__":
    unittest.main()
