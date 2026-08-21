#!/usr/bin/env bash
# Gather the raw material for a release brief, and say whether it is live.
#
# Prints four blocks:
#   1. Ship state  — whether the integration branch holds anything production does not
#   2. Merged PRs  — pull requests merged inside the window, with target branch
#   3. Commits     — non-merge commits in the window
#   4. Tracker IDs — candidate issue identifiers harvested from all of the above
#
# The ship-state check compares trees rather than commit ancestry, because a
# squash or rebase merge rewrites hashes and makes released work look unmerged.
#
# Usage:
#   shipped-in-window.sh --since 2026-08-17 [--until 2026-08-21] \
#                        [--production master] [--integration staging] \
#                        [--remote origin]
#
# Requires: git. Uses gh for the pull request block when available.

set -euo pipefail

since=""; until_date=""; production=""; integration=""; remote="origin"

while [ $# -gt 0 ]; do
  case "$1" in
    --since)       since="$2"; shift 2 ;;
    --until)       until_date="$2"; shift 2 ;;
    --production)  production="$2"; shift 2 ;;
    --integration) integration="$2"; shift 2 ;;
    --remote)      remote="$2"; shift 2 ;;
    -h|--help)     sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

[ -n "$since" ] || { echo "error: --since is required (YYYY-MM-DD)" >&2; exit 2; }
git rev-parse --git-dir >/dev/null 2>&1 || { echo "error: not a git repository" >&2; exit 2; }

# Resolve branch names when not supplied. These are guesses; the brief should
# confirm the real production branch with whoever owns the deploy.
have_branch() { git show-ref --verify --quiet "refs/remotes/$remote/$1"; }

if [ -z "$production" ]; then
  for candidate in master main production prod; do
    if have_branch "$candidate"; then production="$candidate"; break; fi
  done
fi
if [ -z "$integration" ]; then
  for candidate in staging develop dev integration; do
    if have_branch "$candidate"; then integration="$candidate"; break; fi
  done
fi

rule() { printf '\n%s\n%s\n' "$1" "$(printf '%*s' "${#1}" '' | tr ' ' '-')"; }

git fetch --quiet "$remote" ${production:+"$production"} ${integration:+"$integration"} 2>/dev/null || true

rule "SHIP STATE"
if [ -z "$production" ]; then
  echo "No production branch found or supplied. Pass --production."
elif [ -z "$integration" ] || [ "$integration" = "$production" ]; then
  echo "Single-branch repository: '$production' is production."
  echo "A merge into it is a release, so there is no queue to report."
  echo "Confirm the deploy itself succeeded before calling anything live."
else
  drift=$(git diff --stat "$remote/$production" "$remote/$integration" || true)
  if [ -z "$drift" ]; then
    echo "IDENTICAL: '$integration' and '$production' hold the same content."
    echo "Nothing is queued. Everything merged in the window has been promoted."
  else
    echo "DIVERGED: '$integration' holds content '$production' does not."
    echo "Split the brief into what is live and what is queued."
    echo
    echo "$drift" | tail -25
  fi
fi
echo
echo "Merged is not deployed. Check the deploy platform and probe the live host"
echo "before writing that anything is live."

window_args=(--since "$since")
[ -n "$until_date" ] && window_args+=(--until "$until_date")

pr_titles=""
rule "MERGED PULL REQUESTS"
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  # gh embeds its own jq and does not accept --arg, so the window is
  # interpolated into the filter text.
  upper="${until_date:-9999-12-31}"
  jq_filter=".[] | select(.mergedAt[0:10] >= \"$since\") | select(.mergedAt[0:10] <= \"$upper\")
             | \"#\\(.number)|\\(.mergedAt[0:10])|\\(.baseRefName)|\\(.title)\""
  if pr_out=$(gh pr list --state merged --limit 200 \
        --json number,title,mergedAt,baseRefName \
        --jq "$jq_filter" 2>/dev/null); then
    if [ -n "$pr_out" ]; then
      echo "$pr_out" | sort -t'|' -k2,2
      echo
      echo "count: $(echo "$pr_out" | grep -c .)"
      pr_titles="$pr_out"
    else
      echo "(none merged in this window)"
    fi
  else
    echo "(gh could not list pull requests — no remote host, or no access)"
  fi
else
  echo "(gh unavailable or not authenticated; skipping)"
fi

rule "COMMITS IN WINDOW"
# Prefer the integration branch: a squash-merge repository keeps one commit per
# release on production, so its log hides the individual changes.
if [ -n "$integration" ] && have_branch "$integration"; then
  commit_ref="$remote/$integration"
elif [ -n "$production" ] && have_branch "$production"; then
  commit_ref="$remote/$production"
else
  commit_ref="HEAD"
fi
echo "(walking $commit_ref)"
commits=$(git log "${window_args[@]}" --no-merges --date=short \
            --pretty='%h %ad %s' "$commit_ref" 2>/dev/null || true)
if [ -n "$commits" ]; then
  echo "$commits"
  echo
  echo "count: $(echo "$commits" | grep -c .)"
else
  echo "(none)"
fi

rule "CANDIDATE TRACKER IDS"
ids=$(printf '%s\n%s\n' "$commits" "$pr_titles" \
      | grep -oE '\b[A-Z][A-Z0-9]{1,5}-[0-9]+\b' \
      | sort -u -V 2>/dev/null || true)
if [ -n "$ids" ]; then
  echo "$ids" | tr '\n' ' '; echo
  echo
  echo "count: $(echo "$ids" | grep -c .)"
  echo
  echo "These are pattern matches, not confirmed issues. Read each one in the"
  echo "tracker: take its title, priority, type, and status from there, and drop"
  echo "any that turn out to be something else (a standard name, a version)."
else
  echo "(no identifiers matched; harvest them from pull request bodies instead)"
fi
