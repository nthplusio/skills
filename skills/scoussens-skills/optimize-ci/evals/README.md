# optimize-ci evaluation suite

Nine cases cover evaluate, design, and local implementation behavior. Evidence
is checked in under `fixtures/` and is explicitly synthetic; no scenario needs a
live repository, hosted account, install, secret, or paid action. The first three
cases retain their historical purposes and the original Iteration 1 record, but
their facts are now fixture-bound. The skills-repo case records three jobs,
including `plugins`, rather than relying on a moving checkout.

## Running a comparison

Run a fresh with-skill attempt and a fresh baseline attempt against the same
fixture revision, prompt, and permissions. Keep workers read-only except for
the explicitly disposable implementation copy. Do not show workers assertion
IDs, expected outputs, this README's grading guidance, or any separate
ground-truth material; the fixture evidence itself is available to both.
Collect responses without configuration labels, blind/shuffle them, and only
then apply the observable assertions in `evals.json`. Do not force a report
template or reward length.

Grade concrete configuration as well as prose. Expand matrix command values and
compare them with the supplied command names. Match stated tested revisions to
event and checkout semantics. A mention of "combined revision" alone does not
explain the difference between source-only and merged-results pipelines. Keep
unverified execution and absence-of-action claims separate from response scores.

Before each round, check that fixture paths resolve and that no assertion or
expected-output file has leaked into worker context. Afterward inspect the
disposable implementation copy and run its checker; verify the checked-in
source fixture is unchanged. Record attempted/completed cases, skipped cases,
errors, sample counts, and assertion coverage honestly. Do not call a partial
round a full-suite result, infer unrun coverage, or compare attempts made on
different fixture revisions. Agent runs are intentionally not automated here.

## Fixtures

Top-level Markdown dossiers are synthetic provider evidence, not production
measurements. `gitlab-ci.yml` is a minimal illustrative config. The
`implementation/` directory is the source for a disposable working copy; its
checker intentionally fails on the supplied broken gate. Copy that directory
elsewhere before editing it, then run `python3 check_gate.py` from the copy.
The source fixture itself is not the implementation target.

## Check the collector separately

From the repository root, run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s skills/scoussens-skills/optimize-ci/evals -p 'test_*.py' -v
```

These tests exercise the collector's CLI against synthetic API evidence. They
cover retries, timestamp origins, more than 100 jobs, incomplete reads, unknown
workflow revisions, and unreadable protection. They do not evaluate agent
behavior or establish hosted billing. See [results](results.md) for recorded
agent samples and their limitations.
