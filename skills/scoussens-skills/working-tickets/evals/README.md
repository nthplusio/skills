# Evaluating working-tickets

These evaluations execute ordinary code assignments against a local tracker.
They do not ask the worker to describe ticket hygiene or produce an action ledger.
Final prose earns no credit. The old synthetic-ledger scores are superseded;
they measured instruction-following under explicit hygiene cues, not spontaneous
ticket maintenance.

## Paired execution

Run `harness.py prepare` for each case listed below and arm
(`with_skill`, `without_skill`), using fresh output directories. For example:

```sh
python3 harness.py prepare --case assigned --arm with_skill \
  --out /tmp/ticket-evals/assigned-with \
  --url http://127.0.0.1:8794/assigned-with
```

Prepare all runs before starting `harness.py serve --root /tmp/ticket-evals
--port 8794`. In an Amp orb, start this service with `amp orb service start`,
not a detached shell. The server exposes only the fixture tracker API, not
evaluation snapshots or grades. Workers use `tools/tickets.py` in their own repo.

Give each isolated worker **only** the returned repository path, assignment,
and available-skill metadata, plus the same execution boundary: work within that
repository, use its local tools, and do not inspect sibling runs or evaluator
files. Both arms may perform routine local tracker writes. Do not inject these
assertions, mention hygiene, demand a ledger, or pre-load the skill. The with-skill
arm has the skill and references discoverable in `.agents/skills/`; the baseline
does not. Both find the same workflow through ordinary repository guidance.
Record model/version, tool environment, worker prompt, and any preloaded skills.
Use matched settings and independent contexts. A baseline that inherited this
skill is contaminated and must be rerun.

Workers edit real Python files and run real checks. The tasks are:

| Case | Ordinary assignment | Discoverable conditions |
| --- | --- | --- |
| assigned | Fix APP-42. | Empty CSV header bug, poor title/tags, concurrent human edit, accepted comment with lost response. |
| parent | Implement APP-100. | Paginated/nested children, dependent CSV fixes, missing docs child, human-owned blocker, deferred work, automation-owned status. |
| pickup | Pick up the next ready CLI bug and fix it. | Ready-ticket search, incorrect exit code, poor title/missing type label, worker-owned status. |
| resume-assigned | Fix APP-42; reproduce and add a regression test, then pause before production edits for review. | Continue the same conversation without repeating the assignment. |
| resume-parent | Implement APP-100; complete the first ready step, then pause for review. | New session rediscovers the unfinished parent from repository/tracker state, without a handoff. |

## Pause and resume

For the two `resume-*` cases, let the first worker stop at the requested review
boundary. Preserve its actual edits and tracker operations; do not seed a
fictional work log. Once it has stopped, run:

```sh
python3 harness.py checkpoint --run /tmp/ticket-evals/RUN_DIRECTORY
```

The evaluator checks that the assigned fix still needs implementation, or that
the parent's first header step is accepted while quoting and docs remain open.
An overrun or missing checkpoint invalidates the setup; report it rather than
silently resetting state or scoring it as a successful resume. The checkpoint
stores the event boundary and source hashes outside the worker repo, then adds
a human review note to the original ticket. The next tracker request reloads
the persisted state, including that review. Run the checkpoint only between
workers, never concurrently with one.

- **resume-assigned:** continue the same worker with exactly “Looks good.
  Continue from where you stopped and finish the fix.” Do not repeat metadata,
  the ticket ID, workflow rules, or hygiene instructions.
- **resume-parent:** start a fresh worker with the same repository and execution
  boundary, ordinary available-skill metadata, and exactly “Continue the work
  left in this repository and finish the remaining implementation.” Supply no
  prior transcript, ticket ID, handoff, or checkpoint file. Use existing source
  and canonical tracker state, not a newly generated handoff document.

Grade the completed run normally, and report `resumption` separately. Its checks
use **only post-checkpoint operations** for refreshing records, persisted updates,
and new verification evidence. Good first-phase hygiene cannot compensate for
post-resume neglect. Also check human-review preservation, exact reposts of prior
start/pause comments, remaining implementation gates, and parent reconciliation.
Read comments to catch semantic restarts the exact-duplicate check cannot detect.

## Sparse guidance

Pass `--guidance sparse` to `prepare` for both arms of a paired run. The default
is `--guidance linked`. Use fresh directories and the same ordinary assignments.
Do not tell workers where standards live or ask them to search for standards.

