---
name: business-rules-catalogue
description: >-
  Finds where a repository's business logic lives, derives the rules its code
  actually enforces, has a second reader check them, and delivers a tree
  explorer in which business owners mark each rule correct or wrong and export
  corrections for engineering. Load this only when the user explicitly asks for
  such a catalogue or its discovery — "derive the business rules", "catalogue
  the business logic", "where does our business logic live", "business rules
  review for the product team", "refresh the rules explorer". Do not load it to
  explain one function, review a pull request, or document an API; answer those
  directly instead.
---

# Business rules catalogue

A **rule** is one decision the code enforces: a validation, default,
derivation, match, precedence, state change, threshold, ordering, naming or
authorization, or a guarantee a user feels, such as what a re-run or a partial
failure does. Rules come from function bodies, query text, guards and
constants. Comments and documentation show only where intent and code
disagree. A wrong rule sends someone to "fix" correct code, so every rule cites
the line that enforces it, and a second reader re-checks a sample.

A run delivers:

- the **explorer**: a static app with a lifecycle map and a tree of area ›
  folder › module › rule, where business owners mark each rule Correct, Wrong
  or Unsure and export their corrections;
- the **research note**: Markdown citing every rule at the pinned commit;
- the **saved scope**: the confirmed areas and reader assignments, so the next
  run skips discovery.

Partition readers by file ownership, then assign independent checkers. Use
parallel helpers when available; otherwise run reader assignments sequentially
and obtain the second read from another agent invocation or a human checker.
The extractor cannot certify its own output as independently checked. Hold the
final build when an independent checker is unavailable.

## The explorer is settled

`assets/app` defines the explorer. Build it as defined unless the user asks for
a change.
- **Map:** the stages from the scope.
- **Rule view:** the statement, when it applies, exceptions, an example, what
  a violation does, where you see it, glossary terms, related rules, and code
  citations in a collapsed section.
- **Flags:** six types, shown as badges and usable as filters.
- **Reviews:** each reviewer's verdicts and notes stay in their own browser.
  They export as CSV, Markdown or JSON, and an import merges them.

## Setup

```bash
BR="python3 -B <this skill's folder>/scripts/br.py"
```

It needs `git` and Python 3.9 or later. `node` lets `publish-prep` prove the
upload plan, and a browser tool covers step 7. Resolve `<this skill's folder>`
from the installed skill, not from the target repository's layout. Quote paths
containing spaces; invoke `python3 -B "<skill>/scripts/br.py"` directly when
the shell cannot expand `$BR` safely. Every command after `init` takes `--work`.

## Step 1 — Pin the commit

```bash
$BR init --repo <path inside the repository>
```

`init` refuses uncommitted changes to tracked files, because every citation
names a commit. Use a separate clean checkout when the user's working tree is
dirty; leave their changes untouched. Survey, partition, check, batches and
build also reject source changes after init. Readers and checkers read that
same checkout. It also:
- creates a work directory outside the repository, under
  `$XDG_STATE_HOME/business-rules/` by default, or at `--work`;
- loads a saved scope from `<repo>/.business-rules/` or from `--scope-dir`;
- reads code-host link templates from `origin`.

**Done when** `init` prints the repository, the commit and the work
directory.

## Step 2 — Find where the business logic lives

With a saved scope, run `$BR survey --work <work>`. It validates the scope
against today's tree. Fix what it reports, such as new source directories or
vanished paths, then continue.

An **area** is a set of directories that readers cover at one depth:
*business* in full, *platform* as a summary, or *skip*. Without a saved scope,
`$BR survey --work <work>` maps the repository: languages,
package roots, entry points, the glossary, decision records and note folders.
It writes `scope.draft.json`. Read
[references/discovery.md](references/discovery.md), then:
- classify every candidate area as business, platform or skip;
- draft the lifecycle stages;
- save the result as `<work>/scope.json`.

Run survey again to validate it.

**Done when** survey reports 0 errors, and every source directory belongs to
an area, skipped ones included.

## Step 3 — Confirm scope and delivery at one checkpoint

If the user asked only where the business logic lives, ask for scope
confirmation, report the confirmed scope and stop.

For a catalogue run, read
[references/destinations.md](references/destinations.md) and list the available
destinations. Send one message containing the scope table survey printed
(area, tier, size, one-line reason), the stages, and up to three questions:
1. what to change in the scope;
2. local or published explorer, its location or provider, and its audience;
3. where the note and the saved scope go.

