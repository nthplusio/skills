# Orchestration workflow

This extension owns nthplusio's workflow around upstream orchestration. Sync keeps upstream plans, task schemas, handoff parsers, and improvements. Harness profiles select supported tools. Runtime ports implement transport. Application repositories own fixtures, access policy, and product acceptance.

## Choose one execution mode

Record the choice before dispatch. Use the harness's supported agent tools when available. Use a scripted adapter only when native tools are unavailable and the caller authorizes that execution method. A missing native capability is not permission to delegate through a prohibited CLI fallback.

- **Native execution** uses the installed `orchestrate` skill's plan/state lifecycle and `scripts/tools/native.ts` recorder. Read that skill's `references/native-execution.md` before creating the run. The recorder writes receipts; native tools execute agents. CLI kickoff/run, bridge transport, foreground-loop, automatic archive, and one-shot-dispatcher instructions below apply only to scripted execution.
- **Scripted execution** uses upstream plan/state and the chosen harness adapter's loop. Run its preflight before kickoff. Use a writable installation for dependencies. Follow the shell tool's process handle after a wait timeout; a timeout does not imply the process stopped. Never start a second loop while the first is alive.
- **Poteto entry point** keeps the upstream playbook's decomposition, bounded subagent briefs, context reduction, and proportional verification guidance. For native execution, route its lifecycle bookkeeping to the installed `orchestrate` skill above instead of also operating `scripts/orch` or a second `children.tsv` task store. If that set is absent, report the required `pstack-sync --set orchestrate` installation; do not mutate shared skills or invent a replacement scheduler. Existing Poteto-store runs retain their backend until all writers are quiescent and an explicit handoff selects a new run.

One run has one lifecycle backend. Task status belongs in `state.json`, work definitions in `plan.json`, and results in `handoffs/`. Tickets link to these records or project them; tickets are not a second independently edited task state. The dashboard is a derived view, never an execution or approval authority.

## Establish connectivity and ownership

Keep a stable run ID, logical task names, and logical parent in durable metadata. Record the real harness, execution-handle kind, returned handle, attempt ID, and actual parent when the tool provides it. A thread, subagent, and tool call are different identities. A retained thread may own several sequential work units. Do not fabricate thread links or an execution ID to fit another adapter.

The invoking dispatcher normally remains the delivery and approval relay. Add a separate execution root only for independently owned work or another required environment. Name one lifecycle writer for each workspace, one code writer per shared path, and one execution owner for each writable target. These roles can belong to different agents. Independent reviewers report evidence; they do not become additional delivery authorities.

Every brief names its dispatcher, task, logical parent, write ownership, exact code/input references, expected output, completion path, and stop conditions. Choose one completion path per child, a reply or collection, rather than waiting after requesting a reply. Record returned handles immediately. Messages do not transfer files, unpushed commits, services, credentials, or leases. Obtain a receiver receipt for transferred code and inputs before executing against them.

### Make run membership visible

Allocate a unique run ID once before dispatch and persist it with the dispatcher handle. Preserve it through compaction, retries, nested delegation, and coordinator handoff. A separate run gets a new ID even for the same goal. Native execution uses the immutable `native.json.runId`; generate a UUID for a new run. Scripted adapters retain their persisted run tag. These are coordinator identities, not invented harness execution IDs.

Prefix every dispatcher, execution root, worker, subplanner, and verifier name with the same run identifier. Use the native recorder's derived `naming` output, or the scripted adapter's existing run-tag prefix. For example, `[orch-843a13a480] worker · build`. Keep the prefix when a title is shortened or customized. A retained agent keeps its run prefix across sequential tasks; task and attempt identities stay in the receipts. Nested dispatch inherits the run ID rather than creating an unrelated run.

