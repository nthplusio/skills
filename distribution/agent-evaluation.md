# Agent evaluation adapter

`npm run eval:agents -- --list` lists definitions, **not executed scenarios**.
`npm run eval:agents -- --case settings/known-chat-no-runtime` emits a request
and exits 2 because no runner is bundled. This route includes all existing
`evals/evals.json` cases, the nine shared-settings scenarios, high-risk authority
cases, and negative host-invocation cases for the five manual-only workflows.

Use an authorized client/runner to execute one request in isolation. The adapter
must provision only the stated skills, fixtures, and actual tools, deny external
mutations, and log every turn, load, and tool call. Supply `prompt` to the agent;
keep expected output and assertions with an independent grader. Use existing
scenario notes for required fixture PRs; missing fixtures or a browser are
**inconclusive**, not skipped successes. Do not expose a missing companion through
another installation or readable checkout. For ordinary cases, resolve required
companions; for deliberate missing-companion cases, preserve the absence.

Record the client version, product mode, model and tools actually used. A
tool-rich agent instructed to pretend it has no tools does not test a tool-free
mode. For `activation/*`, install metadata in the actual host and observe whether
it loads the skill; directly injecting the skill cannot test activation policy.
Use the host's explicit invocation for positive manual-only workflow cases.
An agent with local doubles is not a target-product acceptance test.

## Result format

Save UTF-8 JSON with these fields:

```json
{
  "schemaVersion": 1,
  "scenarioId": "settings/known-chat-no-runtime",
  "sourceRevision": "<request sourceRevision>",
  "dirty": false,
  "sourceFingerprint": "<request sourceFingerprint>",
  "layer": "agent-with-doubles",
  "model": "<actual model>",
  "client": "<actual client>",
  "clientVersion": "<actual version>",
  "mode": "<actual mode>",
  "runner": "<adapter identity/version>",
  "executedAt": "2026-10-31T12:00:00Z",
  "tools": [],
  "loadedSkills": ["explain-to"],
  "observedActions": ["<observed actions, not planned actions>"],
  "limitations": [],
  "transcript": "transcript.jsonl",
  "toolTrace": "tool-trace.json",
  "output": "output.md",
  "assertions": [
    {"index": 0, "status": "inconclusive", "observation": "<what was actually observed>", "evidence": "transcript.jsonl"}
  ]
}
```

Include one indexed row per assertion, in order. Status is `pass`, `fail`, or
`inconclusive`. Evidence paths resolve beside the result and must contain actual
nonempty files; a no-tools run should record an explicit empty tool trace, not
omit it. Store browser recordings, database snapshots and output inspections
beside the transcript. Stage reviewed files before preparing the request: its
fingerprint covers tracked working-tree bytes, including staged new files, and
validation rejects results from a different fingerprint. Record the tested
archive checksum separately in the transcript. `layer: target-client` requires
actual installation and execution in that product and mode, including package
identity in the evidence.

Validate a recorded result with:

```bash
npm run eval:agents -- --case settings/known-chat-no-runtime --results /absolute/run/result.json
```

This command checks completeness and derives the recorded verdict. It does not
run a model, verify a runner's honesty, or replace human evidence review. Exit 0
means all recorded assertions passed, 1 means a recorded failure or invalid
record, and 2 means missing execution or an inconclusive result. Never report
enumeration, a prepared request, or a synthetic validator fixture as execution.
Keep evidence outside `dist/`: the package builder replaces that directory.
