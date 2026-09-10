#!/usr/bin/env bash
# Gather every evidence source /pr-detail needs for one PR, as a single JSON blob.
#
# Usage: gather_pr.sh <owner/repo> <pr-number>
#
# Why one script instead of five ad-hoc `gh` calls per run: the five sources
# below each have a quirk that is easy to get wrong, and getting one wrong
# changes the evaluation rather than just losing detail.
#
#   .reviews      MUST include DISMISSED entries. This repo's AI reviewer
#                 dismisses its own prior review every time new commits land,
#                 so the dismissed rows ARE the record of how many review
#                 rounds a PR took. (pr-digest deliberately filters these out
#                 because it reports CURRENT status; a retrospective needs the
#                 opposite.) Verified on PR #2094: 5 dismissals = 5 rounds.
#
#   .threads      Only GraphQL exposes isResolved / isOutdated. Thread
#                 resolution is how you tell "reviewer raised it and it was
#                 settled" from "merged with it still open" — on #2094, all 7
#                 threads were unresolved at merge.
#
#   .timeline     The REST timeline is the only source for head_ref_force_pushed,
#                 ready_for_review, review_dismissed and review_requested in
#                 chronological order. Note its `reviewed` events UNDER-count
#                 real reviews (an empty-bodied review can be missing) — use
#                 .reviews for the review set and .timeline only for ordering
#                 and for the events .reviews cannot express.
#
#   .commits      Includes commits authored by OTHER people when the branch
#                 picked up upstream work. Filter by author before calling
#                 anything "churn by the PR author".
#
#   .checkRuns    statusCheckRollup reflects only the LATEST commit, so a PR
#                 that was red for a day and green at merge looks clean. This
#                 walks check-runs per commit to recover the real CI history.

set -euo pipefail

# Sources are staged in files, never passed as `jq --argjson` arguments: the
# PR payload for a large PR exceeds ARG_MAX and jq dies with "Argument list
# too long". PR #1215 (+13k lines) hit this on the first real run.
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

REPO="${1:?usage: gather_pr.sh <owner/repo> <pr-number>}"
NUM="${2:?usage: gather_pr.sh <owner/repo> <pr-number>}"
OWNER="${REPO%%/*}"
NAME="${REPO##*/}"

if ! gh auth status >/dev/null 2>&1; then
  echo "gh is not authenticated. Run 'gh auth login' and retry." >&2
  echo "Refusing to continue: a partial evidence set would produce an" >&2
  echo "evaluation that looks complete but silently omits review history." >&2
  exit 1
fi

gh pr view "$NUM" --repo "$REPO" --json \
  number,title,body,author,state,isDraft,createdAt,mergedAt,closedAt,updatedAt,\
additions,deletions,changedFiles,files,headRefName,baseRefName,labels,\
reviews,comments,commits,statusCheckRollup,mergedBy,reviewDecision > "$TMP/pr.json"

gh api graphql -f query='
query($o:String!,$r:String!,$n:Int!){
  repository(owner:$o,name:$r){ pullRequest(number:$n){
    reviewThreads(first:100){ nodes{
      isResolved isOutdated isCollapsed
      comments(first:20){ nodes{ author{login} createdAt path line body } }
    }}
  }}
}' -F o="$OWNER" -F r="$NAME" -F n="$NUM" \
  --jq '.data.repository.pullRequest.reviewThreads.nodes' > "$TMP/threads.json" 2>/dev/null \
  || echo '[]' > "$TMP/threads.json"

gh api "repos/$REPO/issues/$NUM/timeline?per_page=100" --paginate \
  --jq '[.[] | {event, at: (.created_at // .submitted_at // .committed_at // .author.date // .committer.date),
                actor: (.actor.login // .user.login // .author.name // null),
                state, label: .label.name,
                sha: (.sha // .commit_id),
                message: (.message // null),
                ref: (.source.issue.number // null)}]' > "$TMP/timeline.json" 2>/dev/null \
  || echo '[]' > "$TMP/timeline.json"

# Per-commit CI history. Bounded to 40 commits: beyond that the pattern is
# established and the extra calls cost more than they inform.
SHAS=$(jq -r '.commits[].oid' "$TMP/pr.json" | head -40)
echo '[]' > "$TMP/checks.json"
if [ -n "$SHAS" ]; then
  for sha in $SHAS; do
    gh api "repos/$REPO/commits/$sha/check-runs" \
      --jq "{sha: \"$sha\", runs: [.check_runs[] | {name, conclusion, status}]}" \
      2>/dev/null || echo "{\"sha\":\"$sha\",\"runs\":[]}"
  done | jq -s '.' > "$TMP/checks.json"
fi

jq -n \
  --slurpfile pr       "$TMP/pr.json" \
  --slurpfile threads  "$TMP/threads.json" \
  --slurpfile timeline "$TMP/timeline.json" \
  --slurpfile checks   "$TMP/checks.json" \
  '{pr: $pr[0], threads: $threads[0], timeline: $timeline[0], checkRuns: $checks[0]}'
