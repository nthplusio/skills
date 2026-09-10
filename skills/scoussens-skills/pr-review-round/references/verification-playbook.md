# Verification playbook

Techniques for finding the bugs that survive CI and survive an automated
reviewer. Each one is stated as a general check, with the concrete case that
motivated it, because the example is what makes the check memorable and the
generalisation is what makes it useful.

Read this when reviewing anything in the DATA, AUTH, API, or INFRA risk tiers.
For WEB and DOCS, techniques 1, 2, 5, and 6 are usually enough.

## Contents

1. [Staleness before substance](#1-staleness-before-substance)
2. [Verify, never relay](#2-verify-never-relay)
3. [Green CI is not evidence](#3-green-ci-is-not-evidence)
4. [Silent reverts](#4-silent-reverts)
5. [Body versus diff](#5-body-versus-diff)
6. [Check the other direction](#6-check-the-other-direction)
7. [Reachability before severity](#7-reachability-before-severity)
8. [Renaming persisted state is a migration](#8-renaming-persisted-state-is-a-migration)
9. [Deleted safety comments](#9-deleted-safety-comments)
10. [Proving code is dead](#10-proving-code-is-dead)
11. [The author's own admissions](#11-the-authors-own-admissions)
12. [Two branches, one merged result](#12-two-branches-one-merged-result)

---

## 1. Staleness before substance

Do this first, always. `stale_sweep.py` reports it for the whole queue.

Every review — human as well as bot — carries `commit_id`, the SHA it was
submitted against. There is no unmarked category and nothing has to be judged
by date alone.

**Exclude base history from the range, or the count is fiction.** `--no-merges`
drops the merge commit but keeps every base commit reachable through its second
parent:

```bash
git fetch -q origin <base>
git log --oneline --no-merges <reviewed-sha>..<head-sha> --not origin/<base>
```

**The tell:** on one PR the unfiltered range showed 37 commits and the filtered
range showed **zero** — the author had merged the base and addressed nothing.
Without the filter that reads as three weeks of work.

Author commits and base merges mean opposite things. Author work may have fixed
the finding, so read it first. A branch carrying only base merges has addressed
nothing, however long the raw range looks.

When a fix has landed, verify it at head and then **dismiss with a message that
names the SHA and what you confirmed**. A bare dismissal tells the author
nothing; they cannot distinguish "I checked your fix" from "I got bored".

## 2. Verify, never relay

An automated finding is a lead, not a conclusion. Open the file at the PR's head
and confirm it:

```bash
git show <head-sha>:path/to/file.py | sed -n '100,140p'
```

Two failure modes matter, and the second is the dangerous one:

- **The finding is fixed.** Covered above.
- **The finding is real but mis-severed.** One review described three handlers
  as "bypassing the service layer", which was true, and framed it as an auth
  gap, which was false — authentication was global middleware, so the routes
  were authenticated; the missing dependency only meant the data was not
  user-scoped, which was the PR's stated design. Relaying that unexamined would
  have sent the author chasing a security hole that did not exist.

Getting severity right is most of what makes a review trustworthy. Overstating
one finding costs you credibility on the next nine.

## 3. Green CI is not evidence

Ask what the tests actually enforce, not whether they pass.

A PR added `NOT NULL` to a column while a writer still bound `None` for it.
Every test passed, because the test double was "a minimal, state-driven cursor
stand-in" with no constraint enforcement — and one test asserted the broken
value, pinning the bug in place. On a real database the write fails outright.

The general check: when a PR changes a **constraint, type, schema, or contract**,
find the test that would catch a violation and confirm it *could*. Fakes,
in-memory doubles, and mocks enforce nothing by default.

**A changed test file is not coverage.** Run `test_reach.py <n>`: it extracts
the symbols the PR added and greps the test tree for each. Zero hits is a
question, not a verdict — a private helper covered through its caller is fine.

**The tell:** a PR added one test named after the function it was fixing, which
built its own dict, filtered it with a comprehension written in the test body,
and asserted on that. It imported neither the function nor its module. Six new
symbols, zero test references, and it passed with all five changed files
reverted. Read the assertion, not the filename.

The same logic applies to a red check. A failing `review` or `lint` job is
sometimes the tooling erroring out rather than a finding — one 102-file PR was
red because the automated reviewer hit its own turn limit and never posted.
Read the job before attributing the failure to the author.

## 4. Silent reverts

The highest-value class of finding, and invisible in a diff read in isolation,
because the diff looks like ordinary new code.

For any file a PR substantially rewrites, compare against the base branch and
read that file's recent history:

```bash
git show origin/<base>:path/to/file.py | wc -l     # how big is it on base?
git log --oneline -8 origin/<base> -- path/to/file.py
```

Two real cases:

- A branch cut before a consolidation landed replaced a 45-line shim with a
  176-line local reimplementation of logic that now lived in a shared package.
  **The tell: the PR touched zero files in that package.** A genuine migration
  away from a package edits the package. Only an accidental undo does not.
- A styling PR restored a class string verbatim that a named commit
  ("adopt the design system's token layer and retire one-off chrome") had
  deliberately removed. **The tell: `git log` on that file surfaced a commit
  whose message described removing exactly what the PR was adding back.**

Both were long-lived branches. Suspect this whenever a branch predates work that
landed on the base branch in the same area, and always when a PR's stated purpose
has nothing to do with the file it is rewriting.

## 5. Body versus diff

Read the PR description as a claim to be tested. The gap between what it says
and what the diff does is reliably interesting.

- One PR described a bug ("toggling Public does not reliably refetch") and then
  fixed it by **deleting the toggle entirely** — a user-facing capability
  removed, never mentioned. That is not necessarily wrong, but it has to be a
  stated decision rather than a side effect of a PR about something else.
- Another stated plainly that a phase was "the regression gate — don't move on
  until X still works", and that phase was the one place behaviour actually
  changed for existing users.

Where a linked ticket has acceptance criteria, walk them against the code. The
criterion a PR quietly fails is usually the one it was filed for.

## 6. Check the other direction

Whenever a PR introduces an allowlist, enum, map, or set, two questions matter
and reviewers reliably ask only the first.

1. Does every entry resolve? (Are the listed things real?)
2. **What real thing is missing from the list?**

Both directions produced findings in the same round:

- An icon allowlist: all 26 entries had real files, *and* the two names omitted
  genuinely had no asset — so the fallback was a fix, not a downgrade. Checking
  both directions is what let the review say "correct" with confidence instead
  of "looks fine".
- A `chip` component: the change flipped the **default** from transparent to
  white and added an opt-out flag to 8 call sites. There were 22 call sites. The
  14 untouched ones gained the exact artifact the PR existed to remove. Found by
  enumerating every call site and checking which carried the new flag.

Enumerate call sites mechanically rather than trusting the diff to show them
all — the diff only shows what the author remembered to change.

## 7. Reachability before severity

Before calling something blocking, establish that it can actually happen, and
whether it is new.

A hardening PR left an empty ID list rendering `IN ()`, which is invalid SQL.
Worth reporting. But: the previous interpolated version produced the same
invalid SQL from the same input, so it was not a regression; and the dispatch
site had no validation, so it was reachable. That combination — reachable but
pre-existing — makes it a clear follow-up rather than a merge blocker, and
saying so accurately is what keeps the PR moving.

Sibling code is the best evidence here. If three neighbouring functions guard an
input and the new one does not, that asymmetry is the finding.

This check is not only for other people's findings — apply it to your own before
you post, and hardest of all to the ones that feel most damning. See
[technique 8](#8-renaming-persisted-state-is-a-migration) for the case where
skipping it turned a real finding into an overstated one.

## 8. Renaming persisted state is a migration

A rename that is mechanical in code is a data migration in the database. When a
PR renames a field, check whether that field is **persisted** — a column, a
document key, an index name, a queue message, a cache key, a wire contract.

One PR renamed an identifier across 35 files, cleanly and with tests. It also
renamed the MongoDB field and its index, with no migration and no dual-read, so
existing rows kept the old key.

### Then ask which reads actually use it — before you claim anything is lost

This is technique 7 applied to your own finding, and skipping it is the mistake
I have actually made rather than a hypothetical. On that same PR I wrote that
historical events would become unreachable. That was wrong, and a five-line
check would have caught it: the main read path narrows by conversation id and
**deliberately never filters on the renamed anchor at all**, so renaming the
anchor could not strand it. What genuinely broke was the much narrower set of
reads that *do* filter on it — one adoption helper and the session scope.

So the finding was real and the severity was inflated, which is the worse of the
two errors: the author has to argue you down instead of fixing something.

Before describing any data as unreachable, enumerate the readers and check which
of them actually constrain on the renamed field:

```bash
git grep -n '<new-field-name>' <head-sha> -- <src-dirs> | grep -v test
```

Read each hit and ask: does this query *filter* on the field, or merely carry it?
A field that is written and returned but never used as a predicate can be
renamed with no read-path consequence at all. Scope the blast radius to the
predicates, then state that scope explicitly — "the adoption helper and
session-scoped reads" lands; "all historical events" gets you corrected.

The checks for the migration itself:

```bash
gh pr view <n> --json files -q '.files[].path' | grep -iE 'migrat|backfill'
git grep -n '<old-field-name>' <head-sha> -- <src-dirs> | grep -v test
```

No migration and no surviving reads of the old name together mean the data is
orphaned. Also look for the **old index being left behind** — adding the new one
without dropping the old is easy to miss and costs writes forever.

Where a schema-version guard rejects old messages, ask what happens to clients
mid-session. Browsers hold cached bundles; a hard version cut rejects their
frames until they refresh.

## 9. Deleted safety comments

A PR that removes a comment explaining why something was *not* done deserves a
close look. The comment is usually the only record of the reasoning.

This cuts both ways, and assuming the worst is a mistake. One PR deleted a long
comment arguing that binding a client-supplied ID at connect time was unsafe
(it would let a first-writer claim pre-empt the real owner). That looks alarming
— but the author had replaced it with a real gate: the ownership check was a
pure read, and the boot path used the supplied ID verbatim rather than minting a
new one, so the two could never diverge. The deletion was correct.

Read the deleted reasoning, then check whether the new code actually addresses
it. Approving became straightforward once the mechanism was traced; so would
blocking have been, had it not held.

## 10. Proving code is dead

For a deletion, the whole review is "is this actually unreferenced?" — and the
mistake is grepping only the language you are looking at.

String-keyed dispatchers (`elif function == "update_mapping"`) can be called
from a frontend, a DAG, a webhook, or an external integration. Search the entire
repository, not `--include=*.py`:

```bash
git grep -n '<symbol>' <head-sha>              # everything, all languages
git grep -n '<symbol>' <head-sha> -- '*.ts' '*.tsx' '*.json' '*.yml'
```

Remaining hits in immutable history directories (`docs/history/`, changelogs)
are correct to leave alone. Hits in a module docstring documenting the removal
are a good sign. Hits anywhere executable are the finding.

Worth noting when a deletion also retires unsafe surface: four builders removed
in one PR were all value-interpolated SQL, so the deletion moved a hardening
ratchet by four without anyone writing a bind. Deleting dead code is often the
cheapest way to satisfy a security backlog — say so, because it encourages more
of it.

## 11. The author's own admissions

Take the PR body's self-assessment seriously as a gate.

One PR read "Live verification pending — the views need a manual check with the
flag on" and "On-by-default is ahead of the 'parity before default' guardrail",
while flipping the default renderer for three screens. CI was green and both
prior findings were properly fixed. The author had already identified the
blocker; the review's job was to hold the line they had drawn, not to discover
something new.

A runtime off-switch is not a substitute for verification. It only helps once
someone notices, and the failure modes that need verifying are the quiet ones.

## 12. Two branches, one merged result

A conflict is not only a textual collision. When two branches change the same
area, the interesting bug can exist in **neither branch** and appear only once
they are merged — so no amount of reading either diff finds it.

For every conflicting file, read both sides:

```bash
git diff $(git merge-base origin/<base> <head>) origin/<base> -- <path>
git diff $(git merge-base origin/<base> <head>) <head>       -- <path>
git log --oneline <merge-base>..origin/<base> -- <path>   # who landed the other side
```

Then ask the question a conflict marker cannot: **do these two changes compose?**

**The tell:** both sides added an independent controller for the same piece of
state. The base branch added a manual toggle writing `childrenCollapsed`; the PR
added an effect that *also* wrote it, with the same field in its dependency
array. Each was correct alone. Merged, the effect re-fires on the toggle's write
and reverts it, so the button silently stops working. Two writers for one piece
of state is the shape to look for.

`queue.py` prints the files touched by more than one open PR, which is the same
hazard before the conflict exists.
