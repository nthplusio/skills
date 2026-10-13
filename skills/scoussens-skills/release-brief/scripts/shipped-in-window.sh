#!/usr/bin/env bash
# Gather the raw material for a release brief, and say whether it is live.
#
# Two modes, matching the two kinds of brief:
#
#   --since <date>     PERIOD  — what shipped across a stretch of calendar time
#   --release <ref>    RELEASE — what one named release contains
#
# Prints:
#   1. Ship state  — whether the integration branch holds anything production does not
#   2. Releases    — the promotion sequence, one entry per release
#   3. Pull requests — split into product work and promotions, which are not changes
#   4. Commits     — non-merge commits, walked on the branch that holds the history
#   5. Tracker IDs — candidate issue identifiers harvested from the above
#
# The ship-state check compares trees rather than commit ancestry, because a
# squash or rebase merge rewrites hashes and makes released work look unmerged.
#
# Usage:
#   shipped-in-window.sh --since 2026-01-12 [--until 2026-01-16] \
#                        [--production master] [--integration staging] [--remote origin]
#   shipped-in-window.sh --release v2.3.0 [--production main]
#
# Requires: git. Uses gh for the pull request block when available.

set -euo pipefail

since=""; until_date=""; release=""; production=""; integration=""; remote="origin"

while [ $# -gt 0 ]; do
  case "$1" in
    --since)       since="$2"; shift 2 ;;
    --until)       until_date="$2"; shift 2 ;;
    --release)     release="$2"; shift 2 ;;
    --production)  production="$2"; shift 2 ;;
    --integration) integration="$2"; shift 2 ;;
    --remote)      remote="$2"; shift 2 ;;
    -h|--help)     sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$since" ] && [ -z "$release" ]; then
  echo "error: pass --since <date> for a period, or --release <ref> for one release" >&2
  exit 2
fi
git rev-parse --git-dir >/dev/null 2>&1 || { echo "error: not a git repository" >&2; exit 2; }

have_branch() { git show-ref --verify --quiet "refs/remotes/$remote/$1"; }

# Resolve branch names when not supplied. These are guesses; confirm the real
# production branch with whoever owns the deploy.
if [ -z "$production" ]; then
  for c in master main production prod; do have_branch "$c" && { production="$c"; break; }; done
fi
if [ -z "$integration" ]; then
  for c in staging develop dev integration; do have_branch "$c" && { integration="$c"; break; }; done
fi

