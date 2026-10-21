import { closeSync, existsSync, fsyncSync, mkdirSync, openSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { createHash, randomUUID } from "node:crypto";
import { dirname, join, resolve } from "node:path";
import { z } from "zod/v3";
import { parsePlanJson, parseStateJson, type Plan, type PlanTask, type State } from "../schemas.ts";
import { plannedBranchForTask } from "../core/branches.ts";
import { parseHandoffBranch, parseHandoffFailureMode, parseHandoffPrNumber, parseHandoffVerification } from "../core/handoff.ts";
import { Assignment, CodeConfig, Commit, PathPatterns, Receiver, RefUpdate, applyRefUpdate, buildCandidate, checkBranch, checkCommit, checkRefUpdate, checkRepository, checkScope, contains, git, receive, scopesOverlap } from "./git-work.ts";

const text = z.string().min(1);
const Handle = z.object({ kind: z.enum(["thread", "subagent", "tool-call"]), harness: text, id: text }).strict();
const Scope = z.object({ reference: text, revision: text }).strict();
const Dispatch = z.object({
  task: text, attemptId: text, handle: Handle,
  coordinator: Handle.nullable(), actualParent: Handle.nullable(), logicalParent: text.nullable(),
  preparationId: text.optional(),
}).strict();
const Completion = z.object({ result: z.enum(["finished", "error", "cancelled"]), body: text }).strict();
const CompletionDigest = Completion.omit({ body: true }).extend({ bodyHash: text }).strict();
const Attempt = Dispatch.extend({
  observations: z.array(text), completion: CompletionDigest.nullable(),
  verificationTarget: z.object({ task: text, attemptId: text }).strict().nullable(),
  resultCommit: Commit.nullable().default(null),
}).strict();
const Preparation = Assignment.extend({
  task: text, environment: z.enum(["worktree", "isolated"]), resources: z.array(text),
  allowed: PathPatterns, forbidden: PathPatterns, requiredCommits: z.array(Commit),
  scope: Scope, taskHash: text, requestHash: text,
  receiver: Receiver.nullable(), releaseReason: text.nullable(),
}).strict();
const Integration = z.object({
  attemptId: text, resultCommit: Commit, parentCommit: Commit, candidateCommit: Commit,
  requestHash: text,
  checks: z.array(z.object({ command: text, timeoutSeconds: z.number(), exitCode: z.literal(0), stdout: z.string(), stderr: z.string() }).strict()),
}).strict();
const Metadata = z.object({
  version: z.literal(1), mode: z.literal("native"), runId: text,
  dispatcher: Handle, deliveryOwner: Handle, lifecycleWriter: text, scope: Scope,
  revision: z.number().int().nonnegative(), planHash: text, stateHash: text,
  attempts: z.array(Attempt),
  code: CodeConfig.nullable().default(null),
  preparations: z.array(Preparation).default([]), integrations: z.array(Integration).default([]),
}).strict();
const common = { expectedRevision: z.number().int().nonnegative(), writer: text };
const Request = z.discriminatedUnion("action", [
  z.object({ action: z.literal("init"), ...common, runId: text, dispatcher: Handle, deliveryOwner: Handle, scope: Scope, code: CodeConfig.optional() }).strict(),
  z.object({ action: z.literal("reconcile"), ...common, scope: Scope.optional() }).strict(),
  z.object({ action: z.literal("prepare"), ...common, id: text, task: text, baseCommit: Commit, branch: text, environment: z.enum(["worktree", "isolated"]), resources: z.array(text) }).strict(),
  z.object({ action: z.literal("received"), ...common, receipt: Receiver }).strict(),
  z.object({ action: z.literal("release"), ...common, id: text, reason: text }).strict(),
  z.object({ action: z.literal("integrate"), ...common, attemptId: text, expectedHead: Commit }).strict(),
  z.object({ action: z.literal("dispatch"), ...common, receipt: Dispatch }).strict(),
  z.object({ action: z.literal("observe"), ...common, attemptId: text, note: text }).strict(),
  z.object({ action: z.literal("complete"), ...common, attemptId: text, receipt: Completion, resultCommit: Commit.optional() }).strict(),
  z.object({ action: z.literal("recover"), ...common }).strict(),
  z.object({ action: z.literal("preflight") }).strict(),
  z.object({ action: z.literal("inspect") }).strict(),
]);
type Native = z.infer<typeof Metadata>;
type Action = z.infer<typeof Request>;
const Journal = z.object({
  version: z.literal(1), writer: text, revision: z.number().int(), requestHash: text,
  files: z.array(z.object({ path: text, before: z.string().nullable(), after: z.string() }).strict()),
  refUpdate: RefUpdate.optional(),
}).strict();

function read(path: string): string | null {
  return existsSync(path) ? readFileSync(path, "utf8") : null;
}
function hash(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}
function json(value: unknown): string { return JSON.stringify(value, null, 2) + "\n"; }
function equal(a: unknown, b: unknown): boolean { return JSON.stringify(a) === JSON.stringify(b); }
function must(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}
function atomic(path: string, bytes: string): void {
  mkdirSync(dirname(path), { recursive: true });
  const tmp = `${path}.${randomUUID()}.tmp`;
  const fd = openSync(tmp, "wx", 0o600);
  try { writeFileSync(fd, bytes); fsyncSync(fd); } finally { closeSync(fd); }
  renameSync(tmp, path);
  const directory = openSync(dirname(path), "r");
  try { fsyncSync(directory); } finally { closeSync(directory); }
}
function removeDurably(path: string): void {
  rmSync(path);
  const fd = openSync(dirname(path), "r");
  try { fsyncSync(fd); } finally { closeSync(fd); }
}
function dependencies(task: PlanTask): string[] {
  return [...new Set([...(task.dependsOn ?? []), ...(task.type === "verifier" ? [task.verifies] : [])])];
}
function successful(workspace: string, target: State["tasks"][number] | undefined): void {
  must(target?.status === "handed-off" && target.resultStatus === "finished" && !target.failureMode && target.verification !== "verifier-failed" && target.verification !== "verifier-blocked", `unmet dependency: ${target?.name ?? "missing task"}`);
  must(target.handoffPath && existsSync(join(workspace, target.handoffPath)), `missing dependency handoff: ${target.name}`);
  const body = readFileSync(join(workspace, target.handoffPath), "utf8");
  const status = /^##\s+Status\s*\r?\n\s*`?(success|partial|blocked|error)\b/m.exec(body)?.[1];
  must(status === "success" || (!status && target.type === "verifier" && ["live-ui-verified", "unit-test-verified", "type-check-only"].includes(target.verification ?? "")), `dependency did not report success: ${target.name}`);
}
function dispatchable(workspace: string, state: State, meta: Native, def: PlanTask): void {
  must((!state.andon || state.andon.cleared) && !existsSync(join(workspace, "andon.json")), "Andon hold blocks dispatch");
  const row = state.tasks.find(t => t.name === def.name);
  must(row && ["pending", "error", "cancelled"].includes(row.status), "duplicate dispatch for active or finished task");
  const previous = meta.attempts.filter(a => a.task === def.name);
  must(previous.every(a => a.completion), "unknown previous outcome; reconcile before retry");
  must(previous.length < (def.maxAttempts ?? 3), "maxAttempts reached");
  for (const dep of dependencies(def)) successful(workspace, state.tasks.find(t => t.name === dep));
}
function held(meta: Native, preparation: z.infer<typeof Preparation>): boolean {
  return preparation.releaseReason === null && !meta.attempts.some(a => a.preparationId === preparation.id && a.completion);
}
function requiredCode(state: State, meta: Native, def: PlanTask): string[] {
  return dependencies(def).map(dep => {
    const target = state.tasks.find(t => t.name === dep);
    const attempt = meta.attempts.find(a => a.attemptId === target?.runId);
    must(attempt?.resultCommit, `dependency code unavailable: ${dep}`);
    if (def.type === "verifier") return attempt.resultCommit;
    if (target?.type === "verifier") {
      const verified = meta.integrations.find(i => i.attemptId === attempt.verificationTarget?.attemptId);
      must(verified, `dependency awaits integration: ${dep}`);
      return verified.candidateCommit;
    }
    const integrated = meta.integrations.find(i => i.attemptId === attempt.attemptId);
    must(integrated, `dependency awaits integration: ${dep}`);
    return integrated.candidateCommit;
  });
}
function initial(plan: Plan, task: PlanTask): State["tasks"][number] {
  return {
    name: task.name, type: task.type, branch: plannedBranchForTask(plan, task),
    startingRef: task.startingRef ?? (task.type === "verifier" ? `orch/${plan.rootSlug}/${task.verifies}` : plan.baseBranch),
    dependsOn: dependencies(task), agentId: null, runId: null, parentAgentId: null,
    status: "pending", resultStatus: null, handoffPath: null, startedAt: null,
    finishedAt: null, lastUpdate: null, note: null, slackTs: task.slackTs ?? null,
    prNumber: null, failureMode: null, verification: null,
  };
}
function reconcile(plan: Plan, state: State): void {
  must(state.rootSlug === plan.rootSlug, "rootSlug is immutable");
  for (const def of plan.tasks ?? []) {
    const row = state.tasks.find(t => t.name === def.name);
    if (!row) state.tasks.push(initial(plan, def));
    else {
      must(row.type === def.type, `task type changed: ${def.name}`);
      if (row.status === "pending") row.dependsOn = dependencies(def);
    }
  }
  for (const row of state.tasks) {
    if (!(plan.tasks ?? []).some(t => t.name === row.name) && row.status === "pending" && !row.adHoc) {
      row.status = "pruned";
      row.note = "removed from plan.json";
    }
  }
}
function coherent(state: State, meta: Native): void {
  must(new Set(state.tasks.map(t => t.name)).size === state.tasks.length, "duplicate task state");
  for (const attempt of meta.attempts) must(state.tasks.some(t => t.name === attempt.task), `missing state for attempt: ${attempt.attemptId}`);
  for (const row of state.tasks) {
    const attempts = meta.attempts.filter(a => a.task === row.name);
    const latest = attempts.at(-1);
    if (latest || row.agentId || row.runId || row.status === "running") {
      must(latest && row.agentId === latest.handle.id && row.runId === latest.attemptId && row.parentAgentId === (latest.coordinator?.id ?? null), `unknown execution outcome: ${row.name}; reconcile the actual receipt, do not dispatch`);
      must(latest.completion ? row.status === (latest.completion.result === "finished" ? "handed-off" : latest.completion.result) && row.resultStatus === latest.completion.result && row.handoffPath === `handoffs/${hash(latest.attemptId)}.md` : row.status === "running", `lifecycle conflict: ${row.name}; reconcile the actual receipt`);
    }
  }
}
function handoffProblems(workspace: string, meta: Native): string[] {
  return meta.attempts.flatMap(attempt => {
    if (!attempt.completion) return [];
    const bytes = read(join(workspace, `handoffs/${hash(attempt.attemptId)}.md`));
    if (bytes === null) return [`missing handoff: ${attempt.task}`];
    return hash(bytes) === attempt.completion.bodyHash ? [] : [`conflicting handoff: ${attempt.task}`];
  });
}
function replay(workspace: string, transaction: z.infer<typeof Journal>): void {
  for (const file of transaction.files) {
    must(file.path === "state.json" || file.path === "native.json" || /^handoffs\/[a-f0-9]{64}\.md$/.test(file.path), "invalid journal path");
    const current = read(join(workspace, file.path));
    must(current === file.before || current === file.after, `transaction conflict: ${file.path}; reconcile manually`);
  }
  if (transaction.refUpdate) {
    if (checkRefUpdate(transaction.refUpdate) === "before") {
      const stateBytes = read(join(workspace, "state.json"));
      const hold = stateBytes && parseStateJson(stateBytes, "state.json").andon;
      must(!existsSync(join(workspace, "andon.json")) && (!hold || hold.cleared), "Andon hold blocks pending ref update");
    }
    applyRefUpdate(transaction.refUpdate);
  }
  for (const file of transaction.files) {
    if (read(join(workspace, file.path)) !== file.after) atomic(join(workspace, file.path), file.after);
  }
  removeDurably(join(workspace, "native.transaction.json"));
}
function commit(workspace: string, meta: Native, action: Action, files: { path: string; after: string }[], refUpdate?: z.infer<typeof RefUpdate>): void {
  const transaction = Journal.parse({ version: 1, writer: meta.lifecycleWriter, revision: meta.revision, requestHash: hash(json(action)),
    files: files.map(f => ({ ...f, before: read(join(workspace, f.path)) })), refUpdate });
  atomic(join(workspace, "native.transaction.json"), json(transaction));
  replay(workspace, transaction);
}
function locked<T>(workspace: string, work: () => T): T {
  const lock = join(workspace, "native.lock");
  must(!existsSync(lock), "native writer lock held; after a crash, confirm the recorded PID has exited before manually removing native.lock");
  const fd = openSync(lock, "wx", 0o600);
  try {
    writeFileSync(fd, json({ pid: process.pid })); fsyncSync(fd);
    return work();
  } finally { closeSync(fd); rmSync(lock); }
}

export function recordNative(workspacePath: string, input: unknown): unknown {
  const action = Request.parse(input);
  const workspace = resolve(workspacePath);
  must(existsSync(workspace), "workspace must exist and contain plan.json");
  if (action.action === "inspect" || action.action === "preflight") return inspect(workspace);
  locked(workspace, () => mutate(workspace, action));
  return inspect(workspace);
}

function inspect(workspace: string): unknown {
  const transactionBytes = read(join(workspace, "native.transaction.json"));
  const transaction = transactionBytes ? Journal.parse(JSON.parse(transactionBytes)) : null;
  const pendingTransaction = transaction !== null;
  const metaBytes = read(join(workspace, "native.json"));
  const stateBytes = read(join(workspace, "state.json"));
  const planBytes = read(join(workspace, "plan.json"));
  must(planBytes, "missing plan.json");
  const plan = parsePlanJson(planBytes, "plan.json");
  const meta = metaBytes ? Metadata.parse(JSON.parse(metaBytes)) : null;
  const state = stateBytes ? parseStateJson(stateBytes, "state.json") : null;
  const problems: string[] = [];
  if (existsSync(join(workspace, "native.lock"))) problems.push("native.lock exists; do not reclaim it until its recorded PID has exited");
  if (existsSync(join(workspace, "andon.json"))) problems.push("Andon file hold requires operator resolution");
  if (pendingTransaction) problems.push("interrupted write requires recover with the transaction's expectedRevision and writer");
  if (!meta) problems.push("native execution not initialized");
  if (meta && (meta.planHash !== hash(planBytes) || !stateBytes || meta.stateHash !== hash(stateBytes))) problems.push("unknown write requires explicit reconciliation");
  if (meta && state) {
    try { coherent(state, meta); } catch (error) { problems.push(String(error)); }
    problems.push(...handoffProblems(workspace, meta));
    for (const row of state.tasks) {
      if (row.status === "running") problems.push(`unknown execution outcome: ${row.name}; obtain observation or handoff from native tools, do not retry`);
    }
    if (state.andon && !state.andon.cleared) problems.push("Andon hold requires operator resolution");
  }
  const prefix = meta ? `orch-${hash(meta.runId).slice(0, 10)}` : null;
  const naming = prefix ? {
    prefix,
    dispatcherTitle: `[${prefix}] dispatcher · ${plan.rootSlug}`.slice(0, 100),
    rootTitle: `[${prefix}] root · ${plan.rootSlug}`.slice(0, 100),
    tasks: (plan.tasks ?? []).map(task => ({ task: task.name, title: `[${prefix}] ${task.type} · ${task.name}`.slice(0, 100) })),
  } : null;
  const readiness = meta && state ? (plan.tasks ?? []).map(task => {
    try {
      must(!problems.some(problem => !problem.startsWith("unknown execution outcome:")), "resolve run integrity or security holds first");
      dispatchable(workspace, state, meta, task);
      if (meta.code) {
        requiredCode(state, meta, task);
        for (const preparation of meta.preparations.filter(p => held(meta, p))) {
          must(preparation.task !== task.name, "inputs reserved; reconcile receiver or launch receipt before retry");
          must(task.type === "verifier" || !scopesOverlap(task.pathsAllowed ?? [], preparation.allowed), `write ownership overlaps: ${preparation.task}`);
        }
      }
      return { task: task.name, ready: true, reason: "dependencies collected; prepare exact inputs before launch" };
    } catch (error) { return { task: task.name, ready: false, reason: error instanceof Error ? error.message : String(error) }; }
  }) : [];
  const integrationQueue = meta ? meta.attempts.filter(a => a.resultCommit && !a.verificationTarget && !meta.integrations.some(i => i.attemptId === a.attemptId)).map(a => ({ task: a.task, attemptId: a.attemptId, resultCommit: a.resultCommit })) : [];
  const assignments = meta ? meta.preparations.filter(p => held(meta, p)).map(p => ({ task: p.task, environment: p.environment,
    assignment: Assignment.strip().parse(p), codeReady: p.receiver !== null && equal(p.scope, meta.scope)
      && p.taskHash === hash(json(plan.tasks?.find(t => t.name === p.task)))
      && !problems.some(problem => !problem.startsWith("unknown execution outcome:")) })) : [];
  return { metadata: meta, state, naming, readiness, assignments, integrationQueue, pendingTransaction,
    recovery: transaction ? { action: "recover", writer: transaction.writer, expectedRevision: transaction.revision - 1 } : null,
    problems, safeNextAction: problems.length ? "reconcile receipts and holds; do not automatically spawn or retry" : "record an explicit native receipt" };
}

function mutate(workspace: string, action: Exclude<Action, { action: "inspect" | "preflight" }>): unknown {
  const journalPath = join(workspace, "native.transaction.json");
  if (action.action === "recover") {
    const bytes = read(journalPath);
    must(bytes, "no interrupted transaction");
    const transaction = Journal.parse(JSON.parse(bytes));
    must(transaction.writer === action.writer && transaction.revision === action.expectedRevision + 1, "recovery writer/revision conflict");
    replay(workspace, transaction);
    return inspect(workspace);
  }
  const interrupted = read(journalPath);
  if (interrupted) {
    const transaction = Journal.parse(JSON.parse(interrupted));
    must(transaction.writer === action.writer && transaction.requestHash === hash(json(action)), "interrupted write requires explicit recover or identical request");
    replay(workspace, transaction);
    return inspect(workspace);
  }
  const planBytes = read(join(workspace, "plan.json"));
  must(planBytes, "missing plan.json");
  const plan = parsePlanJson(planBytes, "plan.json");
  const stateBytes = read(join(workspace, "state.json"));
  const state: State = stateBytes ? parseStateJson(stateBytes, "state.json") : { rootSlug: plan.rootSlug, ...(plan.runTag ? { runTag: plan.runTag } : {}), tasks: [], attention: [] };
  const metaBytes = read(join(workspace, "native.json"));
  let meta: Native;
  if (!metaBytes) {
    must(action.action === "init" && action.expectedRevision === 0, "init with expectedRevision 0 required");
    must(!state.tasks.some(t => t.agentId || t.runId || t.status !== "pending"), "cannot adopt previously executed workspace");
    meta = Metadata.parse({ version: 1, mode: "native", runId: action.runId,
      dispatcher: action.dispatcher, deliveryOwner: action.deliveryOwner, lifecycleWriter: action.writer,
      scope: action.scope, revision: 0, planHash: hash(planBytes), stateHash: hash(stateBytes ?? ""), attempts: [], code: action.code ?? null });
    if (meta.code) {
      checkRepository(meta.code.repository, plan.repoUrl);
      git(meta.code.repository, "check-ref-format", meta.code.integrationRef);
      checkCommit(meta.code.repository, git(meta.code.repository, "rev-parse", meta.code.integrationRef));
    }
  } else {
    meta = Metadata.parse(JSON.parse(metaBytes));
    must(meta.lifecycleWriter === action.writer, "lifecycle writer conflict");
    if (action.action === "init") {
      must(meta.runId === action.runId && equal(meta.dispatcher, action.dispatcher) && equal(meta.deliveryOwner, action.deliveryOwner) && equal(meta.scope, action.scope), "run identity or owner conflict");
      must(equal(meta.code, action.code ?? null), "code configuration is immutable");
    }
    must(meta.planHash === hash(planBytes) || action.action === "reconcile", "plan changed; reconcile first");
    must(stateBytes && (meta.stateHash === hash(stateBytes) || action.action === "reconcile"), "unknown write requires explicit reconciliation");
  }
  coherent(state, meta);
  const damagedHandoffs = handoffProblems(workspace, meta);
  must(damagedHandoffs.length === 0, damagedHandoffs.join("; "));
  const unchangedReceipt = action.action === "dispatch"
    ? meta.attempts.some(a => equal(Dispatch.parse(aWithoutDetails(a)), action.receipt))
    : action.action === "complete"
      ? meta.attempts.some(a => a.attemptId === action.attemptId && a.resultCommit === (action.resultCommit ?? null) && equal(a.completion, { result: action.receipt.result, bodyHash: hash(action.receipt.body) }))
      : action.action === "prepare" ? meta.preparations.some(p => p.requestHash === hash(json(action)))
      : action.action === "received" ? meta.preparations.some(p => equal(p.receiver, action.receipt))
      : action.action === "integrate" ? meta.integrations.some(i => i.requestHash === hash(json(action)))
      : action.action === "release" ? meta.preparations.some(p => p.id === action.id && p.releaseReason === action.reason)
      : action.action === "init" && metaBytes !== null;
  if (unchangedReceipt) return inspect(workspace);
  must(action.expectedRevision === meta.revision, "expectedRevision conflict");
  const files: { path: string; after: string }[] = [];
  let refUpdate: z.infer<typeof RefUpdate> | undefined;
  if (action.action === "init" || action.action === "reconcile") {
    for (const attempt of meta.attempts) {
      if (!attempt.verificationTarget || attempt.completion) continue;
      const def = plan.tasks?.find(t => t.name === attempt.task);
      must(def?.type === "verifier" && def.verifies === attempt.verificationTarget.task, `cannot retarget active verifier: ${attempt.task}`);
    }
    reconcile(plan, state);
    if (action.action === "reconcile" && action.scope) meta.scope = action.scope;
  } else if (action.action === "prepare") {
    const config = meta.code;
    must(config, "initialize a code-enabled run before preparing work");
    const def = plan.tasks?.find(t => t.name === action.task);
    must(def, "unknown task");
    dispatchable(workspace, state, meta, def);
    checkRepository(config.repository, plan.repoUrl);
    checkCommit(config.repository, action.baseCommit);
    checkBranch(config.repository, action.branch);
    must(`refs/heads/${action.branch}` !== config.integrationRef, "worker cannot own integration branch");
    must(!meta.preparations.some(p => p.id === action.id), "preparation identity conflict");
    const allowed = PathPatterns.parse(def.type === "verifier" ? [] : def.pathsAllowed ?? []);
    must(def.type === "verifier" || allowed.length > 0, "code writer requires pathsAllowed in plan.json");
    const requiredCommits = requiredCode(state, meta, def);
    for (const commit of requiredCommits) must(contains(config.repository, commit, action.baseCommit), "base does not contain required dependency commit");
    if (def.type === "verifier") {
      const target = meta.attempts.find(a => a.attemptId === state.tasks.find(t => t.name === def.verifies)?.runId);
      must(target?.resultCommit === action.baseCommit, "verifier must start at exact target result commit");
    } else {
      must(contains(config.repository, action.baseCommit, git(config.repository, "rev-parse", config.integrationRef)), "worker base must belong to integration history");
    }
    for (const other of meta.preparations.filter(p => held(meta, p))) {
      must(other.task !== action.task, "task already reserved; reconcile launch before retry");
      must(other.branch !== action.branch, "branch already reserved");
      must(!scopesOverlap(allowed, other.allowed), `write ownership overlaps: ${other.task}`);
      must(!action.resources.some(resource => other.resources.includes(resource)), `resource occupied: ${other.task}`);
    }
    meta.preparations.push({ id: action.id, task: action.task, repository: plan.repoUrl,
      baseCommit: action.baseCommit, branch: action.branch, environment: action.environment,
      resources: action.resources, allowed, forbidden: def.pathsForbidden ?? [], requiredCommits,
      scope: meta.scope, taskHash: hash(json(def)), requestHash: hash(json(action)), receiver: null, releaseReason: null });
  } else if (action.action === "received") {
    const preparation = meta.preparations.find(p => p.id === action.receipt.id);
    must(preparation && held(meta, preparation), "no active preparation for receiver receipt");
    must(equal(Assignment.strip().parse(preparation), Assignment.strip().parse(action.receipt)), "receiver receipt does not match pinned assignment");
    must(!preparation.receiver, "receiver receipt conflict");
    if (preparation.environment === "worktree") {
      must(equal(receive(action.receipt.checkout, Assignment.strip().parse(preparation)), action.receipt), "local receiver receipt changed");
      must(!meta.preparations.some(p => p.id !== preparation.id && held(meta, p) && p.environment === "worktree" && p.receiver?.checkout === action.receipt.checkout), "checkout already owned");
    }
    preparation.receiver = action.receipt;
  } else if (action.action === "release") {
    const preparation = meta.preparations.find(p => p.id === action.id);
    must(preparation && !preparation.releaseReason, "no active preparation");
    must(!meta.attempts.some(a => a.preparationId === preparation.id), "dispatched preparation requires actual completion, not release");
    preparation.releaseReason = action.reason;
  } else if (action.action === "integrate") {
    const config = meta.code;
    must(config, "not a code-enabled run");
    must((!state.andon || state.andon.cleared) && !existsSync(join(workspace, "andon.json")), "Andon hold blocks integration");
    const attempt = meta.attempts.find(a => a.attemptId === action.attemptId);
    must(attempt?.resultCommit && !attempt.verificationTarget, "no worker result commit to integrate");
    const row = state.tasks.find(t => t.runId === attempt.attemptId);
    successful(workspace, row);
    for (const verifier of plan.tasks ?? []) {
      if (verifier.type === "verifier" && verifier.verifies === attempt.task) successful(workspace, state.tasks.find(t => t.name === verifier.name));
    }
    must(!meta.integrations.some(i => i.attemptId === action.attemptId), "attempt already integrated");
    const preparation = meta.preparations.find(p => p.id === attempt.preparationId);
    must(preparation && equal(preparation.scope, meta.scope), "scope changed; reconcile result before integration");
    must(preparation.taskHash === hash(json(plan.tasks?.find(t => t.name === attempt.task))), "task changed; result needs a new preparation");
    checkRepository(config.repository, plan.repoUrl);
    checkScope(config.repository, preparation.baseCommit, attempt.resultCommit, preparation.allowed, preparation.forbidden);
    let built: ReturnType<typeof buildCandidate>;
    try {
      built = buildCandidate(config, action.expectedHead, attempt.resultCommit);
    } catch (error) {
      const failure = { request: action, error: error instanceof Error ? error.message : String(error) };
      atomic(join(workspace, "integration-failures", `${hash(json(failure))}.json`), json(failure));
      throw error;
    }
    checkScope(config.repository, action.expectedHead, built.candidate, preparation.allowed, preparation.forbidden);
    refUpdate = { repository: config.repository, ref: config.integrationRef, before: action.expectedHead, after: built.candidate };
    checkRefUpdate(refUpdate);
    meta.integrations.push(Integration.parse({ attemptId: attempt.attemptId, resultCommit: attempt.resultCommit,
      parentCommit: action.expectedHead, candidateCommit: built.candidate, checks: built.checks, requestHash: hash(json(action)) }));
  } else if (action.action === "dispatch") {
    const receipt = action.receipt;
    const row = state.tasks.find(t => t.name === receipt.task);
    const def = plan.tasks?.find(t => t.name === receipt.task);
    must(row && def, "unknown task");
    dispatchable(workspace, state, meta, def);
    must(!meta.attempts.some(a => a.attemptId === receipt.attemptId), "attempt identity conflict");
    must(!meta.attempts.some(a => equal(a.handle, receipt.handle) && !a.completion), "execution handle still owns an active attempt");
    const previous = meta.attempts.filter(a => a.task === row.name);
    if (meta.code) {
      const preparation = meta.preparations.find(p => p.id === receipt.preparationId);
      must(preparation && preparation.task === row.name && held(meta, preparation), "prepare and reserve exact inputs before dispatch");
      must(!meta.attempts.some(a => a.preparationId === preparation.id), "preparation already dispatched");
      must(preparation.taskHash === hash(json(def)) && equal(preparation.scope, meta.scope), "preparation is stale; reconcile before launch");
      must(preparation.environment === "isolated" || preparation.receiver, "receive local inputs before launching code work");
      row.startingRef = preparation.baseCommit;
      row.branch = preparation.branch;
    }
    let verificationTarget: z.infer<typeof Attempt>["verificationTarget"] = null;
    if (def.type === "verifier") {
      const target = state.tasks.find(t => t.name === def.verifies);
      must(target?.runId, "missing verifier target attempt");
      verificationTarget = { task: target.name, attemptId: target.runId };
      if (!meta.code && !def.startingRef) row.startingRef = target.branch;
    }
    meta.attempts.push({ ...receipt, verificationTarget, observations: [], completion: null, resultCommit: null });
    Object.assign(row, { status: "running", agentId: receipt.handle.id, runId: receipt.attemptId,
      parentAgentId: receipt.coordinator?.id ?? null, startedAt: new Date().toISOString(),
      finishedAt: null, handoffPath: null, resultStatus: null, failureMode: null,
      verification: null, prNumber: null, attempts: previous.length + 1, note: null });
  } else {
    const attempt = meta.attempts.find(a => a.attemptId === action.attemptId);
    must(attempt, "unknown attempt");
    const row = state.tasks.find(t => t.name === attempt.task);
    must(row && row.runId === attempt.attemptId, "not the current attempt");
    must(!attempt.completion, "conflicting terminal receipt");
    if (action.action === "observe") {
      if (!attempt.observations.includes(action.note)) attempt.observations.push(action.note);
    } else {
      const receipt = action.receipt;
      if (meta.code && receipt.result === "finished") {
        const preparation = meta.preparations.find(p => p.id === attempt.preparationId);
        must(preparation?.receiver, "receiver must confirm pinned inputs before completion");
        must(action.resultCommit, "code completion requires an exact resultCommit");
        checkRepository(meta.code.repository, plan.repoUrl);
        checkScope(meta.code.repository, preparation.baseCommit, action.resultCommit, preparation.allowed, preparation.forbidden);
        if (attempt.verificationTarget) must(action.resultCommit === preparation.baseCommit, "verifier changed the code it reviewed");
        const reportedBranch = parseHandoffBranch(receipt.body);
        must(!reportedBranch || reportedBranch === preparation.branch, "handoff branch differs from assignment");
        attempt.resultCommit = action.resultCommit;
      } else must(!action.resultCommit, "resultCommit is only valid for finished code attempts");
      const path = `handoffs/${hash(attempt.attemptId)}.md`;
      const old = read(join(workspace, path));
      must(old === null || old === receipt.body, "conflicting handoff bytes");
      files.push({ path, after: receipt.body });
      attempt.completion = { result: receipt.result, bodyHash: hash(receipt.body) };
      Object.assign(row, { status: receipt.result === "finished" ? "handed-off" : receipt.result,
        resultStatus: receipt.result, finishedAt: new Date().toISOString(), handoffPath: path,
        branch: parseHandoffBranch(receipt.body) ?? row.branch,
        failureMode: parseHandoffFailureMode(receipt.body), verification: parseHandoffVerification(receipt.body),
        prNumber: parseHandoffPrNumber(receipt.body) });
      if (attempt.verificationTarget && row.verification) {
        const target = state.tasks.find(t => t.name === attempt.verificationTarget?.task);
        must(target?.runId === attempt.verificationTarget.attemptId, "verifier target attempt changed; reconcile exact code before collecting verdict");
        target.verification = row.verification;
        target.lastUpdate = row.finishedAt;
      }
    }
    row.lastUpdate = new Date().toISOString();
  }
  const afterState = json(parseStateJson(json(state), "state.json"));
  meta.revision++;
  meta.planHash = hash(planBytes); meta.stateHash = hash(afterState);
  files.push({ path: "state.json", after: afterState }, { path: "native.json", after: json(Metadata.parse(meta)) });
  commit(workspace, meta, action, files, refUpdate);
  return inspect(workspace);
}
function aWithoutDetails(attempt: z.infer<typeof Attempt>): z.infer<typeof Dispatch> {
  const { observations: _observations, completion: _completion, verificationTarget: _target, resultCommit: _commit, ...receipt } = attempt;
  return receipt;
}

if (import.meta.main) {
  try {
    const [workspace, request] = process.argv.slice(2);
    must(workspace && request, "usage: bun scripts/tools/native.ts <workspace> <request.json>");
    process.stdout.write(json(recordNative(workspace, JSON.parse(readFileSync(request, "utf8")))));
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  }
}
