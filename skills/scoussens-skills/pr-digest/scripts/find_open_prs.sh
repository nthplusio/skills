#!/usr/bin/env bash
# Lists PRs currently open against a branch. This is a deliberate *live
# snapshot*, not bound to the digest's merged-PR time window: a PR opened
# three weeks ago that's still sitting there today is exactly the kind of
# thing worth surfacing alongside "what already shipped" — filtering it out
# by open-date would hide the very staleness that makes it worth mentioning.
#
# Two callers, two shapes:
#   - Step 2b (ready-for-review section of a digest) — default: drafts excluded.
#   - Step 2c (open-PR inventory) — pass --include-drafts. On a long-lived
#     branch drafts are usually the *majority* of what's open, and they are
#     the whole point of an inventory, so excluding them there would hide the
#     finding rather than tidy it.
#
# Usage: find_open_prs.sh [--include-drafts] <owner/repo> <branch> [limit]
#
# Output: JSON array — number, title, url, author, headRefName, createdAt,
# updatedAt, isDraft, reviewDecision, additions, deletions, changedFiles,
# statusCheckRollup — oldest-open first.
#
# `updatedAt` and the diffstat fields cost nothing extra in the same call and
# are what the inventory's staleness/size flags are derived from — an
# oldest-first list alone cannot tell a PR pushed yesterday from one untouched
# since the day it opened, and that difference is the whole signal.
#
# The repository argument binds the query independently of the installed path.
set -euo pipefail

INCLUDE_DRAFTS=0
ARGS=()
for arg in "$@"; do
  case "$arg" in
    --include-drafts) INCLUDE_DRAFTS=1 ;;
    *) ARGS+=("$arg") ;;
  esac
done

REPO="${ARGS[0]:?usage: find_open_prs.sh [--include-drafts] <owner/repo> <branch> [limit]}"
BRANCH="${ARGS[1]:?branch required}"
LIMIT="${ARGS[2]:-200}"
if [[ ! "$LIMIT" =~ ^[1-9][0-9]{0,3}$ ]] || (( LIMIT > 1000 )); then
  echo 'error: limit must be between 1 and 1000.' >&2
  exit 2
fi
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

if ! gh auth status >/dev/null 2>&1; then
  echo "error: gh is not authenticated (gh auth status failed). Run 'gh auth login' and retry." >&2
  exit 1
fi

if [[ "$INCLUDE_DRAFTS" -eq 1 ]]; then
  FILTER='sort_by(.createdAt)'
else
  FILTER='[.[] | select(.isDraft == false)] | sort_by(.createdAt)'
fi

gh pr list \
  --repo "$REPO" \
  --state open \
  --base "$BRANCH" \
  --json number,title,url,author,headRefName,createdAt,updatedAt,isDraft,reviewDecision,additions,deletions,changedFiles,statusCheckRollup \
  --limit "$LIMIT" > "$TMP/prs.json"
if (( $(jq 'length' "$TMP/prs.json") >= LIMIT )); then
  echo "error: open PR results reached limit $LIMIT for $REPO before draft filtering; coverage may be incomplete. Increase the limit (max 1000) or enumerate with a paginated forge API before reporting a complete inventory." >&2
  exit 2
fi
jq "$FILTER" "$TMP/prs.json"
