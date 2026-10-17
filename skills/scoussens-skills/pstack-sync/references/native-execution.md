# Native execution receipts

Use the installed `orchestrate/scripts/tools/native.ts` with the upstream script dependencies available in a writable installed tree. This is portable bookkeeping. It never spawns, archives, cancels, pushes, or queries an agent. Use supported native tools for those operations and supply their actual receipts.

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

## Recover without dispatching twice

A running row has an unresolved execution outcome until native observation supplies its result. Inspect it through its original tool. Never use the scripted poller, cleanup, or respawn on a native-owned workspace.

Writes use an exclusive `native.lock` and durable `native.transaction.json`. A crash may leave the lock. Confirm the recorded PID has exited before manually removing that lock. Then repeat the identical request or use the `recover` request returned by preflight. Recovery checks every file against its before/after bytes and refuses conflicting writes. Do not edit a transaction to manufacture successful evidence.

Unexpected state changes require explicit reconciliation. Reconciliation preserves security holds; it does not establish that an unknown external operation was safe. Mode and lifecycle writer remain fixed for this workspace. For transfer, stop the old writer and hand off the canonical workspace with its unresolved receipts; do not run two coordinators against it.
