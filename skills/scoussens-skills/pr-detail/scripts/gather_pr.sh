#!/usr/bin/env bash
# Gather every evidence source /pr-detail needs for one PR, as a single JSON blob.
#
# Usage: gather_pr.sh <owner/repo> <pr-number>
#
# Why one script instead of five ad-hoc `gh` calls per run: the five sources
# below each have a quirk that is easy to get wrong, and getting one wrong
# changes the evaluation rather than just losing detail.
#
#   .reviews      MUST include DISMISSED entries. Some AI reviewers dismiss
#                 their own prior review every time new commits land,
#                 so the dismissed rows ARE the record of how many review
#                 rounds a PR took. (pr-digest deliberately filters these out
#                 because it reports CURRENT status; a retrospective needs the
#                 opposite.) Verified on one PR: 5 dismissals = 5 rounds.
#
#   .threads      Only GraphQL exposes isResolved / isOutdated. Thread
#                 resolution is how you tell "reviewer raised it and it was
#                 settled" from "merged with it still open" — on one PR, all 7
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
# too long". A +13k-line PR hit this on the first real run.
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

# An empty result from a FAILED fetch and an empty result from a PR with
# nothing to report are the same JSON. This artifact publishes a judgement
# about a named person, so "no review threads" must never be manufactured by a
# permissions error. Record the failure and let the caller disclose it.
FAILED_FETCHES=""
fetch_failed() {
  echo "WARNING: could not fetch $1 -- emitting an empty set. Any conclusion" >&2
  echo "         that depends on it is unsupported and must say so." >&2
  FAILED_FETCHES="$FAILED_FETCHES $1"
  echo '[]' > "$2"
}

# Who is a bot, according to GitHub rather than a name list. `gh pr view
# --json reviews` gives only author.login and strips the [bot] suffix, so the
# authoritative account type has to come from REST.
gh api "repos/$REPO/pulls/$NUM/reviews?per_page=100" --paginate --slurp \
  > "$TMP/reviews-pages.json" || fetch_failed reviews "$TMP/reviews-pages.json"
jq '[.[][]] | map({key: .user.login, value: .user.type}) | from_entries' \
  "$TMP/reviews-pages.json" > "$TMP/accounts.json"
jq --slurpfile pages "$TMP/reviews-pages.json" \
  '.reviews = [$pages[0][][] | {author: {login: (.user.login | rtrimstr("[bot]"))}, state, body,
    submittedAt: .submitted_at, url: .html_url}]' "$TMP/pr.json" > "$TMP/pr-next.json"
mv "$TMP/pr-next.json" "$TMP/pr.json"

gh api graphql -f query='
query($o:String!,$r:String!,$n:Int!,$endCursor:String){
  repository(owner:$o,name:$r){ pullRequest(number:$n){
    reviewThreads(first:100,after:$endCursor){
      pageInfo{hasNextPage endCursor}
      nodes{
        id isResolved isOutdated isCollapsed
        comments(first:100){
          totalCount
          nodes{ author{login} createdAt path line body url }
        }
      }
    }
  }}
}' -F o="$OWNER" -F r="$NAME" -F n="$NUM" \
  --paginate --slurp > "$TMP/thread-pages.json" \
  || fetch_failed threads "$TMP/thread-pages.json"
jq '[.[] | .data.repository.pullRequest.reviewThreads.nodes[]]' \
  "$TMP/thread-pages.json" > "$TMP/threads.json"

# Each nested connection has its own cursor; the outer paginator cannot advance it.
jq -r '.[] | select(.comments.totalCount > (.comments.nodes | length)) | .id' "$TMP/threads.json" > "$TMP/thread-ids"
while IFS= read -r id; do
  if gh api graphql -f query='
query($id:ID!,$endCursor:String){
  node(id:$id){ ... on PullRequestReviewThread {
    comments(first:100,after:$endCursor){
      pageInfo{hasNextPage endCursor}
      nodes{ author{login} createdAt path line body url }
    }
  }}
}' -f id="$id" --paginate --slurp > "$TMP/comment-pages.json"; then
    jq --arg id "$id" --slurpfile pages "$TMP/comment-pages.json" \
      'map(if .id == $id then .comments = {nodes: [$pages[0][] | .data.node.comments.nodes[]]} else . end)' \
      "$TMP/threads.json" > "$TMP/threads-next.json"
    mv "$TMP/threads-next.json" "$TMP/threads.json"
  else
    fetch_failed "thread-comments:$id" "$TMP/comment-pages.json"
  fi
