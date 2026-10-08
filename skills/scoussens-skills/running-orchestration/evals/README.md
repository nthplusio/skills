# Run behavioral evaluations

This suite records candidate-agent actions against isolated mock tools. It
does not launch agents, call customer services, or publish anything. The
candidate must execute the request; generating fixtures or grading untouched
files is not a behavioral evaluation.

The first suite uses six existing prompts:

| Case | Skill and prompt ID | Observable contract |
| --- | --- | --- |
| `setup-missing-owners` | Setup 0 | Confirm paths, save valid JSON, classify blocking sessions as helpers, leave unavailable owner operations null. |
| `setup-confirmation` | Setup 2 | Discover facts and ask one storage question; save no configuration while confirmation is pending. |
| `runner-proof-reuse` | Runner 0 | Reuse sufficient receipts and owners, remove the hash-only hold, separate delivery claims, retain an unresolved runtime obligation. |
| `runner-authorization` | Runner 2 | Keep unrelated work moving, reserve the occupied runtime, ask about indirect deployment, and perform no unauthorized publication. |
| `runner-closure` | Runner 3 | Retain B's proof and update status before actual closure; leave idle A open while required CI runs. |
| `runner-native-resume` | Runner 5 | Restore native context and stable IDs, retrieve missing proof, preserve corrections, and claim no new closure when unsupported. |

## Prepare and execute

Run from a Git checkout. Choose a new absolute directory outside the checkout
for every iteration. Existing evidence is preserved rather than overwritten.

```bash
python3 -B <runner-skill>/evals/behavior.py prepare /absolute/path/iteration-1
```

Give a fresh bounded candidate agent each case's `request.md`. Give all
candidates the same execution instructions:

> Execute this request using its skill and mock harness. Record all scenario
> actions through the harness and your final user-facing answer with `reply`.
> Read only this request, the skill resources exposed by the harness, and your
> case's state. Do not inspect the evaluator implementation, world.json, grading
> output, or other cases. Use no live services, Git mutations, real owner
> conversations, or additional agents. Modify no repository instructions.
> Return what you actually completed or await and any harness error. Do not
> grade your own run.

Cases have disjoint state directories and can execute concurrently. Work
owners exist only in stub state; a bounded candidate is not another
orchestration owner. Keep the agent mode and inherited guidance consistent
and record them in the result limitations.

## Grade actions and claims

```bash
python3 -B <runner-skill>/evals/behavior.py grade /absolute/path/iteration-1
```

The command writes `mechanical-results.json` and exits nonzero on failed
checks. It inspects recorded actions and actual files, not the candidate's
assurance that it followed the skill. Mock publication, checks, and closure
are allowed to succeed even when wrong, so the grader can detect those
mistakes without causing live effects.

Inspect each `trace.jsonl`, `reply.md`, and final state too. Record a separate
manual verdict citing the relevant events or exact claims. Check that questions
name the missing authorization, assignments respect occupied resources, claims
stay within retained proof, and unsupported capabilities remain explicit.
Mechanical success alone does not grade the meaning of a message.

Retain `suite.json`, instruction and harness snapshots, requests, traces,
replies, state, and both verdicts. Report the six case outcomes separately from
the existing 15 JSON/dashboard contract tests. One sample per case establishes
only that observed run, not reliability across models or live integrations.

If a case fails, preserve the original result. Correct the skill, fixture, or
grader only after identifying which one caused the failure. Rerun affected
cases with fresh candidates in a new directory:

```bash
python3 -B <runner-skill>/evals/behavior.py prepare /absolute/path/iteration-2 \
  --cases runner-proof-reuse runner-authorization
```

A without-skill baseline is an optional separate comparison. It is not a gate
for this pass/fail suite.
