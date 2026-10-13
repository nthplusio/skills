# Pull request 61 — Split the validate workflow into a fast gate and a full run

> Synthetic fixture for a skills repository with one GitHub Actions
> workflow.

## Before

One job, `validate`, runs on every push and every pull request. It installs
Node, installs dependencies, runs the frontmatter validator, the private-terms
scan, the builder check, the Python eval tests for every skill, and the three
plugin test suites, in sequence. A typical run takes 9 to 11 minutes. Any
failure anywhere marks the whole run red, and a contributor who changed one
skill waits for the plugin suites to finish before seeing the validator
result.

## After

Two jobs.

- `gate` runs the validator, the private-terms scan, and the builder check.
  It finishes in under one minute. It is the only required check for
  merging.
- `full` runs the Python eval tests and the plugin suites. It starts at the
  same time as `gate` and reports separately. It is required on `main` and
  on pull requests that touch `plugins/` or any `evals/` folder, and
  advisory otherwise.

The private-terms scan stays in `gate`, so no merge can land a private name
even when `full` is skipped.

## Cost

Both jobs install dependencies, so the total runner minutes per run rise by
about one minute. Wall-clock time to the first useful signal falls from about
ten minutes to under one.

## What a contributor sees

A pull request that only edits a `SKILL.md` gets a green `gate` in about a
minute and can merge. The `full` job still runs and reports, and a failure in
it opens an issue instead of blocking the merge.
