#!/usr/bin/env bash
# detect_setup.sh [base-branch]
# One-time probe: what review machinery does this repo actually have?
# Run this before reviewing anything — it decides how you clear blockers.
set -uo pipefail
BASE="${1:-}"
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null) || { echo "not a gh repo"; exit 1; }
echo "repo: $REPO"

if [ -z "$BASE" ]; then
  BASE=$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name)
  echo "base: $BASE  (default branch; confirm with the user if the team targets something else)"
else
  echo "base: $BASE"
fi

echo
echo "merge:"
gh repo view --json mergeCommitAllowed,squashMergeAllowed,rebaseMergeAllowed,deleteBranchOnMerge \
  -q 'to_entries|map("  \(.key)=\(.value)")|.[]'
MQ=$(gh api "repos/$REPO/branches/$BASE/protection" -q '.required_status_checks.checks|length' 2>/dev/null || echo "?")
QUEUE=$(gh api graphql -f query="{repository(owner:\"${REPO%%/*}\",name:\"${REPO##*/}\"){mergeQueue(branch:\"$BASE\"){id}}}" \
  -q '.data.repository.mergeQueue.id' 2>/dev/null)
if [ -n "$QUEUE" ] && [ "$QUEUE" != "null" ]; then
  echo "  MERGE QUEUE: enabled -> call 'gh pr merge <n>' with NO strategy flag; the queue owns the strategy"
else
  echo "  merge queue: not detected -> pick the strategy the repo's history uses (see below)"
fi
echo "  recent merge style on $BASE:"
git log --oneline -3 "origin/$BASE" --merges 2>/dev/null | sed 's/^/    /'

echo
echo "review bots (authors of CHANGES_REQUESTED in the last 20 PRs):"
for n in $(gh pr list --base "$BASE" --state all --limit 20 --json number -q '.[].number'); do
  gh api "repos/$REPO/pulls/$n/reviews" -q '.[]|select(.state=="CHANGES_REQUESTED")|.user.login' 2>/dev/null
done | sort | uniq -c | sort -rn | sed 's/^/  /'

echo
echo "repo conventions docs (grounds severity claims — cite these, don't invent rules):"
for f in CLAUDE.md AGENTS.md CONTRIBUTING.md docs/conventions.md docs/README.md; do
  [ -f "$f" ] && echo "  $f"
done
# One loop, not `ls` over several candidates: `ls` exits non-zero when any
# argument is missing, and being the last command that became the script's own
# exit status -- so a successful detection reported failure to anything checking
# it, or running under `set -e`.
for d in docs/decisions docs/adr docs/architecture docs/decision-records adr; do
  [ -d "$d" ] && echo "  $d"
done

exit 0