Before launch, put the run identifier, dispatcher handle/link, logical parent, task, and canonical state location at the start of the brief. Set the supported title/name/description field on the launch call. After launch, record the real returned handle and check the visible name when inspection is available. Repair a missing prefix with a supported rename tool. If naming or inspection is unavailable, put the prefix in the task description and brief, and record that limitation in an observation. Do not spawn a replacement solely to repair a name.

Harness profiles must map these launch, inspection, and rename capabilities from observed tools. Amp uses `create_thread.title` for threads and `Task.description` for blocking subagents. A Cursor cloud adapter uses its supported agent name; a Claude Code adapter uses its supported session title or subagent description. Record unsupported mappings rather than assuming all products expose the same API. Worktree and ticket names may repeat the prefix but do not establish ownership.

The recorded dispatcher and returned handles establish membership, regardless of whether the platform displays children or siblings. Names are a human-readable projection, not an authorization check. Match the full run ID and recorded handle before collecting a result; a matching prefix alone grants no ownership. Keep the portable rule in this extension and harness mappings in their profiles so upstream sync preserves both.

## Separate coordination files from code checkouts

Choose topology from observed filesystem access, not the harness name. A local agent can share a disk; a cloud agent may have an isolated image even under the same harness. Record the canonical run-workspace location and each worker's repository, checkout/worktree path or isolated environment, exact starting commit, output branch, and allowed write paths in the brief. The canonical workspace holds plan/state, native receipts, decisions, and collected handoffs. A worker's copy is a snapshot, not another writable authority.

- **Same filesystem:** keep one coordinator workspace and a separate worktree/branch per concurrent code writer. Workers return results or write only their assigned output files. The coordinator collects those results into canonical state. A shared Git object database does not share uncommitted edits, worktree files, processes, or environments. Assign one integration writer; never let parallel agents check out or reset the core worktree.
- **Separate images:** send a pinned published Git ref when authorized, or transfer a Git bundle, patch plus exact base, and required inputs with supported file-transfer tools. A branch name or commit ID is not a transfer. The receiver confirms that the commit, patches, and inputs exist and match before work starts. Return the worker's exact result and handoff by the same supported channel. Keep immutable evidence packages distinct from the coordinator's mutable state. Do not copy credentials or runtime leases.