done < "$TMP/thread-ids"

gh api "repos/$REPO/issues/$NUM/timeline?per_page=100" --paginate --slurp \
  > "$TMP/timeline-pages.json" || fetch_failed timeline "$TMP/timeline-pages.json"
jq '[.[][] | {event, at: (.created_at // .submitted_at // .committed_at // .author.date // .committer.date),
                actor: (.actor.login // .user.login // .author.name // null),
                state, label: .label.name,
                sha: (.sha // .commit_id),
                message: (.message // null),
                ref: (.source.issue.number // null)}]' "$TMP/timeline-pages.json" > "$TMP/timeline.json"

# gh pr view may cap its connections. Compare returned rows with forge totals
# rather than treating a capped collection as a complete personnel record.
gh api graphql -f query='
query($o:String!,$r:String!,$n:Int!){
  repository(owner:$o,name:$r){ pullRequest(number:$n){
    comments{totalCount} commits{totalCount} files{totalCount}
  }}
}' -F o="$OWNER" -F r="$NAME" -F n="$NUM" \
  --jq '.data.repository.pullRequest' > "$TMP/counts.json" \
  || fetch_failed collection-counts "$TMP/counts.json"
if ! jq -e 'type == "object" and ([.comments.totalCount, .commits.totalCount, .files.totalCount] | all(type == "number"))' \
  "$TMP/counts.json" >/dev/null; then
  if [[ " $FAILED_FETCHES " != *" collection-counts "* ]]; then
    fetch_failed collection-counts "$TMP/counts.json"
  fi
fi
jq -n --slurpfile pr "$TMP/pr.json" --slurpfile counts "$TMP/counts.json" \
  '["comments", "commits", "files"] | map(. as $key |
    select(($counts[0] | type) == "object") |
    select(($pr[0][$key] | length) < $counts[0][$key].totalCount))' > "$TMP/truncated.json"

# Per-commit CI history. Bounded to 40 commits: beyond that the pattern is
# sampled, not a claim about the remaining commits.
if [ "$(jq '.commits | length' "$TMP/pr.json")" -gt 40 ]; then
  jq '. + ["check-runs:commits-after-40"]' "$TMP/truncated.json" > "$TMP/truncated-next.json"
  mv "$TMP/truncated-next.json" "$TMP/truncated.json"
fi
jq -r '.commits[:40][].oid' "$TMP/pr.json" > "$TMP/shas"
: > "$TMP/checks.jsonl"
while IFS= read -r sha; do
  if gh api "repos/$REPO/commits/$sha/check-runs?per_page=100&filter=all" --paginate --slurp \
    > "$TMP/check-pages.json"; then
    jq --arg sha "$sha" '{sha: $sha, runs: [.[] | .check_runs[] | {name, conclusion, status}]}' \
      "$TMP/check-pages.json" >> "$TMP/checks.jsonl"
  else
    fetch_failed "check-runs:$sha" "$TMP/check-pages.json"
  fi
done < "$TMP/shas"
jq -s '.' "$TMP/checks.jsonl" > "$TMP/checks.json"

jq -n \
  --slurpfile pr       "$TMP/pr.json" \
  --slurpfile threads  "$TMP/threads.json" \
  --slurpfile timeline "$TMP/timeline.json" \
  --slurpfile checks   "$TMP/checks.json" \
  --slurpfile accounts "$TMP/accounts.json" \
  --slurpfile truncated "$TMP/truncated.json" \
  --arg failed "$FAILED_FETCHES" \
  '{pr: $pr[0], threads: $threads[0], timeline: $timeline[0], checkRuns: $checks[0],
    accountTypes: $accounts[0],
    truncatedSources: $truncated[0],
    failedFetches: ($failed | split(" ") | map(select(length > 0)))}'
