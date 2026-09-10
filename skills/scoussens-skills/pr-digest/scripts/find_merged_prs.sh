#!/usr/bin/env bash
# Lists PRs actually merged into a branch within a UTC time window.
#
# Why this shells out to `gh pr list --search` instead of walking git log:
# an earlier version of this script tried three different git-log
# strategies (grep the default "Merge pull request #N" title, --first-parent
# traversal, --merges + --since/--until) and every one of them silently
# UNDER-COUNTED real merged PRs in this repo, for reasons that turned out to
# be structural, not fixable with a better regex or a wider date net:
#
#   - Squash merges land as a single-parent commit — invisible to `--merges`
#     entirely. This repo has squash merging enabled and uses it heavily.
#   - Stacked PRs (a PR opened against a co-worker's feature branch, not
#     against this branch) show up in this branch's ancestry once THEIR
#     base branch eventually merges too — but they never targeted this
#     branch. "What was this PR's base ref" is GitHub metadata with no
#     git-graph equivalent, especially once the head ref is deleted on
#     merge (this repo does that by default).
#   - --first-parent looked like the fix for merge noise, but it isn't:
#     in a repo merging faster than ~1 PR per instant (true here), only
#     one PR at a time can occupy the first-parent slot — every other PR
#     that lands nearby becomes reachable only via someone else's SECOND
#     parent. --first-parent's own "spine" ends up far shorter than the
#     real list of merged PRs.
#   - git log --since/--until can itself skip real commits inside the
#     stated window (verified: a commit authored/committed inside the
#     window was missing from --since/--until output but present in an
#     unbounded log) — its revision-walker prunes based on a date-ordered
#     heuristic that isn't fully reliable across merge topology, and even
#     --since-as-filter (which exists specifically to disable early
#     pruning) didn't recover it.
#
# GitHub's PR search knows the real base ref and the real merge time
# directly, so none of the above applies. This is the reliable source.
#
# Usage: find_merged_prs.sh <branch> <start-utc-iso> <end-utc-iso> [limit]
#   <start>/<end> must be explicit UTC instants, e.g. 2026-07-20T00:00:00Z —
#   compute these once against a single clock (see SKILL.md) rather than
#   passing bare YYYY-MM-DD and hoping the timezone works out; `mergedAt`
#   from GitHub is itself always UTC, so matching that avoids drift.
#
# Output: JSON array (gh's own --json shape) — number, title, mergedAt,
# url, author, headRefName — sorted by merge time, oldest first.
set -euo pipefail

BRANCH="${1:?usage: find_merged_prs.sh <branch> <start-utc-iso> <end-utc-iso> [limit]}"
START="${2:?start UTC ISO-8601 required, e.g. 2026-07-20T00:00:00Z}"
END="${3:?end UTC ISO-8601 required, e.g. 2026-07-23T00:00:00Z}"
LIMIT="${4:-300}"

if ! gh auth status >/dev/null 2>&1; then
  cat >&2 <<'EOF'
error: gh is not authenticated (gh auth status failed).

This script deliberately has no git-log fallback: every fallback strategy
tried during development silently under-counted real merged PRs (squash
merges and stacked PRs are invisible to plain commit-ancestry walks in
this repo — see the comment block at the top of this file). A degraded
answer that looks complete is worse than a clear error here.

Run `gh auth login` and retry.
EOF
  exit 1
fi

gh pr list \
  --state merged \
  --base "$BRANCH" \
  --search "merged:${START}..${END}" \
  --json number,title,mergedAt,url,author,headRefName \
  --limit "$LIMIT" \
  --jq 'sort_by(.mergedAt)'