For native code-writing runs, use the checked Git workflow in [native-execution.md](native-execution.md#prepare-parallel-code-work). Initialize `code`, reserve each batch with `prepare`, and collect the Git helper's receiver receipt before code execution. Worktree creation and isolated receipt checking use `scripts/tools/git-work.ts`. Keep resource names distinct for independent databases and ports. The recorder prevents conflicting reservations within the run, not outside it.

Native execution performs no file replication or Git publication. Its explicit `integrate` action merges and checks code locally. The coordinator still transfers and collects objects. The scripted backend's existing Git-state synchronization applies only in that mode and requires authorized writes to its state ref. Neither mode needs a new shared storage service. Persist a recovery checkpoint in an authorized durable location before retiring an isolated coordinator; changing the writer requires a quiescent handoff, not two writable replicas.

## Integrate through one parent branch

A parent draft pull request can be the integration point. Use the existing `prBase` and task `startingRef` fields where applicable, and name the integration branch, trunk branch, and integration writer in the brief. Start each worker from an observed exact commit of the integration branch or its declared dependency, not an assumed copy of the coordinator's current checkout. A draft pull request is a review surface, not permission to push, merge, or deploy.

Collect worker commits or patches without moving the core checkout. Check their base, changed paths, and evidence against the task's ownership. Serialize integrations into the parent branch. Disjoint files reduce conflicts but do not remove semantic dependencies. For overlapping changes, sequence the tasks or assign the overlap to one writer. Resolve conflicts at integration, rerun the affected checks, and bind independent review to the resulting exact code. Do not carry a pre-conflict verification claim onto changed code.

Keep integration ahead of unrelated feature work. Give each workstream small, completed batches instead of waiting for a whole lane to finish. Native `inspect` derives dependency readiness, reserved assignments, and the integration queue from canonical metadata. A collected result does not satisfy a code dependency until integration succeeds. Use the resulting exact commit as the dependent worker's base. Native integration preserves worker ancestry, tests a detached candidate, and advances the designated unoccupied branch with an expected-head check. Keep published lane history intact.

After the integrated candidate meets its declared acceptance, update it against trunk according to repository policy, run the affected final checks, and report readiness. Only an authorized delivery action moves the parent branch into trunk. Deleting worker branches and archiving agents are separate authorized cleanup actions; first confirm no retained owner still has active work. Preserve the receipts and failed evidence needed to resume or audit the run.

## Bound context and resume from files

Delegate bulky, bounded investigation or an independently owned slice when isolation removes material context from the parent. Give file pointers and an output contract. Return the conclusion, exact evidence paths, exclusions, and blockers instead of a transcript. The parent integrates results and owns the outcome. Keep tasks needing the current checkout in that environment; a new phase alone does not require a new thread.

Before compaction or stopping, persist collected handoffs and the next unresolved action. On restart, read plan/state, identity metadata, authoritative scope, and outstanding handoffs first. Verify current code/input hashes, owners, running attempts, and any interrupted writes before resuming. Inspect native handles through their original tool. An unknown outcome calls for reconciliation, not an automatic respawn. Confirm a writer has stopped before transferring ownership. Archive is not cancellation.

## Carry decisions without recreating consent gates

Keep the authoritative human source, scope revision, exclusions, and superseded source in the run's brief or decision document. A newer preparation update is not a new approval requirement. Before an affected side effect, the executor records which revision, exact code, target, and owner govern it. Explicit acknowledgment is needed when changed instructions reach an active remote owner or ownership transfers, not for every metadata update or read-only investigation. A delivered message is not proof that the owner consumed it.

Preserve independent security holds, access checks, exact-code evidence, single-writer ownership, and authorization stops. Superseding an obsolete consent hold cannot clear a security hold. Approval records describe authorization; a recorder is not a security boundary. Unknown write outcomes must be reconciled before retry. Keep publication, deployments, and shared configuration changes within their own authorized scope.

## Prove the outcome and finish

Before dispatch, use each task's `acceptance` and `verify` fields to name the risky behavior, cheapest decisive check, required evidence, and completion condition. Start with a small real user workflow. Separate candidate correctness, baseline preservation, and performance comparison. Generic suites prove only their stated coverage.

Workers run cheap deterministic checks. Use independent exact-code review for lifecycle, security, or other judgment-heavy changes. Rerun checks affected by a fix, retain unrelated valid evidence, and run the broader final suite once on the integrated candidate. After two attempts fail the same check, diagnose the shared premise or report the bounded blocker instead of repeating the loop. Do not recursively review a review or keep revisiting unchanged metadata to delay delivery.

A verifier's label describes evidence quality, not publication or business acceptance. Preserve raw failures and superseded receipts. Claim publication only with repository, remote ref, and observed exact commit. Claim product acceptance only with the requested feature's exact output and exercised interaction. Once the acceptance checks pass or a genuine external blocker remains, report the actual delivery state and remaining action.

For executable handoffs, include all transitive replay inputs, exact code and patches, literal expectations, commands/exits, and scope exclusions. Replay from an empty extraction without sibling files or rescue downloads. Label incremental packages with their prerequisites. Ordinary research handoffs need evidence links, not executable bundles. Keep credentials and runtime leases out of both.

## Update the workflow

The set declares portable additions and entry-point pointers. Harness transforms remain separate. Review stale ports, seed conflicts, and changed upstream instructions before adopting an update. A quiet repeat sync does not resolve an earlier seed conflict. Record the pack revision, upstream commit, effective transformations, and installed hashes from the sync manifest. Validate fresh install, repeat sync, upstream update, and extension survival in a disposable directory before changing shared installations.
