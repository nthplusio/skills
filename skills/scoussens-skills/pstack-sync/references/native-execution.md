# Native execution receipts

Use the installed `orchestrate/scripts/tools/native.ts` with the upstream script dependencies available in a writable installed tree. It records native execution and can integrate checked commits into a designated local branch. It never spawns, archives, cancels, pushes, or queries an agent. Use supported native tools for those operations and supply their actual receipts.

```sh
bun <orchestrate>/scripts/tools/native.ts <workspace> <request.json>
```

The workspace already contains an upstream-valid `plan.json`. Start a new native workspace rather than adopting an executed scripted run. `state.json` is the only task lifecycle. `native.json` records mode, run identity, ownership, scope reference, revision, and typed execution receipts. Do not put new metadata fields in the strict upstream plan/state schemas.

## Initialize and inspect

```json
{
  "action": "init",
  "writer": "root-recorder",
  "expectedRevision": 0,
  "runId": "project-run-1",
  "dispatcher": {"kind": "thread", "harness": "example", "id": "actual-dispatcher-handle"},
  "deliveryOwner": {"kind": "thread", "harness": "example", "id": "actual-dispatcher-handle"},
  "scope": {"reference": "path-or-link-to-approved-brief", "revision": "1"}
}
```

Run `{"action":"preflight"}` before native tool calls and after restart. It reads without writing. It returns metadata, lifecycle state, unresolved problems, and any interrupted transaction's recovery request. `inspect` is the same read-only operation. Verify scope and write target yourself; a valid JSON request does not authorize a side effect.

After initialization, both commands also return `naming`. Its prefix is `orch-` plus the first ten SHA256 hex characters of the immutable run ID. `dispatcherTitle`, `rootTitle`, and `tasks[].title` derive from that prefix, with at most 100 characters and the prefix first. They are suggested tool arguments, not claims that an agent was renamed. No second identity store is written. The full run ID and recorded dispatcher/agent handles remain authoritative.

Before creating agents, use those titles in the supported launch name or task description and carry the full run ID, dispatcher, and state location in the brief. Apply `dispatcherTitle` to the delivery dispatcher when supported and `rootTitle` only to a separate execution root. Inspect/repair names with supported native tools or record the capability limitation through `observe`. The recorder never renames an agent itself. Keep the prefix for retained threads and nested delegation; a retry changes its attempt receipt, not run membership. See the portable workflow's "Make run membership visible" contract for harness fallbacks.

Every write includes the same `writer` and current `expectedRevision`. Successful changes increment the revision. Exact repeated init, dispatch, and completion receipts are no-ops. Use `reconcile` after editing plan.json; it adds new pending tasks, prunes removed pending tasks, and preserves running/terminal history and Andon. It can update `scope`, but the referenced decision document retains the prior source and supersession history.

## Record actual tool results

After the native tool returns its handle, record it immediately. A blocking subagent's returned result can be recorded as dispatch followed by completion. Do not infer success from a delivered message. Choose the actual `thread`, `subagent`, or `tool-call` kind and real harness. The attempt ID comes from the tool's run/call receipt, not the scripted adapter's synthetic `m0`.

```json
{
  "action": "dispatch",
  "writer": "root-recorder",
  "expectedRevision": 1,
  "receipt": {
    "task": "build",
    "attemptId": "actual-execution-attempt-id",
    "handle": {"kind": "subagent", "harness": "example", "id": "actual-worker-handle"},
    "coordinator": {"kind": "thread", "harness": "example", "id": "actual-coordinator-handle"},
    "actualParent": null,
    "logicalParent": "root-plan"
  }
}
```

`actualParent` is nullable when the tool does not report nesting. `logicalParent` names the planned parent and is independent of that fact. Dependencies must have successful collected handoffs before dispatch. A verifier resolves its starting ref from its target's collected branch unless explicitly pinned. Check these prerequisites before spawning; recording a refusal cannot undo an already-created agent.

Dispatch binds a verifier to its target's current execution attempt. Reconciliation refuses to retarget an active verifier. Its collected verdict updates that exact target in the same transaction, superseding a worker's self-report without discarding either raw handoff. A failed or blocked verdict prevents dependent dispatch.

Use `observe` with `attemptId` and a literal `note` for progress. It does not invent lifecycle transitions. For completion, supply `attemptId` and `receipt` with `result` set to `finished`, `error`, or `cancelled`, and `body` set to the raw handoff text. The recorder preserves every attempt's bytes, parses upstream branch/verification/failure/PR fields, and persists the handoff before terminal state. `handed-off` means collected, not accepted. An explicit new attempt after error/cancellation preserves the earlier receipt. Confirm the old writer is quiescent first.

