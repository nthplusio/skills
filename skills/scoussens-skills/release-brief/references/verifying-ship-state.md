# Verifying ship state

A brief claims things are live. This is how to earn that claim.

## Contents

- [Why ancestry lies](#why-ancestry-lies)
- [Map the branch topology first](#map-the-branch-topology-first)
- [Merged is not deployed](#merged-is-not-deployed)
- [Dates disagree across tools](#dates-disagree-across-tools)
- [Confirming a web change reached the browser](#confirming-a-web-change-reached-the-browser)
- [Cherry-picks, reverts, and partial releases](#cherry-picks-reverts-and-partial-releases)
- [When you cannot verify](#when-you-cannot-verify)

## Why ancestry lies

`git log production..integration` answers "which commits are reachable from
`integration` but not from `production`". After a squash merge that question
stops matching the one you care about. Squashing replaces a branch's commits
with a single new commit holding their combined *content*; the originals are
never ancestors of the target, so they are reported as unmerged forever.

Rebase merges rewrite hashes and produce the same illusion. So do repositories
that release by copying a tree rather than merging.

Compare content:

```bash
git diff --stat origin/<production> origin/<integration>
```

Empty output means the branches are identical and nothing is queued. That is
the sentence a brief can rest on.

If the output is non-empty, read it before concluding anything. A handful of
changed files may be release-only scaffolding — a version bump, a lockfile —
rather than unreleased product work.

## Map the branch topology first

Ask which branch serves production rather than assuming a name. Common shapes:

| Shape | Production branch | What to compare |
| --- | --- | --- |
| Trunk-based | `main` / `master` | Nothing; a merge is a release |
| Two-stage | `master`, fed by `staging` | `master` against `staging` |
| Release branches | `release/*`, merged back | The active release branch against trunk |
| Tag-driven | Whatever the latest tag points at | `git diff <latest-tag> origin/main` |

`git worktree list` and the repository's own contributor documentation usually
settle it faster than guessing. In a two-stage repository, note that a pull
request merged into the integration branch is *not yet in production* — a
separate promotion merges it onward, and the brief has to distinguish the two.

## Merged is not deployed

A merge starts a pipeline; it does not finish one. Between merge and live
there may be a gated check suite, a queued build, a manual approval, or a
failed deploy nobody noticed.

Check the deployment surface the project actually uses — its platform CLI or
MCP server, its deploy workflow runs, or its status endpoint — and then probe
the running system:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://<production-host>/
```

Read a run's `conclusion` rather than trusting an exit code: some watch
commands exit `0` on a run that was cancelled.

## Dates disagree across tools

`git log --since` interprets a bare date in the machine's local timezone, while
a forge API reports merge times in UTC. A promotion made at 21:00−05:00 is
therefore *yesterday* to git and *today* to the API, and any date filter run
across that boundary drops it from one side silently.

This is not hypothetical. In one two-branch repository, three of the four
promotions inside a Monday-to-Friday window carried git timestamps of
`2026-08-16T21:00−05:00`, `21:59−05:00`, and `2026-08-17T00:45−05:00`. A
`--since 2026-08-17` filter returned one release; the forge reported four.

Two habits avoid it:

- **Print full ISO timestamps** (`%cI`) rather than `%ad`/`%cd` short dates, so
  the offset is visible and comparable.
- **Do not date-filter a release list.** Print the recent promotion sequence
  unfiltered and match it to the window yourself, in one timezone. You want the
  boundary immediately *before* the window anyway, to know where the first
  release in range begins.

Where an exact cutoff matters, give git an unambiguous instant —
`--since '2026-08-17T00:00:00Z'` — rather than a bare date.

## Confirming a web change reached the browser

For a front-end change, a green deploy is weaker evidence than it looks. Fetch
the page and confirm the built asset hashes changed. Modern builds also split
code by route, so page copy lives in a route chunk rather than the entry
bundle: grep the entry bundle for the route chunk's filename, fetch that chunk,
and search it for a string you added — and for the string you removed.

## Cherry-picks, reverts, and partial releases

- **Cherry-picks** put content in production under a different hash. The tree
  diff catches this correctly; the commit range does not.
- **Reverts** mean work merged inside the window is no longer live. Search the
  window for `Revert` and check whether anything you are about to describe was
  undone.
- **Partial releases** are the case most likely to embarrass a brief. When only
  some of the window reached production, split the page: what is live, then
  what is verified and queued, with the expected promotion named.

## When you cannot verify

Say so plainly, in the brief and in your reply. "Merged and awaiting the
Thursday release" is a useful sentence. "Live" when you did not check is the
one failure this whole document exists to prevent.