The sparse profile removes the workflow link from `AGENTS.md` and moves the
unchanged standards to `docs/engineering/contributing.md`, with no incoming link.
`AGENTS.md` still identifies Python, the local tracker CLI, and execution limits.
The tracker workflow API exposes its schema and status owner, not the comment,
title, tagging, or parent-plan conventions. Both arms retain identical standards,
ticket data, implementation tasks, and grading rules. Only skill availability
differs between arms. Grades record the guidance profile.

Run at least `assigned` and `parent` to cover both single-ticket maintenance and
child planning. Review worker transcripts for discovery of the unlinked document
as well as persisted tracker operations. Finding a document alone earns no
hygiene credit. Keep discovery observations separate from the unchanged action
rubric, and record inherited instructions that might help either arm.

This profile tests a missing pointer, not an inaccessible policy. The fixture is
small, and the standards remain easy to find through a file listing or search.
It does not model a large repository, external documentation, or conflicting
standards. Report ties rather than moving the document again to force a gap.

## Evidence and grading

After workers stop, run `harness.py grade --run PATH` for each directory.
`evidence.json` lives outside the worker repository and persists every request,
including rejected writes, server sequence/time, before/after tracker snapshots,
and source hashes. The service saves accepted-but-unacknowledged comments before
returning an error. Lost or unreadable evidence invalidates a run; do not score
it as zero or success. Restarting the server reloads saved evidence.

The grader separates implementation acceptance from hygiene. It runs fixed
evaluator-owned acceptance assertions in a fresh Python process, independent of
worker-authored tests. It checks actual mutations, timing relative to source
changes, same-ticket verification updates, cleanup, state gates, preservation,
and parent/child reconciliation. A fixed implementation with no tracker writes
fails maintenance checks. A perfect final explanation changes no score.

`no_unsupported_success_claims` checks persisted comments and body writes in
event order. An explicit acceptance-success claim needs an earlier passing
check for that ticket, matching the files its acceptance executes. A later
failed check supersedes an earlier pass. A completion claim also needs the
tracker's status to be `done` at the time of the claim. Parent updates that name
children are checked against each named child, not the parent comment's target.
Within a plan bullet that starts with a ticket ID, later sentences retain that
ticket as their subject. The next bullet resets the subject.
Corrections and eventual success do not erase an earlier unsupported claim.
Failure evidence includes the event, ticket, clause, and latest check event.

This assertion uses bounded phrase recognition, not a language-model judge.
It excludes negated, prospective, conditional, and correction wording, and
does not infer tracker acceptance from ordinary local-test statements. Unnamed
child aggregates, arbitrary paraphrases, mixed clauses, historical summaries,
and claims about local tests still require semantic review. A passing assertion
does not prove that every sentence is truthful. Preserve raw scores alongside
manual findings rather than changing the rubric after a run.

Report per-case outcomes and missing behaviors, not just an aggregate percentage.
Keep operation logs and worker transcripts with results outside the installable
skill directory. Review semantic quality too: automated checks of plan IDs,
comment length/evidence terms, and changed titles cannot prove that wording is
useful or that every dependency was understood. Do not adjust the rubric after
seeing an arm's result to force a difference.

## What this does not establish

- This is a local mock, not real Linear/GitHub integration or production work.
- Available skill metadata is controlled; actual loading needs transcript
  evidence. `skill_loading_observed` is unknown in machine grades. Use
  `triggers.json` separately to evaluate discovery, including negative queries.
- Same-user filesystem separation prevents accidental edits, not adversarial
  access to evaluator files. There is no security-isolation claim.
- One paired run per case is exploratory, not a reliable effect estimate.
  Repeat with multiple seeds/models and ordinary repository workloads before
  claiming general effectiveness. Report shared inherited instructions that
  could raise baseline performance.
- Interruption cases model planned review pauses and a fresh-context restart,
  not arbitrary mid-tool cancellation, actual harness compaction, or a long
  unrelated conversation. Default interruption runs retain linked guidance;
  report sparse guidance separately when that profile is used.
- The current action suite uses one HTTP tracker contract. File-based trackers,
  read-only boundaries, and create-and-work triggering need separate coverage;
  do not retain the old simulation's coverage claims.

`python3 -B -m unittest discover -s PATH/TO/evals` tests the harness's behavior,
not the model. `npm run test:skills` discovers that suite automatically;
`npm run validate` checks skill structure and eval metadata. Neither runs models.