rule() { printf '\n%s\n%s\n' "$1" "$(printf '%*s' "${#1}" '' | tr ' ' '-')"; }

git fetch --quiet --tags "$remote" ${production:+"$production"} ${integration:+"$integration"} 2>/dev/null || true

# ── 1. Ship state ───────────────────────────────────────────────────────────
rule "SHIP STATE"
if [ -z "$production" ]; then
  echo "No production branch found or supplied. Pass --production."
elif [ -z "$integration" ] || [ "$integration" = "$production" ]; then
  echo "Single-branch repository: '$production' is production."
  echo "A merge into it is a release, so there is no queue to report."
else
  drift=$(git diff --stat "$remote/$production" "$remote/$integration" || true)
  if [ -z "$drift" ]; then
    echo "IDENTICAL: '$integration' and '$production' hold the same content."
    echo "Nothing is queued."
  else
    echo "DIVERGED: '$integration' holds content '$production' does not."
    echo "Split the brief into what is live and what is queued."
    echo
    echo "$drift" | tail -15
  fi
fi
echo
echo "Merged is not deployed. Check the deploy platform and probe the live host"
echo "before writing that anything is live."

# ── 2. Release boundaries ───────────────────────────────────────────────────
# --first-parent on the production branch gives one entry per promotion, in
# order. Trunk-based repositories have no such boundary: there the release is
# the deploy, so read the sequence from the deploy platform instead.
rule "RELEASES"
if [ -n "$production" ] && have_branch "$production"; then
  # Deliberately NOT date-filtered. git interprets --since in local time while
  # a forge API reports merge times in UTC, so a promotion at 21:00-05:00 is
  # "yesterday" to git and "today" to the API. Filtering here silently drops
  # releases across that boundary. Timestamps are printed in full ISO form so
  # the offset is visible; match them to the window yourself.
  releases=$(git log --first-parent --pretty='%h %cI %s' "$remote/$production" 2>/dev/null | head -15 || true)
  if [ -n "$releases" ]; then
    echo "$releases"
    echo
    echo "Each entry is one promotion to production, newest first, NOT filtered to"
    echo "the window — compare the timestamps yourself, in one timezone. For a"
    echo "release brief, take the range between two consecutive entries, or"
    echo "<prev-tag>..<tag>."
  else
    echo "(no promotions in this window — work may be merged but not yet released)"
  fi
else
  echo "(no production branch resolved; pass --production)"
fi

# ── 3. Pull requests ────────────────────────────────────────────────────────
pr_work=""; pr_promo=""
rule "PULL REQUESTS"
if [ -n "$release" ]; then
  echo "(skipped in release mode — a release's contents come from its commit"
  echo " range, and the pull request numbers are in the commit subjects below."
  echo " Listing by date here would sweep every pull request ever merged.)"
elif command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  # Filter by merge date on the server. `--state merged --limit N` pages by
  # creation date, so filtering its output here would drop a long-lived pull
  # request that merged inside the window.
  window="merged:>=${since}T00:00:00Z"
  [ -n "$until_date" ] && window="merged:${since}T00:00:00Z..${until_date}T23:59:59Z"
  merged_into() {
    gh pr list --state merged ${1:+--base "$1"} --search "$window" --limit 300 \
      --json number,title,mergedAt,baseRefName,headRefName \
      --jq 'sort_by(.mergedAt) | .[] | "#\(.number)|\(.mergedAt[0:10])|\(.baseRefName)|\(.headRefName)|\(.title)"' \
      2>/dev/null
  }
  two_branch=""
  if [ -z "$production" ]; then
    work_label="Product work (no production branch resolved, so every base):"
    pr_work=$(merged_into "") || pr_failed=1
  elif [ -z "$integration" ] || [ "$integration" = "$production" ]; then
    work_label="Product work (merged to '$production'; each merge is also a release):"
    pr_work=$(merged_into "$production") || pr_failed=1
  else
    two_branch=1
    work_label="Product work (merged to '$integration'):"
    pr_work=$(merged_into "$integration") || pr_failed=1
    pr_promo=$(merged_into "$production") || pr_failed=1
  fi
  if [ -n "${pr_failed:-}" ]; then
    pr_work=""; pr_promo=""
    echo "(gh could not list pull requests — no remote host, or no access)"
  else
    echo "Lines read #number|merged|base|head|title."
    echo "$work_label"
    if [ -n "$pr_work" ]; then
      echo "$pr_work"
      echo "  count: $(echo "$pr_work" | grep -c .)"
    else
      echo "  (none)"
    fi
    if [ -n "$two_branch" ]; then
      echo
      echo "Promotions (merged to '$production') — these are releases, NOT changes."
      echo "Do not add them to the change count:"
      if [ -n "$pr_promo" ]; then
        echo "$pr_promo"
        echo "  count: $(echo "$pr_promo" | grep -c .)"
      else
        echo "  (none)"
      fi
      echo
      echo "Merge date is not release date. A change merged before this window may"
      echo "have gone live inside it, and one merged inside it may still be queued."
      echo "For a period brief, select by the promotion that carried it."
    fi
  fi
else
  echo "(gh unavailable or not authenticated; skipping)"
fi

# ── 4. Commits ──────────────────────────────────────────────────────────────
rule "COMMITS"
if [ -n "$release" ]; then
  # One release: the range from the previous first-parent entry up to this ref.
  prev=$(git rev-parse "$release^" 2>/dev/null || true)
  if [ -z "$prev" ]; then
    echo "error: could not resolve '$release'" >&2
  else
    echo "(contents of $release)"
    commits=$(git log --no-merges --date=short --pretty='%h %ad %s' "$prev..$release" 2>/dev/null || true)
  fi
else
  # A squash-merge repository keeps one commit per release on production, so
  # its log hides the work. Prefer the branch that holds the real history.
  if [ -n "$integration" ] && have_branch "$integration"; then ref="$remote/$integration"
  elif [ -n "$production" ] && have_branch "$production"; then ref="$remote/$production"
  else ref="HEAD"; fi
  echo "(walking $ref)"
  w=(--since "$since"); [ -n "$until_date" ] && w+=(--until "$until_date")
  commits=$(git log "${w[@]}" --no-merges --date=short --pretty='%h %ad %s' "$ref" 2>/dev/null || true)
fi
if [ -n "${commits:-}" ]; then
  echo "$commits"
  echo
  echo "count: $(echo "$commits" | grep -c .)"
else
  echo "(none)"
fi

# ── 5. Tracker IDs ──────────────────────────────────────────────────────────
rule "CANDIDATE TRACKER IDS"
# Branch names are often lowercase, so match without case and print uppercase.
# A version such as doorbell-0.1.1 is matched whole and then dropped.
ids=$(printf '%s\n%s\n' "${commits:-}" "$pr_work" \
      | grep -oiE '\b[a-z][a-z0-9]{1,9}-[0-9]{1,6}(\.[0-9]+)*\b' | grep -v '\.' \
      | tr '[:lower:]' '[:upper:]' | sort -u -V 2>/dev/null || true)
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
