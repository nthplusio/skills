# layout-rebuild: work done and remaining

The orchestrator thread ([T-orchestrator](https://example.org/threads/T-orchestrator)) is the only editor of this page. Lane threads read the mirror before starting a piece and report changes to the orchestrator by message instead of editing this page.

Lanes read the mirror with:

```bash
git fetch --quiet origin layout-rebuild-status && git show origin/layout-rebuild-status:STATUS.md
```

Last updated: 2026-11-05

## Where things stand

- **Outcome so far:** the walk menu and the JSON-driven drum work on the plan branch. Saved layouts are designed and waiting on two rulings.
- **Delivery head:** `layout-rebuild-plan` at [`ab5d078`](https://example.org/commit/ab5d078). [Hosted CI](https://example.org/runs/42017580376) green on the first run.
- **Waiting on the owner:** 2 decisions. The ID question holds up lane 2's write-back step.
- **Mirror:** `STATUS.md` on branch `layout-rebuild-status`, committed only by the orchestrator. It has no pull request and is never merged.
- **Feedback:** manual review. Comment on the decision in this record, then [ask the editor to review it](https://example.org/threads/T-orchestrator). Comments alone do not start review.

## Lanes

| Lane | Owner | Branch | State | Now |
| --- | --- | --- | --- | --- |
| 1, integrator | [T-lane-1](https://example.org/threads/T-lane-1) | layout-rebuild-plan | Idle | Plan green at `ab5d078` |
| 2, data | [T-lane-2](https://example.org/threads/T-lane-2) | layout-rebuild-data | Held | Write-back held on the ID question |
| 3, look | [T-lane-3](https://example.org/threads/T-lane-3) | layout-rebuild-look | Working | Header walk, ticket 60 |

## How open questions get answered

The owner's rule, 2026-11-04: answers come from these sources, in this order:

1. Meeting recordings and transcripts (the project's meeting tools)
2. The design reference app
3. The existing web and API apps
4. When necessary: the development database, read only

Each open question first goes to a research thread with its sources, which returns a recommendation. Only a question the sources cannot settle goes to the owner, under **Needs the owner**, with the sources checked and what it is holding up. The orchestrator decides reversible, in-scope questions itself and records them as **Decided by me**, open to the owner's veto.

## Remaining work

### Needs the owner

- [ ] **Which ID does a document's object link hold?**
  - **Context:** the local column points at the Object, but the current system writes the ID of the object's source record instead.
    - An Object is the shared item used by documents, deliveries and jobs. A source record is the original imported row. The decision is whether to keep these as separate links or change every reader to use the original row.
    - Local schema: the column references the Object (`baseline/schema.sql:5010`); lane 2's registration code follows it (`stores/registration.ts:110-125`).
    - Current system: writes the source-record ID (`services/dimensions/write/node.py:2166-2177`). The development database's two assigned documents hold source-record IDs that are not Object IDs.
  - **Sources checked:** meetings and the design reference don't address the column; the local schema and registration code; the existing API; the development database (2 of 32 documents linked). ([research](https://example.org/threads/T-research-k10))
  - **Options:** A: keep the column pointing at the Object, and add a separate reference to the source record. B: change the column to hold the source-record ID, and update its key and every reader.
  - **Recommendation:** A: keep the document linked to the shared Object and store the original source record in a separate column.
  - **Why:** the Object link is what Document, delivery and Job references need, and a separate column keeps the existing lineage without mixing two kinds of ID in one column. **Tradeoff:** one more column to fill on write.
  - **Holding up:** lane 2's write-back step. The rest of that piece is being built.
- [ ] **Should bars change from 4 cards to 6 that snap only to 0, 1 or 6?**
  - **Context:** bars are authored at 4 cards today and snap to 0, 1 or 4 and up (`Seam.tsx:24-27`). The design reference uses 6.
  - **Sources checked:** meeting 10-19 (cue 273 says seven); meeting 11-04 (cues 459-473: the six-card example, admitted unfinished); the existing web app uses percentages, so it settles neither.
  - **Recommendation:** keep 4 cards and the current snapping; treat a change as its own later piece.
  - **Why:** six is a demonstration in the reference, not a ruling; the meetings give 4, 6 and 7 at different times. **Tradeoff:** the reference and the app keep differing until the owner rules.
  - **Holding up:** nothing yet.
- [x] **Do saved layouts survive a local reset?**
  - **Ruled 2026-11-05 by the owner:** approved as recommended. Layouts that matter are promoted into the stored baseline; a reset clears the rest.
  - **Recommendation:** no; promote the ones that matter into the baseline.
  - **Why:** that is the existing baseline rule for definitions (`ADR-0007:147-157`). **Tradeoff:** existing saved collections need a one-time export first.

### Decisions already approved

- [x] **Sign out:** in the user-card panel (approved 2026-11-05). *Holds:* ticket 65.
- [x] **Dragging the page:** the page stays visible, at least one card wide (approved 2026-11-05). *Holds:* ticket 68.

### Answered by research (open to the owner's veto)

- [x] **One source row to many entries (research, 2026-11-05):** no. In each map table a source row maps to exactly one entry. Sources: meeting 10-30, 06:34 ("you cannot have the same source dimension pointing to multiple values"); `registration.py:1574-1603` already deletes other mappings for a source. ([research](https://example.org/threads/T-research-7a))
- [x] **One active Book per Spine (decided by me, 2026-11-05):** a Spine shows one Book at a time for now. Reversible: the definition format allows more later.

### Stopped

- **Follow-up post to the architect:** already answered by the owner's drum ruling. No further posts.

### Lane work

- [ ] **Lane 2:** identity rows built locally and uncommitted; waiting on the ID question above before it can freeze.
- [x] **Lane 3:** ticket 60 delivered at `084daf3`, hosted CI green.

## Done

| Date | Kind | What | Where |
| --- | --- | --- | --- |
| 2026-11-05 | Delivery | Ticket 27: the importer registers each delivery through the atomic apply. Checks: check 476, DB 306, importer 16, fixture 429, gitleaks clean. CI green on the first run ([run 42017580376](https://example.org/runs/42017580376)) | [`ab5d078`](https://example.org/commit/ab5d078) |
| 2026-11-05 | Delivery | Lane 3: ticket 60 live walk and the drum order fix. Checks: check 476, DB 286, fixture 429. CI green on the first run ([run 41995484614](https://example.org/runs/41995484614)) | [`084daf3`](https://example.org/commit/084daf3) |
| 2026-11-05 | Delivery | The fill-down rule pushed (docs only). Checks: check 470, DB 286. Hosted lab-1 failed on a known startup flake; the one authorized rerun failed the same way, so it is pushed but not CI-green | [`a4cbe1e`](https://example.org/commit/a4cbe1e) |
| 2026-11-04 | Ruling | The owner approved building ticket 96 | Lane 3 |
