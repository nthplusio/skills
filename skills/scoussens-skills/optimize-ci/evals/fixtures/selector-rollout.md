# Synthetic selector rollout dossier

GitHub Actions, private TypeScript monorepo. A ruleset on `main` requires the
`ci-gate` check, and the merge queue is enabled. Most pull requests come from
coding agents that squash before pushing; 92% of shadow-period pull requests
had a single commit.

A dependency-graph test selector has run in shadow mode for eight weeks. The
planning job uploads its predicted test set before any test job starts, and the
full suite runs independently. Evidence so far:

- 120 independent faulty changes, grouped by root cause, with zero misses.
  The team's 3% miss budget at 95% confidence was set before collection; the
  zero-miss bound is about 2.5%.
- A backtest of 60 past regressions, including renames, deleted files, shared
  helpers, fixtures, and lockfile changes, selected the exposing test in all 60.
- A selected test without shard metadata rejects the narrowed plan and runs the
  full suite. `ci/check-gate.mjs` compares executed test IDs with `plan.json`.
- The repository variable `TEST_SELECTION=full` restores the full suite and was
  tested with selection on in a staging fork.
- The shadow comparison job decides whether the full suite passed from the exit
  code of `gh run watch <run-id> --exit-status`.

Proposed `.github/workflows/ci.yml` with selection on:

```yaml
on:
  pull_request:
  merge_group:

jobs:
  plan:
    runs-on: ubuntu-latest
    outputs:
      mode: ${{ steps.plan.outputs.mode }}
    steps:
      - uses: actions/checkout@<pinned-sha>
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          fetch-depth: 2
      - id: plan
        env:
          TEST_SELECTION: ${{ vars.TEST_SELECTION }}
        run: node ci/plan.mjs --base HEAD~1 --head HEAD --out plan.json
        # In merge_group runs, plan.mjs writes mode=skip because every queued
        # pull request already passed ci-gate on its own.
      - uses: actions/upload-artifact@<pinned-sha>
        with: { name: plan, path: plan.json }

  unit:
    needs: plan
    if: needs.plan.outputs.mode != 'skip'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<pinned-sha>
      - uses: actions/download-artifact@<pinned-sha>
        with: { name: plan }
      - run: node ci/run-selected.mjs plan.json --executed executed.json
      - uses: actions/upload-artifact@<pinned-sha>
        with: { name: executed, path: executed.json }

  ci-gate:
    needs: [plan, unit]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<pinned-sha>
      - uses: actions/download-artifact@<pinned-sha>
        with: { name: plan }
      - uses: actions/download-artifact@<pinned-sha>
        with: { name: executed }
      - run: node ci/check-gate.mjs plan.json executed.json
```

Proposed `.github/workflows/integration.yml`, whose `integration` check the
team plans to add to the ruleset once selection is on:

```yaml
on:
  pull_request:
    paths: ['services/**', 'db/**']
```

The team asks to enable skipping next week.
