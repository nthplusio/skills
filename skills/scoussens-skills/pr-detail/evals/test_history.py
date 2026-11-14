import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pr_history import normalize, render


def evidence():
    reviews = [
        {"id": 10, "state": "DISMISSED", "submittedAt": "2026-11-02T15:00:00Z", "body": "",
         "author": {"login": "reviewer", "type": "User"}, "commitOid": "a" * 40, "url": "https://example.test/review/10"},
        {"id": 11, "state": "DISMISSED", "submittedAt": "2026-11-02T16:00:00Z", "body": "Unclassified dismissal",
         "author": {"login": "bot[bot]", "type": "Bot"}, "url": "https://example.test/review/11"},
        {"id": 12, "state": "COMMENTED", "submittedAt": "2026-11-03T15:00:00Z", "body": "Please consider this",
         "author": {"login": "author", "type": "User"}, "url": "https://example.test/review/12"},
    ]
    return {"schemaVersion": 1, "repository": "sample/product", "collectedAt": "2026-11-03T16:00:00Z",
            "pr": {"number": 482, "author": {"login": "author"}, "headRefOid": "b" * 40,
                   "baseRefOid": "c" * 40, "createdAt": "2026-11-01T10:00:00Z", "reviews": reviews},
            "timeline": [{"id": 31, "event": "review_dismissed", "at": "2026-11-02T17:00:00Z",
                          "dismissedReview": {"review_id": 10, "state": "changes_requested"}},
                         {"id": 32, "event": "head_ref_force_pushed", "at": "2026-11-03T14:00:00Z"}],
            "threads": [{"id": "thread-1", "isResolved": True, "comments": {"nodes": [
                {"id": "comment-1", "pullRequestReview": {"databaseId": 10}, "path": "store.py", "line": 42,
                 "body": "Rollback drops **saved filters**.", "url": "https://example.test/thread/1",
                 "author": {"login": "reviewer"}}]}}], "failedFetches": [], "truncatedSources": []}


class HistoryTests(unittest.TestCase):
    def test_dismissal_requires_original_verdict_and_empty_reviews_keep_inline_reason(self):
        history = normalize(evidence())
        returns = [item for item in history["events"] if item["returned"]]
        self.assertEqual([item["id"] for item in returns], ["review-10"])
        self.assertEqual(returns[0]["head"], "a" * 40)
        source = render(history, "America/Chicago")
        self.assertIn("↩ 1 return", source)
        self.assertIn("Nov 02, 09:00 CST", source)
        self.assertIn("Rollback drops <strong>saved filters</strong>.", source)
        self.assertIn("Discussion marked resolved. This does not confirm that the code is fixed.", source)
        self.assertIn("no recorded original decision", source)
        self.assertIn("Ticket history unavailable", source)
        self.assertIn('href="https://example.test/thread/1"', source)
        self.assertNotIn("Fixed in code", source)
        collapsed = source.split('<details class="history-detail">', 1)[0]
        self.assertNotIn("Rollback drops", collapsed)
        self.assertNotIn("**saved filters**", collapsed)

    def test_tracker_events_keep_their_own_provenance_and_partial_coverage(self):
        raw = evidence()
        raw["failedFetches"] = ["comments"]
        raw["ticketEvidence"] = {"status": "partial", "tickets": [{"id": "APP-217", "state": "In review"}],
                                 "events": [{"id": "tracker-1", "at": "2026-10-30T09:00:00Z", "actor": "Maya",
                                             "label": "Ticket entered development", "url": "https://tracker.test/APP-217"}]}
        history = normalize(raw)
        self.assertEqual(history["events"][0]["kind"], "tracker")
        source = render(history)
        self.assertIn("Ticket history partial", source)
        self.assertIn("Some PR history could not be read: comments", source)
        self.assertIn("Ticket APP-217 · In review", source)
        self.assertIn("https://tracker.test/APP-217", source)
        broken = copy.deepcopy(raw)
        del broken["ticketEvidence"]["events"][0]["url"]
        with self.assertRaises(ValueError):
            normalize(broken)

    def test_comments_and_unassociated_findings_stay_visible_without_inventing_returns(self):
        raw = evidence()
        raw["pr"]["comments"] = [{"id": 21, "createdAt": "2026-11-02T18:00:00Z",
                                  "author": {"login": "author", "type": "User"},
                                  "body": "I pushed a revision, not yet verified.",
                                  "url": "https://example.test/comment/21"}]
        orphan = copy.deepcopy(raw["threads"][0])
        orphan["id"] = "orphan"
        root = orphan["comments"]["nodes"][0]
        root.pop("pullRequestReview")
        root["body"] = "Unassociated inline objection"
        root["createdAt"] = "2026-11-02T19:00:00Z"
        raw["threads"].append(orphan)
        history = normalize(raw)
        self.assertEqual(sum(item["returned"] for item in history["events"]), 1)
        self.assertEqual([item["kind"] for item in history["events"] if item["kind"] in ("comment", "feedback")],
                         ["comment", "feedback"])
        source = render(history)
        self.assertIn("I pushed a revision, not yet verified.", source)
        self.assertIn('<details><summary>Read comment</summary><div class="md"><p>I pushed a revision, not yet verified.</p>', source)
        self.assertIn("Unassociated inline objection", source)
        self.assertIn("review association unknown", source)

    def test_user_and_team_request_targets_and_removals_remain_visible(self):
        raw = evidence()
        raw["timeline"] += [{"id": 40, "event": "review_requested", "actor": "author",
                             "at": "2026-11-03T15:00:00Z", "requestedTeam": "data-reviewers"},
                            {"id": 41, "event": "review_request_removed", "actor": "maintainer",
                             "at": "2026-11-03T15:30:00Z", "requestedReviewer": "reviewer"}]
        history = normalize(raw)
        self.assertEqual(history["events"][-1]["requestedReviewer"], "reviewer")
        source = render(history)
        for text in ("Team target: data-reviewers", "Review request removed", "Reviewer target: reviewer"):
            self.assertIn(text, source)

    def test_hostile_bodies_and_links_remain_inert(self):
        raw = evidence()
        raw["pr"]["reviews"][0]["body"] = '<script>alert(1)</script> [unsafe](javascript:alert)'
        raw["pr"]["reviews"][0]["url"] = 'javascript:alert(1)'
        source = render(normalize(raw))
        self.assertNotIn("<script>", source)
        self.assertNotIn('href="javascript:', source)
        self.assertIn("&lt;script&gt;", source)


if __name__ == "__main__":
    unittest.main()
