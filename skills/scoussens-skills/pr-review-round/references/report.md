# Reporting the round

Two deliverables. The terminal summary is what gets read now; the artifact is
what gets shared. Build both from `round_report.py`'s JSON, not from memory —
by report time the merged PRs have left `queue.py`'s list and the bodies you
posted are hundreds of lines back.

`round_report.py` bounds the round from the ledger's previous `ended_at`. A
fixed clock window is wrong in both directions: too wide and it reports PRs that
landed before the round opened, too narrow and it drops a long round's earliest
merges.

## Terminal summary

Group by outcome, because that is the question being asked. Lead with what
landed. One line per PR naming the *finding* — "silently reverts the Phase F
consolidation" is information; "12 files changed" is not.

```markdown
## Merged — N
| PR | Reviewed | What |
| [#NNNN](url) | 16:04 | one-line statement |

## Queued, not landed — N
- **[#NNNN](url)** (16:12) — approved; in the merge queue, not yet on <base>.

## Approved, on the author — N
- **[#NNNN](url)** (16:19) — approved; needs a base merge (conflicting).

## Changes requested — N
(most consequential finding first, not PR order)
- **[#NNNN](url)** (16:31) — one-line statement of the actual defect.
```

Link every PR number and give every row the time its review was submitted;
`round_report.py` returns both as `url` and `reviewed_at`. Terminal clients make
markdown links clickable, so a linked number costs nothing.

**Say plainly what is queued versus merged.** A PR in a merge queue has not
landed, and reporting it as merged is the one inaccuracy that will bite. With
auto-merge, approval enqueues immediately — so a PR can be queued seconds after
you approve and still take half an hour to land.

## HTML artifact

Load the `artifact-design` skill first — required for any artifact, and it
calibrates how much design the page warrants.

The page answers, for a teammate who was not there: what came in, what landed,
what is blocked and on whose desk, what the notable findings were.

- Header: base branch, date, counts (reviewed / merged / blocked).
- A row per PR: **PR number linked**, author, risk tier, verdict, blocker,
  one-line finding, **the review's timestamp**.
- **Each row expands into the review you left**, collapsed by default.
- **A teach-me button per row** (below).
- A section for the substantive findings, each with `file:line` and the
  scenario — the reusable part, and the reason anyone opens the page.
- A short synthesis: patterns worth acting on, gates that failed to catch things.

### The four per-PR affordances

**Link.** A verdict a reader cannot act on is one they defer.

**Review timestamp.** The page's own honesty check. A round takes an hour and
the queue moves underneath it, so "reviewed 16:04" is what lets a reader tell a
verdict formed *before* a merge reshuffled the branch from one formed after.
Render a real time, not "recently".

**Expandable review body.** The table states conclusions; the disclosure carries
the argument. Two rules:

- **Paste, never paraphrase.** A summarised review reads as authoritative while
  being unfalsifiable, and the reader cannot know the two diverged.
- **Render the Markdown.** A review body is `##` headings, `**bold**`, backticked
  `file.py:123`, fenced diffs, tables. A `<pre>` shows all of that as literal
  `**` and ``` ``` ```, which is what makes a disclosure look broken enough that
  nobody opens a second one. Use `scripts/md_to_html.py` at **build time** —
  the Artifact CSP blocks external scripts, so a CDN parser silently fails in
  the viewer's browser where you will not see it:

  ```python
  sys.path.insert(0, "~/.claude/skills/pr-review-round/scripts")
  from md_to_html import render as md
  f'<div class="md">{md(review["body"])}</div>'
  ```

- **Include comments too.** Some PRs get a comment rather than a review — a
  conflict note, a status check. Those rows have `reviewed_at: null`; say
  "commented" rather than implying a review happened.

Three CSS details that bite once bodies are rendered:

- **Scope the styles** under `.md h4`, `.md pre`. A bare `h4 {}` rule lets a
  review body restyle the page. `md_to_html` demotes review `##` to `<h4>` for
  the same reason.
- **Reset `code` inside `pre`** — `.md pre code { background:none; border:0;
  padding:0 }`, or a fenced block draws a pill around every line.
- **Cap the height** with `max-height` + `overflow-y: auto`, and give tables and
  code blocks their own `overflow-x: auto` container.

**Teach-me prompt.** The other three point backwards, at what was decided. This
one points forward, at the code. A round report is read by people who own two or
three of its rows, and their next question after "why is this blocked" is "what
do I have to understand to unblock it".

Keep favicon and title stable across rounds so redeploys stay recognisable.

## The teach-me button

A round report already knows the verdict, the head SHA, and the open findings,
so the prompt can ask for a deep-dive *shaped by the review* rather than a
generic walkthrough. On a merged PR the reader wants the mechanism; on a blocked
one they are usually the author, and their real question is what to fix.

```
/pr-teacher — build an interactive teaching artifact for
<owner/repo> PR #<N> — "<title>".

  Author: <author> · Risk tier: <tier> · <stats>
  Reviewed at <sha> on <date>: <VERDICT>
  Open findings: <one line per blocking item, file:line where the review had one>

Cover the mechanism first, then use the findings above as the spine of the
"what would break" section — I want to understand why each one is a problem in
this code, not just that it was flagged.

If `/pr-teacher` isn't installed: read the PR with `gh pr view <N> --repo
<owner/repo>` and `gh pr diff <N>` (that API caps at 20,000 diff lines — above
it, fetch the branch and use `git diff $(git merge-base origin/<base> <head>)
<head>`), read the changed files and the code around them, then publish one
self-contained HTML artifact covering the problem it solved, a map of where each
changed file sits and why, how the mechanism works (mermaid where a diagram
beats prose), before/after on the decisive hunks, the open findings above traced
to the code that causes them, and 6-10 self-check questions with revealable
answers grounded in the real code. Prefer real paths and line numbers over
illustrative ones.
```

**Build it from data attributes, not duplicated markup.** Put the row's identity
on the `<article>` (`data-num`, `data-repo`, `data-title`, `data-author`,
`data-tier`, `data-stats`, `data-sha`, `data-date`, `data-verdict`, and
`data-findings` as a `|`-delimited list) and have one function assemble the
prompt. The visible row and the copied prompt then cannot drift. **Skip the
`Open findings:` line when the attribute is empty** — an empty label reads as a
bug.

### Copying reliably

Artifacts render in an iframe that does **not** delegate `clipboard-write`. In
that frame `window.isSecureContext` is `true` and `navigator.clipboard` exists,
so a capability check passes — and then `writeText()` rejects with
`NotAllowedError`. Meanwhile `document.execCommand('copy')` in the same frame,
in the same click, returns `true`.

So **chain the fallback on rejection, never on feature detection.** This is the
failure that shipped once already:

```js
// WRONG — the guard passes, writeText then rejects, and the execCommand path
// is unreachable dead code.
if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(t);
return execCommandCopy(t);

// RIGHT — outcome decides, not capability.
function copyText(t) {
  return Promise.resolve()
    .then(function () {
      if (!navigator.clipboard) throw new Error('no clipboard api');
      return navigator.clipboard.writeText(t);
    })
    .catch(function () { return execCommandCopy(t); });  // runs on NotAllowedError too
}
```

`execCommand` is itself removed-on-paper and can be disabled, so give the reader
a real third resort: **render the prompt into a selectable element** — a
collapsed `<details>` per row that the handler fills and opens. Do not tell
anyone to "select the text manually" unless the text is on the page; a prompt
that exists only inside `buildPrompt()` at click time cannot be selected.

Say what actually happened in each of the three cases, and never report
"Copied" on a write you did not confirm.
