# Worked examples

These come from a real record, with names made generic. For a full record, see
[`../assets/example-record.md`](../assets/example-record.md).

## A decision item, open

```markdown
- [ ] **Should a saved layout show the latest version of a Book, or the version it was saved with?**
  - **Context:** Books are becoming their own saved definitions so they can be reused, and a layout needs a rule for which version it shows.
    - Our definitions reader already returns the published head (`ops/definitions/get.ts:10-23`).
    - The existing API's grid presets resolve to the current saved version.
  - **Sources checked:** meetings 10-22 and 10-30 (no ruling on versions); the design reference (no versioning); `ops/definitions/get.ts:10-23`; the existing API's grid presets. No source rules on it. ([research](https://example.org/threads/T-research-l1))
  - **Options:** A: always the latest *published* version, never a draft. B: pin the version the layout was saved with.
  - **Recommendation:** A, the latest published version.
  - **Why:** Books are separate so they can be reused, and pinning would force every layout to be republished after each Book edit. **Tradeoff:** rolling back a layout alone won't restore the exact Books it showed then.
  - **Holding up:** lane 5's saving and loading piece.
```

## The same item, ruled

Check it off in place, put the ruling first, and keep the reasoning beneath it.

```markdown
- [x] **Should a saved layout show the latest version of a Book, or the version it was saved with?**
  - **Ruled 2026-11-05 by the owner:** A, as recommended. Lane 5 builds saving and loading on it.
  - **Context:** …unchanged…
  - **Recommendation:** A, the latest published version.
  - **Why:** …unchanged…
```

Then add a Done row: `| 2026-11-05 | Ruling | The owner ruled A on Book versions | Lane 5 |`.

## A ruling that changes the recommendation

```markdown
    5. Does a book get its own definition? **Not yet**: keep it inside the spine until reuse is asked for.
      - **The owner ruled 2026-11-05: yes.** Books will be reused, so a book gets its own definition with the same draft and publish path. This replaces the "not yet" recommendation.
```

## An answer recorded as open to veto

```markdown
- [x] **One source row to many entries (research, 2026-11-05):** no. In each map table a source row maps to exactly one entry. Sources: meeting 10-30, 06:34 ("you cannot have the same source dimension pointing to multiple values"); `registration.py:1574-1603` already deletes other mappings for a source. ([research](https://example.org/threads/T-research-7a))
- [x] **One active Book per Spine (decided by me, 2026-11-05):** a Spine shows one Book at a time for now. Reversible: the definition format allows more later.
```

## A worker's report to the editor

Workers send this by message; they never edit the record.

```text
Lane 3: ticket 60 delivered.
Commit: 084daf3 on layout-rebuild-plan (link).
Checks: check 476, DB 286, fixture 429/429, gitleaks clean.
CI: green on the first run (run link).
Record changes: Lane work item for ticket 60 is done; lane 3 is idle.
New question for the owner: none.
```

When a worker has a new question, it includes the question, what it checked,
and what the question holds up. The editor then routes it through
[`answering-questions.md`](answering-questions.md).