Ask only what the user has not already answered. Wait for the answers, then
record them with `$BR record`.

**Done when** the user has confirmed the scope, and each delivery choice is
recorded or **held**: an unanswered destination means build locally and
deliver nothing until the user chooses.

## Step 4 — Assign readers

`$BR partition --work <work>` assigns files to readers of about 10,000 lines
each (`--target-lines`). It writes `partition.json`, one prompt per reader in
`prompts/` and the reader brief. Edit `partition.json` in two cases:
- the proposal separates a decision from the code that executes it; query or
  template text belongs with the reader who owns its caller;
- a reader needs a `focus`.

Then run partition again. `--force` discards your edits and proposes afresh.

**Done when** partition reports 0 errors: every in-scope file has exactly one
reader.

## Step 5 — Read

Launch the reader assignments, in parallel when available, with this prompt:

```text
You are reader W3. Read <work>/prompts/W3.md and follow it exactly.
```

Then run `$BR check --work <work>`.

**Done when** check reports 0 errors and every coverage warning has a reason
you can name, such as a re-export or a test helper. To repair an error, re-run
that reader with the error lines. Reader output is evidence, so edit it only
through a reader.

## Step 6 — Second read

`$BR batches --work <work>` puts two kinds of rule into `verify/in1.json` to
`verify/in4.json`:
- every rule flagged *contradicts docs* or *inconsistent*;
- five unflagged rules per reader, chosen at random.

Assign each batch to a checker who did not extract its rules, with this prompt:

```text
You are checker N. Read <work>/verify/VERIFY.md and follow it exactly. Your input is <work>/verify/inN.json; write <work>/verify/outN.json.
```

**Done when** every `outN.json` covers its input exactly once, including every
requested flag verdict. Empty batches take `[]`. `build` rejects missing,
duplicate, mismatched or invalid verdicts and applies accepted corrections.
Changing reader output requires re-running batches and the second read;
`batches` clears old checker outputs. Report the checked counts, not an
estimated error rate among unchecked rules.

## Step 7 — Build and inspect

`$BR build --work <work>` writes `build/catalogue.json`, `site/` and
`bundle.html`. Serve `site/` with a supervised service in a remote sandbox.
Capture five states at 1440×900 and 2x scale:
- the home view;
- a flagged rule;
- a module;
- a stage combined with a flag filter;
- the same flagged rule at 390 px wide.

In each state, check three things:
- `BR_DATA.loaded.length === BR_DATA.expected`;
- the console shows no errors;
- nothing overflows horizontally at 390 px.

Inspect every screenshot. Reload after a rebuild, because browsers keep the
old files.

Verify review behavior on both `site/` and `bundle.html`. Enter a reviewer,
mark a rule Wrong, type a correction and export immediately as JSON, CSV and
Markdown. Each export must contain the latest text. Type on one rule and
navigate immediately; reload and confirm the note stayed with that rule.
Import JSON, confirm newer reviews win and older ones leave local corrections
unchanged, and reject another commit or malformed review. Walk the tree with
arrow keys and operate export/import by keyboard. Confirm citation URLs name
the pinned commit. Use states present in this catalogue; when no flag exists,
inspect an unflagged rule and state why the flagged/filter cases do not apply.

**Done when** the applicable visual states and review checks pass, screenshots
are inspected and retained at a user-accessible location, and failures or
unavailable browser checks are named. See the repeatable checks in
[references/verification.md](references/verification.md).

## Step 8 — Write the note

`$BR note --work <work>` writes the note to the recorded path, or to
`<work>/note.md`. Run it again with `--share-url` after delivery, so the note
cites the explorer.

**Done when** the note exists and the command reports no unbalanced
backticks.

## Step 9 — Deliver

Follow the recorded destination's section in `destinations.md`. Copy
`scope.json` and `partition.json` to the recorded save location.

**Done when** one of these holds:
- the destination's own check passes: a hosted upload verifies, and a public
  link opens in a fresh browser session;
- delivery is explicitly held because no destination was chosen.

## Step 10 — Report

Lead with the explorer's link or path and its audience. Then give the counts:
rules, flags by type, and the second-read results. After that:
- the *contradicts docs* findings a business owner must decide;
- the choices you made for the user: scope, partition and skipped files;
- the five screenshots;
- the delivery state: what is local, saved, shared, public or committed.