Include the installed `prompts/worker.md` or `prompts/verifier.md` handoff format in each native brief. Native tools do not render those templates automatically. Worker success requires a `## Status` heading followed by `success` on the next line. Inline `Status: success` is not equivalent. Before collecting a terminal receipt, check the headings and ask the worker to correct malformed output without changing its code. Preserve the worker's returned bytes. If malformed output is already collected, keep that immutable receipt and use an explicit follow-up task rather than rewriting history.

## Prepare parallel code work

For a new code-writing run, include `code` in the `init` request. Leave it absent for research-only runs. Existing runs keep their mode. Choose a local integration branch distinct from trunk and leave that branch unchecked out in every worktree.

```json
{
  "code": {
    "repository": "/absolute/path/to/coordinator/repo",
    "integrationRef": "refs/heads/orch/example/integration",
    "checks": [{"command": "npm ci && npm test", "timeoutSeconds": 300}]
  }
}
```

Create that branch from the observed starting commit before initialization. `repository` is the coordinator's local path. `plan.repoUrl` is the shared repository identity and must match each checkout's `origin`. Fetch complete history before ancestry checks. The configured commands execute in a fresh candidate worktree. Include dependency installation and every required integration check. Commands must leave tracked files and HEAD unchanged, and leave no untracked files outside Git's ignore rules. These commands have your shell's privileges. Keep production writes and credentials out of them.

Assign every code writer `pathsAllowed` in `plan.json`, using repository-relative globs such as `packages/tree/**`. Use `pathsForbidden` for exclusions. Verifiers are read-only. Ownership checks conservatively compare glob prefixes, so two patterns with the same prefix may serialize even when they match different files. Prefer narrower directories or sequence the work. Resource names reserve external mutable targets within this run, such as `snowflake:test-schema` or `port:3000`. Independent database namespaces use different names. These reservations do not lock other runs or external clients.

Before launching a worker, send `prepare` with the current writer and revision:

```json
{
  "action": "prepare",
  "writer": "root-recorder",
  "expectedRevision": 1,
  "id": "tree-batch-1",
  "task": "tree",
  "baseCommit": "FULL_COMMIT_ID",
  "branch": "orch/example/tree-1",
  "environment": "worktree",
  "resources": []
}
```

Replace `FULL_COMMIT_ID` with the observed full commit ID. `prepare` reserves the task, branch, paths, and resources before a launch can have an unknown outcome. It rejects unavailable commits, overlapping writers, and unmet dependencies. Code writers must start within the integration branch's history. A worker depending on another worker must include its verified integration commit. A verifier instead starts at its target's exact result commit. Use a new task for each completed batch in a long-lived workstream.

Inspect `readiness` for dependency and ownership blockers. `ready` means eligible for preparation, not authorized to launch. Inspect `assignments` for reserved inputs and receiver state. A running task does not block independent preparation. A reserved task with no execution handle requires launch reconciliation, not another launch.

### Receive inputs on a shared disk

Copy the task's `assignment` object from `inspect` into a request for the installed Git helper:

```json
{
  "action": "worktree",
  "repository": "/absolute/path/to/coordinator/repo",
  "checkout": "/absolute/path/to/tree-worktree",
  "assignment": {
    "id": "tree-batch-1",
    "repository": "https://github.com/example/repo",
    "baseCommit": "FULL_COMMIT_ID",
    "branch": "orch/example/tree-1"
  }
}
```

Run `bun <orchestrate>/scripts/tools/git-work.ts <request.json>`. It creates a new worktree and branch at the pinned commit. On repetition, it checks the existing destination without resetting it. It returns a receiver receipt only when origin, HEAD, branch, and clean status match. Record that output with `native.ts` using `action: "received"`, `receipt`, writer, and revision. The coordinator rechecks local receipts. Give the worker this checkout path, then record its actual dispatch receipt with `preparationId: "tree-batch-1"`.

### Receive inputs in an isolated environment

Use `environment: "isolated"` when preparing. Launch an independently owned worker with a bootstrap-only brief. Record its actual dispatch handle immediately, with `preparationId`. The worker must obtain and confirm the input before editing code.

