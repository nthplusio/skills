# Deriving the CI and review-status pills

Reached from Step 2b, and only when the digest includes ready-for-review PRs.
CI uses the `find_open_prs.sh` snapshot; review status also uses the full
paginated review history.

Each result carries `reviewDecision` and `statusCheckRollup` directly from
GitHub — no extra API calls needed for CI status, but `reviewDecision`
alone is **not enough** for the review-status pill (see below — this bit
cost a real, user-caught bug the first time this skill ran).

- **CI status**: derive one label from `statusCheckRollup` (an array of
  checks, each with its own `status`/`conclusion`). Any `conclusion` of
  `FAILURE`/`ERROR`/`TIMED_OUT` → "CI failing"; else any check still
  `IN_PROGRESS`/`QUEUED`/`PENDING` → "CI running"; else if every check
  concluded `SUCCESS` (ignore `SKIPPED`/`NEUTRAL` — those aren't failures,
  just checks that didn't apply) → "CI passing"; an empty array → "No
  checks configured."
- **Review status — don't trust `reviewDecision` at face value.**
  `reviewDecision` only records the latest *formal* verdict (an explicit
  Approve or Request-changes review); it has exactly three real values —
  `APPROVED`, `CHANGES_REQUESTED`, or `REVIEW_REQUIRED` (GitHub also
  returns `null` for the same "no formal verdict yet" case) — and a
  comment-only review, no matter how thorough or how many times it's run,
  never moves it off `REVIEW_REQUIRED`/`null`. Treating that value as
  "nobody's looked at this" produced a digest that told a PR author their
  own just-completed review was "awaiting review" in the same paragraph
  that quoted the review — visibly self-contradictory to anyone who'd just
  read both. Branch on the actual value, and for the ambiguous case, look
  at the review history before picking a label:
  - `APPROVED` → an **"approved"** pill (calm/positive, distinct from the
    "reviewed; no formal verdict" pill below — an approval is a stronger, formal
    signal and deserves to read as one). Naming the approver is a nice
    touch when there's room.
  - `CHANGES_REQUESTED` → a **blocking** pill. Fetch the actual reason with
    the paginated review-history command below; surface the relevant review's
    author and a trimmed excerpt of its body. If the body is empty, say the
    reviewer requested changes without a written reason.
  - `REVIEW_REQUIRED` or `null` → **fetch the full review history** before
    labeling anything. Exclude `DISMISSED` and `PENDING` — some automated
    reviewers dismiss their own prior review whenever new commits land, so a
    dismissed entry describes a stale commit, not the PR as it stands now.
    Separate the author's own replies from reviews by other people or bots.
    Then:
    - If that filtered list is **empty** → the quiet
      **"awaiting review"** pill means no surviving submitted reviewer verdict
      or comment, not proof that nobody has read the code.
    - If it's **non-empty** (one or more `COMMENTED` reviews, human or
      bot) → the PR *has* been reviewed, just without a formal verdict —
      label it **"reviewed; no formal verdict"**. Read the surviving reviews
      and quote relevant findings with their author and link. A `COMMENTED`
      review saying "Do not merge" is blocking feedback despite its state;
      surface that objection. If a reviewer explicitly says "No blocking
      issues found," quote it as that reviewer's assessment of the reviewed
      commit, not as clearance inferred from `COMMENTED`. Empty bodies give
      no evidence about whether findings exist.

  Retrieve all pages, including later objections:

  ```bash
  set -o pipefail
  gh api "repos/<owner/repo>/pulls/<n>/reviews?per_page=100" --paginate --slurp |
    jq '[.[][] | select(.state != "DISMISSED" and .state != "PENDING")] | sort_by(.submitted_at)'
  ```

  If retrieval fails, report
  **"review status unknown"** and the gap; an empty failed response cannot
  establish "awaiting review" or clearance. REST review authors are in
  `user.login`, with `user.type` distinguishing bots, and links in `html_url`.

  Because this whole check re-fetches per-PR state, it can also catch a
  PR that changed status *during* the digest run (a review lands mid-run)
  — when history and the initial snapshot disagree, refresh the formal decision
  with `gh pr view <n> --repo <owner/repo> --json reviewDecision,headRefOid`
  before labeling it. A comment-only review cannot substitute for that decision.
