#!/usr/bin/env python3
"""findings.py <pr-number> [review-id ...]

Print the full text of blocking reviews plus their inline comments.

Inline comments are where the substance lives -- a review body usually just
says "see inline comments for 3 issues". They live on a different endpoint than
the review itself and have to be joined on `pull_request_review_id`, which is
why this is a script and not a one-liner you retype every time.

With no review-id, prints every review still in CHANGES_REQUESTED state.

findings.py <pr-number> --draft <review-id> prints a `verified_findings` draft for
a bot's review: one entry per inline finding, with status "confirm". Set each to
fixed or overstated only after checking it at the head; until every entry is
confirmed, the assessment does not validate and `review_write.py dismiss` holds.
"""
import json
import subprocess
import sys
import time
from review_requests import effective_reviews


def gh(args, tries=3):
    for attempt in range(tries):
        r = subprocess.run(args, capture_output=True, text=True)
        if r.returncode == 0:
            try:
                return json.loads(r.stdout)
            except json.JSONDecodeError:
                return r.stdout
        if attempt < tries - 1:
            time.sleep(2 * (attempt + 1))
    return None


def is_bot(user):
    """A review bot by GitHub's account type or its `[bot]` login, never by the caller's say-so."""
    return (user or {}).get("type") == "Bot" or ((user or {}).get("login") or "").endswith("[bot]")


def inline_comments(repo, num):
    """Every inline review comment on the PR, or None when unreadable."""
    pages = gh(["gh", "api", f"repos/{repo}/pulls/{num}/comments?per_page=100", "--paginate", "--slurp"])
    if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
        return None
    return [comment for page in pages for comment in page]


def review_findings(comments, review_id):
    """A review's own findings: its inline comments that start a thread, not its replies."""
    return [c for c in comments if c.get("pull_request_review_id") == review_id and not c.get("in_reply_to_id")]


def line_of(comment):
    return comment.get("line") or comment.get("original_line") or "?"


def superseded_bot_reviews(reviews, head):
    """Each bot's changes request at an older head that a later COMMENT review of its own at `head` followed.
    GitHub keeps the changes request in force, because a COMMENT review does not replace it."""
    at = lambda r: r.get("submitted_at") or r.get("submittedAt") or ""
    sha = lambda r: r.get("commit_id") or r.get("commitOid")
    who = lambda r: (r.get("user") or r.get("author") or {}).get("login")
    return [review for login, review in effective_reviews(reviews).items()
            if review.get("state") == "CHANGES_REQUESTED" and is_bot(review.get("user") or review.get("author"))
            and sha(review) != head and any(who(r) == login and r.get("state") == "COMMENTED" and sha(r) == head
                                            and at(r) > at(review) for r in reviews)]


def draft(comments, review_id):
    """Unconfirmed verified_findings for a review's inline findings; the reviewer sets each status."""
    return [{"comment": c["id"], "status": "confirm", "file": c["path"], "line": line_of(c),
             "observation": "Check at the head: " + ((c.get("body") or "").strip().splitlines() or [""])[0]}
            for c in review_findings(comments, review_id)]


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: findings.py <pr-number> [review-id ...]")
    num = sys.argv[1]
    repo = (gh(["gh", "repo", "view", "--json", "nameWithOwner",
                "-q", ".nameWithOwner"]) or "").strip()
    if sys.argv[2:3] == ["--draft"]:
        if len(sys.argv) != 4:
            sys.exit("usage: findings.py <pr-number> --draft <review-id>")
        comments = inline_comments(repo, num)
        if comments is None:
            sys.exit(f"could not read inline findings for #{num}; coverage unknown")
        print(json.dumps(draft(comments, int(sys.argv[3])), indent=2))
        return
    wanted = {int(a) for a in sys.argv[2:]} if len(sys.argv) > 2 else None

    pages = gh(["gh", "api", f"repos/{repo}/pulls/{num}/reviews?per_page=100", "--paginate", "--slurp"])
    if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
        # A failed fetch and a PR with no reviews produce the same empty list.
        # Saying "no blocking reviews" on a fetch failure invents a clean bill
        # of health, so refuse instead.
        sys.exit(f"could not read reviews for #{num} -- re-check by hand rather "
                 f"than treating this as 'no blocking reviews'")
    reviews = [review for page in pages for review in page]
    if wanted is None:
        targets = [r for r in effective_reviews(reviews).values() if r.get("state") == "CHANGES_REQUESTED"]
    else:
        targets = [r for r in reviews if r.get("id") in wanted]
    if not targets:
        print("no blocking reviews on this PR")
        return

    comments = inline_comments(repo, num)
    if comments is None:
        sys.exit(f"could not read inline findings for #{num}; coverage unknown")

    for r in targets:
        who = (r.get("user") or {}).get("login", "?")
        print("=" * 78)
        print(f'REVIEW {r["id"]}  by {who}  {r.get("state")}  '
              f'{(r.get("submitted_at") or "")[:16]}')
        print("=" * 78)
        print((r.get("body") or "").strip() or "(no body)")

        mine = [c for c in comments if c.get("pull_request_review_id") == r["id"]]
        print(f"\n--- {len(mine)} inline comment(s) on this review ---")
        for c in mine:
            resolved = " [reply-thread]" if c.get("in_reply_to_id") else ""
            print(f'\n### {c["path"]}:{line_of(c)} (comment {c["id"]}){resolved}')
            print((c.get("body") or "").strip())
        print()


if __name__ == "__main__":
    main()
