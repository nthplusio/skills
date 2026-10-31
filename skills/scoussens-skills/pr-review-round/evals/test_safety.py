"""Local forge doubles only; these tests never contact GitHub."""
import contextlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import land
import merge_queue
import review_write
import round_report
from md_to_html import render

HEAD = "a" * 40


def state(**changes):
    return {"state": "OPEN", "headRefOid": HEAD,
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
    def run_land(self, states, args=None, failure=False):
        output = io.StringIO()
        snapshots = iter(states)
        writes = []
        current = {}

        def forge(command, **kwargs):
            nonlocal current
            if command[:3] == ["gh", "pr", "view"]:
                current = next(snapshots)
                payload = {"id": "PR_fixture", **current}
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

        with patch.object(sys, "argv", ["land.py", *(args or ["--enqueue", f"17:{HEAD}"])]), \
                patch.object(subprocess, "run", side_effect=forge), \
                patch.object(land.time, "sleep"), patch.object(land, "MAX_POLLS", 2), \
                contextlib.redirect_stdout(output):
            code = land.main()
        for command in writes:
            self.assertEqual(command, ["gh", "pr", "merge", "17", "--match-head-commit", HEAD])
        return len(writes), output.getvalue(), code

    def test_revoked_approval_stops_enqueue(self):
        writes, output, code = self.run_land([state(), state(reviewDecision="CHANGES_REQUESTED")])
        self.assertEqual(writes, 1, output)
        self.assertIn("current approval not confirmed", output)
        self.assertEqual(code, 1)

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
                self.assertIn("review again", output)
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

    def test_evicted_approved_head_is_reenqueued_then_observed_merged(self):
        writes, output, code = self.run_land([state(), state(), state(state="MERGED")])
        self.assertEqual(writes, 2)
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


class QueueReportTests(unittest.TestCase):
    def test_verdict_uses_membership_not_cleanliness(self):
        for snapshot, expected in [
            (state(), "APPROVED"),
            (state(queue_state="queued", mergeStateStatus="BLOCKED"), "APPROVED_QUEUED"),
            (state(queue_state="unknown"), "APPROVED_QUEUE_UNKNOWN"),
            (state(mergeStateStatus="DIRTY"), "APPROVED_CONFLICTING"),
            (state(mergeStateStatus="DIRTY", reviewDecision="REVIEW_REQUIRED"), "CONFLICTING"),
            (state(state="MERGED"), "MERGED"), (state(state="CLOSED"), "CLOSED"),
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
    def run_write(self, action, *, flags=(), snapshots=None, failure=False, author="author"):
        writes = []
        snapshots = iter(snapshots or [{"head": {"sha": HEAD}, "state": "open",
                                      "draft": False, "auto_merge": None, "user": {"login": author}}] * 2)

        def forge(command, **kwargs):
            method = command[command.index("--method") + 1]
            if method != "GET":
                writes.append((command[2], json.loads(kwargs["input"])))
                return subprocess.CompletedProcess(command, int(failure), '{"id": 42}', "denied" if failure else "")
            payload = {"login": "reviewer"} if command[2] == "user" else next(snapshots)
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

        with tempfile.TemporaryDirectory() as directory:
            body = Path(directory) / "review.md"
            body.write_text("Verified store.py:42 reads the corrected key.")
            output = io.StringIO()
            with patch.object(sys, "argv", ["review_write.py", action, "17", "--repo", "owner/repo",
                                           "--head", HEAD, "--body-file", str(body),
                                           "--review-id", "9", *flags]), \
                    patch.object(subprocess, "run", side_effect=forge), contextlib.redirect_stdout(output):
                code = review_write.main()
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

    def test_auto_merge_requires_landing_authority_for_clearance(self):
        pr = {"head": {"sha": HEAD}, "state": "open", "draft": False,
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

    def test_head_movement_during_dismissal_is_not_reported_as_clearance(self):
        pr = {"head": {"sha": HEAD}, "state": "open", "draft": False, "auto_merge": None}
        writes, output, code = self.run_write("dismiss", flags=["--write"],
                                             snapshots=[pr, {"head": {"sha": "b" * 40}}])
        self.assertEqual(len(writes), 1)
        self.assertIn("HEAD MOVED during write", output)
        self.assertEqual(code, 1)


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