Transfer a published ref when pushes are authorized, or transfer a Git bundle through supported file tools. Include the helper and its dependencies if they are absent at the destination. Fetch the ref or bundle, check out the assigned branch at the exact base commit, and run `git-work.ts` with `action: "receive"`, `checkout`, and `assignment`. This operation checks the existing checkout without changing it. Send the returned receipt to the coordinator. After the coordinator records `received`, continue code work in that same environment. `assignments[].codeReady` reports receipt collection, not an agent sandbox permission.

The coordinator cannot inspect an isolated filesystem through its local Git executable. Collect the helper's actual output through the recorded worker handle. A message containing a guessed receipt is not evidence. Fetch or transfer the result's Git objects back before collecting successful completion. Uncommitted files are not a result commit.

For Amp, use native thread and file-transfer tools. Orbs start from project state, not the coordinator's unpushed branch. Run project dependency preparation after selecting the assigned commit, even when the orb restored a setup snapshot. Use `.agents/resume` for runtime authentication and managed orb services for long-lived processes. Keep setup credentials, service leases, and shared database namespaces outside Git bundles. Keep the worker that owns the checkout when bootstrap or a repair needs that state. Respect observed spawn capacity rather than launching duplicate replacements for queued or paused orbs.

## Integrate checked batches

Successful code completion adds `resultCommit` to the normal `complete` request. The recorder checks object availability, base ancestry, allowed paths, forbidden paths, and the receiver receipt. Rename source and destination paths both count. A verifier must return the exact commit it received. The handoff's branch, if supplied, must match the assignment.

`inspect.integrationQueue` lists collected worker results that have not been integrated. It is a derived list, not another lifecycle store or a claim that every result is ready to merge. Give the queue priority over starting unrelated feature work. Integrate one bounded batch at a time:

```json
{
  "action": "integrate",
  "writer": "root-recorder",
  "expectedRevision": 5,
  "attemptId": "ACTUAL_WORKER_ATTEMPT",
  "expectedHead": "FULL_INTEGRATION_HEAD"
}
```

The recorder requires a successful handoff and any declared verifier's successful handoff. It builds an ancestry-preserving merge in a temporary detached worktree and runs the configured checks on that exact candidate. It records command output and the resulting commit, then advances the local integration ref only if its head still matches `expectedHead`. It never pushes. A checked-out integration branch, conflict, failed check, stale scope, or moved ref stops integration. Candidate build failures are preserved under `integration-failures/`. Successful candidates remain pinned under `refs/orchestrate/candidates/` for recovery.

Keep published lane history intact. Use the latest verified integration checkpoint as the base of dependent work. When a conflict needs a code change, assign a repair batch with explicit ownership and fresh verification. Do not silently choose one worker's side. Unrelated plan additions do not invalidate a prepared task. Changes to that task's definition or the run's scope require a new preparation and, after completion, a new task that carries the revised acceptance.

An identical integration request is a no-op after collection. Its receipt describes the commit integrated at that time, not a fresh assertion about a remote branch. Before publication, inspect the current local and remote refs and run the final acceptance checks. Candidate retention refs, worker branches, and worktrees remain available until explicitly cleaned up.

## Recover without dispatching twice

A running row has an unresolved execution outcome until native observation supplies its result. Inspect it through its original tool. Never use the scripted poller, cleanup, or respawn on a native-owned workspace.

Writes use an exclusive `native.lock` and durable `native.transaction.json`. A crash may leave the lock. Confirm the recorded PID has exited before manually removing that lock. Then repeat the identical request or use the `recover` request returned by preflight. Recovery checks every file against its before/after bytes and refuses conflicting writes. Do not edit a transaction to manufacture successful evidence.

For an interrupted integration, the journal also records the expected old and new Git commits. Recovery advances the old ref once or recognizes the exact new ref and completes metadata. Any third value requires reconciliation. A security hold stops a pending ref advancement, while an already-applied advancement can finish its metadata. Recovery does not rebuild or retest a candidate. Preserve the repository, candidate objects, and canonical workspace together at their recorded paths when resuming.

For a preparation that never launched, record `release` with its `id` and a reason only after confirming that no worker owns it. A dispatched preparation requires an actual completion or cancellation receipt. Reservations have no automatic timeout. Copying state to another orb does not stop its previous writer.

Unexpected state changes require explicit reconciliation. Reconciliation preserves security holds; it does not establish that an unknown external operation was safe. Mode and lifecycle writer remain fixed for this workspace. For transfer, stop the old writer and hand off the canonical workspace with its unresolved receipts; do not run two coordinators against it.
