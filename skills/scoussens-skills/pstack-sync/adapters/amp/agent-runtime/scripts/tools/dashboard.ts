#!/usr/bin/env bun
// Amp port: write a `dashboard` skill status record from an orchestrate run
// workspace and render it.
//
// Usage:
//   bun tools/dashboard.ts <workspace> [--out <html>] [--hosted] [--status-only]
//
// Reads `<workspace>/plan.json`, `state.json`, `handoffs/` and
// `attention.log`, writes `<workspace>/status.json` as a schema 2 record of
// `dashboard/references/status-contract.md` (one row per task in state.json;
// the owner is the task's thread), then runs the dashboard skill's
// `scripts/render_dashboard.py` on it. `--out` names the page (default
// `<workspace>/dashboard.html`), `--hosted` passes the renderer's hosted
// link check and keeps handoff links out of the record, `--status-only`
// writes the record and skips the render.
//
// The dashboard skill is found the way `core/runtime.ts` finds the adapter:
// `ORCHESTRATE_DASHBOARD_DIR`, else `<skills>/dashboard` beside this skill,
// else the newest `dashboard@<hash>` sibling in Amp's skill cache, else the
// pack layout relative to this file.
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, readFileSync, renameSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { agentUrl, isThreadId } from "../core/runtime.ts";

// ---------------------------------------------------------------------------
// The workspace files, typed to the fields this tool reads. The full shapes
// are `PlanSchema` and `StateSchema` in `scripts/schemas.ts`, which is not a
// port file and so is absent in the pack layout; the raw JSON is read here.
// ---------------------------------------------------------------------------

export type TaskStatus = "pending" | "running" | "handed-off" | "error" | "cancelled" | "pruned";
export type TaskType = "worker" | "subplanner" | "verifier";

export interface PlanTaskFile {
  name: string;
  type: TaskType;
  scopedGoal?: string;
  acceptance?: string[];
  dependsOn?: string[];
  verifies?: string;
  openPR?: boolean;
}

export interface PlanFile {
  goal?: string;
  summary?: string;
  rootSlug?: string;
  selfAgentId?: string;
  tasks?: PlanTaskFile[];
}

export interface StateTaskFile {
  name: string;
  type: TaskType;
  branch: string;
  dependsOn: string[];
  status: TaskStatus;
  agentId?: string | null;
  runId?: string | null;
  handoffPath?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  lastUpdate?: string | null;
  note?: string | null;
  adHoc?: boolean;
  prNumber?: number | null;
  failureMode?: string | null;
  verification?: string | null;
  resultStatus?: string | null;
}

export interface StateFile {
  rootSlug: string;
  tasks: StateTaskFile[];
  attention?: { at: string; message: string }[];
  andon?: {
    raisedAt?: string;
    raisedBy?: string;
    reason?: string;
    cleared?: boolean;
  };
}

/** The lines this tool reads from `handoffs/<task>.md`; see references/handoffs.md. */
export interface Handoff {
  /** Absolute path of the file read. */
  path: string;
  /** `## Status` value (`success`, `partial`, `blocked`) or the `Status:` word of a failure handoff. */
  status: string | null;
  /** `## Verification` value of a verifier handoff. */
  verification: string | null;
  /** `## Branch` value with backticks stripped. */
  branch: string | null;
  publication: PublicationReceipt | null;
}

export interface PublicationReceipt {
  repo: string;
  remote_ref: string;
  observed_commit_sha: string;
}

export interface WorkspaceSnapshot {
  workspace: string;
  plan: PlanFile;
  state: StateFile;
  handoffs: Map<string, Handoff>;
  native?: {
    runId: string;
    deliveryOwner: { kind: string; harness: string; id: string };
    scope: { reference: string; revision: string };
    attempts: { task: string; attemptId: string; handle: { kind: string; harness: string; id: string }; logicalParent: string | null }[];
  };
  /** `attention.log` lines, oldest first. */
  attention: string[];
}

// ---------------------------------------------------------------------------
// The record, typed to the contract's schema 2.
// ---------------------------------------------------------------------------

export type OwnerState = "active" | "waiting" | "blocked" | "unreachable" | "complete" | "closed";
export type WorkState =
  | "needs_decision"
  | "blocked"
  | "waiting"
  | "unknown"
  | "working"
  | "ready"
  | "awaiting_acceptance"
  | "delivered"
  | "no_change_needed"
  | "cancelled"
  | "deferred";
export type StageState = "verified" | "pending" | "blocked" | "not_requested";
export type StageKey =
  | "defined"
  | "researched"
  | "pr_readiness"
  | "code_publication"
  | "review"
  | "verification"
  | "deployment"
  | "business_acceptance";

export interface Stage {
  state: StageState;
  note: string;
  evidence: string[];
}

export interface Evidence {
  id: string;
  label: string;
  scope: string;
  result: "passed" | "failed" | "interrupted" | "observed";
  assessment: "accepted" | "limited" | "superseded";
  note: string;
  href: string;
  output: string;
}

export interface Work {
  state: WorkState;
  reason: string;
  summary?: string;
  evidence?: string[];
  receipt?: string;
}

export interface Row {
  id: string;
  title: string;
  owner: {
    id: string;
    label: string;
    state: OwnerState;
    href?: string;
    activity?: string;
    location?: string;
    handoff?: string;
    last_checked_at?: string;
  };
  work: Work;
  milestones: Partial<Record<StageKey, Stage>>;
  blocked_by: string[];
  blocker: string;
  next_action: string;
  done_when: string;
}

export interface Decision {
  id: string;
  text: string;
  recommendation: string;
  task_ids: string[];
  unblocks: string;
  discussion?: { owner_id: string; label: string; href: string };
}

export interface StatusRecord {
  schema_version: 2;
  run_id: string;
  title: string;
  goal?: string;
  updated_at: string;
  contract_version: string;
  harness_name: string;
  presentation: {
    destination: "local";
    local_path: string;
    coordinator_href?: string;
    interaction: string;
  };
  tasks: Row[];
  evidence: Evidence[];
  decisions: Decision[];
  history: string[];
}

// ---------------------------------------------------------------------------
// Reading the workspace
// ---------------------------------------------------------------------------

function readJson<T>(path: string, what: string): T {
  let text: string;
  try {
    text = readFileSync(path, "utf8");
  } catch (err) {
    throw new Error(`${what} not readable at ${path}: ${err instanceof Error ? err.message : String(err)}`);
  }
  try {
    return JSON.parse(text) as T;
  } catch (err) {
    throw new Error(`${what} at ${path} is not valid JSON: ${err instanceof Error ? err.message : String(err)}`);
  }
}

/** The first non-empty line after a `## <heading>` line, or null. */
function sectionValue(lines: readonly string[], heading: string): string | null {
  const at = lines.findIndex(line => line.trim().toLowerCase() === `## ${heading}`.toLowerCase());
  if (at < 0) return null;
  for (const line of lines.slice(at + 1)) {
    const trimmed = line.trim();
    if (trimmed.startsWith("## ")) return null;
    if (trimmed) return trimmed;
  }
  return null;
}

/** The value of a `Key: value` line outside the traceability comment, or null. */
function labelledValue(lines: readonly string[], label: string): string | null {
  const re = new RegExp(`^${label}:\\s*(.+)$`, "i");
  for (const line of lines) {
    const match = re.exec(line.trim());
    if (match) return match[1].trim();
  }
  return null;
}

function statusWord(value: string | null): string | null {
  if (value === null) return null;
  const word = value.toLowerCase().match(/^[a-z-]+/)?.[0] ?? "";
  return word || null;
}

function publicationReceipt(value: string | null): PublicationReceipt | null {
  if (!value) return null;
  try {
    const receipt: unknown = JSON.parse(value);
    if (typeof receipt !== "object" || receipt === null || !("repo" in receipt) || !("remote_ref" in receipt) || !("observed_commit_sha" in receipt)) return null;
    const { repo, remote_ref, observed_commit_sha } = receipt;
    if (typeof repo !== "string" || typeof remote_ref !== "string" || typeof observed_commit_sha !== "string") return null;
    const url = new URL(repo);
    if (url.protocol !== "https:" || !url.hostname || url.username || url.password || url.search || url.hash || !/^\/[^\s]+$/.test(url.pathname)) return null;
    if (!/^refs\/(heads|tags)\/[A-Za-z0-9_][A-Za-z0-9_./-]*$/.test(remote_ref) || remote_ref.includes("..") || remote_ref.includes("//") || remote_ref.split("/").some(part => !part || part.startsWith(".") || part.endsWith(".") || part.endsWith(".lock"))) return null;
    if (!/^(?:[a-fA-F0-9]{40}|[a-fA-F0-9]{64})$/.test(observed_commit_sha) || /^0+$/.test(observed_commit_sha)) return null;
    return { repo, remote_ref, observed_commit_sha };
  } catch {
    return null;
  }
}

export function parseHandoff(path: string, text: string): Handoff {
  const lines = text.split(/\r?\n/);
  const body = lines.filter(line => !/^\s*(<!--|-->|task:|branch:|agentId:|runId:|resultStatus:|finishedAt:|failureMode:|terminatedAt:)/.test(line));
  const branchRaw = sectionValue(lines, "Branch") ?? labelledValue(body, "Branch");
  return {
    path,
    status: statusWord(sectionValue(lines, "Status") ?? labelledValue(body, "Status")),
    verification: statusWord(sectionValue(lines, "Verification")),
    branch: branchRaw === null ? null : branchRaw.replace(/`/g, "").trim() || null,
    publication: publicationReceipt(sectionValue(body, "Publication receipt")),
  };
}

/** The handoff the row's status points at: the failure sidecar for an error, else the recorded path, else `handoffs/<name>.md`. */
function handoffFor(workspace: string, task: StateTaskFile): Handoff | null {
  const candidates: string[] = [];
  if (task.status === "error") candidates.push(join(workspace, "handoffs", `${task.name}-failure.md`));
  if (task.handoffPath) candidates.push(resolve(workspace, task.handoffPath));
  candidates.push(join(workspace, "handoffs", `${task.name}.md`));
  for (const path of candidates) {
    if (existsSync(path)) return parseHandoff(path, readFileSync(path, "utf8"));
  }
  return null;
}

export function readWorkspace(workspaceArg: string): WorkspaceSnapshot {
  const workspace = resolve(workspaceArg);
  const plan = readJson<PlanFile>(join(workspace, "plan.json"), "plan.json");
  const state = readJson<StateFile>(join(workspace, "state.json"), "state.json");
  if (!Array.isArray(state.tasks) || typeof state.rootSlug !== "string") {
    throw new Error(`state.json at ${workspace} has no rootSlug and tasks array`);
  }
  const handoffs = new Map<string, Handoff>();
  for (const task of state.tasks) {
    const handoff = handoffFor(workspace, task);
    if (handoff) handoffs.set(task.name, handoff);
  }
  const logPath = join(workspace, "attention.log");
  const attention = existsSync(logPath)
    ? readFileSync(logPath, "utf8").split(/\r?\n/).filter(line => line.trim())
    : (state.attention ?? []).map(entry => `[${entry.at}] ${entry.message}`);
  const nativePath = join(workspace, "native.json");
  const native = existsSync(nativePath) ? readJson<NonNullable<WorkspaceSnapshot["native"]>>(nativePath, "native.json") : undefined;
  return { workspace, plan, state, handoffs, attention, native };
}

// ---------------------------------------------------------------------------
// Building the record
// ---------------------------------------------------------------------------

const OWNER_STATE: Record<TaskStatus, OwnerState> = {
  pending: "waiting",
  running: "active",
  "handed-off": "complete",
  error: "blocked",
  cancelled: "closed",
  pruned: "closed",
};

const VERIFIED_VERDICTS = new Set(["live-ui-verified", "unit-test-verified", "type-check-only"]);
const TERMINAL: ReadonlySet<TaskStatus> = new Set(["handed-off", "error", "cancelled", "pruned"]);

function stage(state: StageState, note = "", evidence: string[] = []): Stage {
  return { state, note, evidence };
}

function firstSentence(text: string, max = 100): string {
  const sentence = text.trim().split(/(?<=[.!?])\s/)[0] ?? "";
  return sentence.length > max ? `${sentence.slice(0, max - 1).trimEnd()}…` : sentence;
}

function evidenceId(name: string): string {
  return `handoff-${name}`;
}

function describeHandoff(handoff: Handoff): string {
  const parts: string[] = [];
  if (handoff.status) parts.push(`Status: ${handoff.status}`);
  if (handoff.verification) parts.push(`Verification: ${handoff.verification}`);
  if (handoff.branch) parts.push(`Branch: ${handoff.branch}`);
  if (handoff.publication) parts.push(`Publication: ${handoff.publication.repo} ${handoff.publication.remote_ref} at ${handoff.publication.observed_commit_sha}`);
  return parts.join(" · ") || "No Status or Branch line";
}

/** A link from the page's directory to a workspace file: relative inside the workspace, absolute when the page lives elsewhere. */
function localLink(outDir: string, target: string): string {
  const rel = relative(outDir, target);
  return rel.startsWith("..") ? target : rel;
}

function handoffEvidence(task: StateTaskFile, handoff: Handoff, snapshot: WorkspaceSnapshot, outDir: string, hosted: boolean): Evidence {
  const verdict = handoff.status ?? handoff.verification;
  let result: Evidence["result"] = "observed";
  let assessment: Evidence["assessment"] = "accepted";
  if (verdict === "success" || (verdict !== null && VERIFIED_VERDICTS.has(verdict))) result = "passed";
  else if (verdict === "blocked" || verdict === "error" || verdict === "verifier-failed") result = "failed";
  else if (verdict === "verifier-blocked") result = "interrupted";
  if (verdict === "partial" || verdict === "verifier-blocked" || verdict === null || handoff.verification === "unit-test-verified" || handoff.verification === "type-check-only") assessment = "limited";
  const file = relative(snapshot.workspace, handoff.path);
  return {
    id: evidenceId(task.name),
    label: `Handoff from ${task.name}`,
    scope: `Thread ${task.agentId ?? "(none)"}${handoff.branch ? ` on ${handoff.branch}` : ""}; the worker's own report, not a review`,
    result,
    assessment,
    note: describeHandoff(handoff),
    href: hosted ? "" : localLink(outDir, handoff.path),
    output: `${describeHandoff(handoff)}\nFile: ${file}`,
  };
}

function workFor(task: StateTaskFile, handoff: Handoff | null, unmet: string[]): Work {
  const file = handoff ? `handoffs/${task.name}.md` : "no handoff file";
  switch (task.status) {
    case "pending":
      return unmet.length
        ? { state: "waiting", summary: "Waiting for earlier work to finish.", reason: `Not spawned; dependsOn ${unmet.join(", ")} not handed off` }
        : { state: "ready", summary: "Ready to start.", reason: "Not spawned yet; every dependency has handed off" };
    case "running":
      return { state: "working", summary: "In progress.", reason: `Thread running since ${task.startedAt ?? "(unknown)"}` };
    case "error":
      return {
        state: "blocked",
        summary: "The worker stopped before finishing.",
        reason: `Run ended with status=${task.resultStatus ?? "error"}${task.failureMode ? ` (${task.failureMode})` : ""}${task.note ? `: ${task.note}` : ""}`,
        ...(handoff ? { evidence: [evidenceId(task.name)] } : {}),
      };
    case "cancelled":
      return { state: "cancelled", summary: "Stopped by the operator.", reason: "Cancelled through the loop's stop command", receipt: "state.json status=cancelled" };
    case "pruned":
      return { state: "cancelled", summary: "Removed from the plan.", reason: "Pruned: the task left plan.json", receipt: "state.json status=pruned" };
    case "handed-off": {
      const evidence = handoff ? [evidenceId(task.name)] : [];
      const verdict = handoff?.status ?? handoff?.verification ?? null;
      const branch = handoff?.branch ? ` on ${handoff.branch}` : "";
      if (task.verification === "verifier-failed" || handoff?.verification === "verifier-failed") {
        return { state: "needs_decision", summary: "Verification found the change does not work yet.", reason: "Collected verifier verdict: verifier-failed", evidence };
      }
      if (task.verification === "verifier-blocked" || handoff?.verification === "verifier-blocked") {
        return { state: "blocked", summary: "Verification is blocked.", reason: "Collected verifier verdict: verifier-blocked", evidence };
      }
      if (verdict === "success") {
        return { state: "delivered", summary: `Handed off${branch}.`, reason: `${file}: Status success`, evidence };
      }
      if (verdict !== null && VERIFIED_VERDICTS.has(verdict)) {
        return { state: "delivered", summary: "Verification finished.", reason: `${file}: Verification ${verdict}`, evidence };
      }
      if (verdict === "partial") {
        return { state: "needs_decision", summary: "Partly done; the planner decides whether to retry or follow up.", reason: `${file}: Status partial`, evidence };
      }
      if (verdict === "blocked") {
        return { state: "blocked", summary: "The worker hit a blocker and stopped.", reason: `${file}: ${handoff?.status ? "Status" : "Verification"} ${verdict}`, evidence };
      }
      return { state: "unknown", summary: "We're confirming how this item ended.", reason: `${file}: no Status or Verification line`, evidence };
    }
    default: {
      const _exhaustive: never = task.status;
      return _exhaustive;
    }
  }
}

function milestonesFor(
  task: StateTaskFile,
  planTask: PlanTaskFile | undefined,
  handoff: Handoff | null,
  verifierNames: string[]
): Row["milestones"] {
  const proof = handoff ? [evidenceId(task.name)] : [];
  const verdict = handoff?.status ?? handoff?.verification ?? null;
  const delivered = task.status === "handed-off" && (verdict === "success" || (verdict !== null && VERIFIED_VERDICTS.has(verdict)));
  const stopped = task.status === "error" || verdict === "blocked" || verdict === "verifier-blocked" || verdict === "verifier-failed";
  const implemented: Stage = delivered
    ? stage("verified", `${handoff?.path ? relative(dirname(dirname(handoff.path)), handoff.path) : "handoff"} reports ${verdict}`, proof)
    : stopped
      ? stage("blocked", task.status === "error" ? `Run ended with status=${task.resultStatus ?? "error"}` : `Handoff reports ${verdict}`, proof)
      : task.status === "handed-off"
        ? stage("pending", verdict ? `Handoff reports ${verdict}` : "Handoff has no Status line", proof)
        : stage("pending", task.status === "running" ? "Thread running" : "Not started");

  let published: Stage;
  if (task.type === "verifier") {
    published = stage("not_requested", "Verifiers commit nothing; the verdict is the deliverable");
  } else if (handoff?.publication) {
    const receipt = handoff.publication;
    const pr = task.prNumber ? `; PR #${task.prNumber}` : planTask?.openPR ? "; openPR requested but no PR number recorded" : "";
    published = planTask?.openPR && !task.prNumber
      ? stage("pending", `Publication receipt: ${receipt.repo} ${receipt.remote_ref} at ${receipt.observed_commit_sha}${pr}`, proof)
      : stage("verified", `Publication receipt: ${receipt.repo} ${receipt.remote_ref} at ${receipt.observed_commit_sha}${pr}`, proof);
  } else if (delivered) {
    published = stage("pending", "No valid publication receipt; a branch name is not proof of publication", proof);
  } else {
    published = stage("pending", "No valid publication receipt");
  }

  let verification: Stage;
  const recorded = task.verification ?? null;
  if (task.type === "verifier") {
    verification = delivered
      ? stage("verified", `Verifier reports ${verdict}`, proof)
      : stopped
        ? stage("blocked", `Verifier reports ${verdict ?? "error"}`, proof)
        : stage("pending", "Verifier not finished");
  } else if (recorded !== null && VERIFIED_VERDICTS.has(recorded)) {
    verification = stage("verified", `state.json verification=${recorded}`);
  } else if (recorded === "verifier-blocked" || recorded === "verifier-failed") {
    verification = stage("blocked", `state.json verification=${recorded}`);
  } else if (verifierNames.length) {
    verification = stage("pending", `Awaiting verifier ${verifierNames.join(", ")}`);
  } else if (recorded === "not-verified") {
    verification = stage("not_requested", "Worker self-reported not-verified; no verifier planned");
  } else {
    verification = stage("not_requested");
  }

  return {
    defined: planTask
      ? stage("verified", planTask.acceptance?.length ? `plan.json scopedGoal and ${planTask.acceptance.length} acceptance item(s)` : "plan.json scopedGoal")
      : stage("not_requested", task.adHoc ? "Added outside plan.json" : "No plan.json entry"),
    // A verifier implements nothing; its verdict lands in the verification stage below.
    pr_readiness: task.type === "verifier" ? stage("not_requested", "Verifier; see verification") : implemented,
    code_publication: published,
    verification,
    deployment: stage("not_requested"),
    business_acceptance: stage("not_requested"),
  };
}

function nextActionFor(task: StateTaskFile, work: Work, unmet: string[]): string {
  switch (task.status) {
    case "pending":
      return unmet.length ? `Wait for ${unmet.join(", ")} to hand off` : "The loop spawns this task on its next pass";
    case "running":
      return "Wait for the thread to hand off";
    case "error":
      return "Planner decides: retry, repair, or abandon (references/handoffs.md)";
    case "cancelled":
    case "pruned":
      return "None; the task is out of the run";
    case "handed-off":
      return work.state === "delivered" ? "None for this task" : "Planner reads the handoff and decides";
    default: {
      const _exhaustive: never = task.status;
      return _exhaustive;
    }
  }
}

function rowFor(task: StateTaskFile, snapshot: WorkspaceSnapshot, outDir: string, hosted: boolean): { row: Row; evidence: Evidence | null } {
  const planTask = snapshot.plan.tasks?.find(candidate => candidate.name === task.name);
  const byName = new Map(snapshot.state.tasks.map(candidate => [candidate.name, candidate]));
  const dependsOn = task.dependsOn ?? planTask?.dependsOn ?? [];
  const unmet = dependsOn.filter(name => byName.get(name)?.status !== "handed-off");
  const handoff = snapshot.handoffs.get(task.name) ?? null;
  const verifierNames = (snapshot.plan.tasks ?? []).filter(candidate => candidate.type === "verifier" && candidate.verifies === task.name).map(candidate => candidate.name);
  const work = workFor(task, handoff, unmet);
  const hasThread = typeof task.agentId === "string" && task.agentId.length > 0;
  const native = snapshot.native?.attempts.find(attempt => attempt.task === task.name && attempt.attemptId === task.runId);
  const owner: Row["owner"] = {
    id: native ? `${native.handle.harness}:${native.handle.kind}:${native.handle.id}` : task.agentId || `unassigned-${task.name}`,
    label: task.name,
    state: OWNER_STATE[task.status],
  };
  if (hasThread && isThreadId(task.agentId) && (!snapshot.native || (native?.handle.kind === "thread" && native.handle.harness === "amp"))) owner.href = agentUrl(task.agentId);
  if (task.status === "running") owner.activity = task.note?.trim() || `Working in its thread since ${task.startedAt ?? "(unknown)"}.`;
  if (native) owner.activity = `${native.handle.harness} ${native.handle.kind} ${native.handle.id}; attempt ${native.attemptId}; logical parent ${native.logicalParent ?? "(not reported)"}.`;
  if (task.branch) owner.location = task.branch;
  if (handoff) owner.handoff = `${relative(snapshot.workspace, handoff.path)}: ${describeHandoff(handoff)}`;
  const checked = task.lastUpdate ?? task.finishedAt ?? task.startedAt;
  if (checked) owner.last_checked_at = checked;

  const blocker =
    task.status === "error"
      ? work.reason
      : work.state === "blocked" || work.state === "needs_decision"
        ? work.reason
        : "";
  const row: Row = {
    id: task.name,
    title: planTask?.scopedGoal ? firstSentence(planTask.scopedGoal) : task.name,
    owner,
    work,
    milestones: milestonesFor(task, planTask, handoff, verifierNames),
    blocked_by: unmet,
    blocker,
    next_action: snapshot.native && task.status === "pending" ? "Use native tools after preflight; record the actual dispatch receipt" : snapshot.native && task.status === "running" ? "Collect the native execution result and record its handoff" : nextActionFor(task, work, unmet),
    done_when: planTask?.acceptance?.length ? planTask.acceptance.join("; ") : planTask?.scopedGoal ?? "",
  };
  return { row, evidence: handoff ? handoffEvidence(task, handoff, snapshot, outDir, hosted) : null };
}

function decisionsFor(snapshot: WorkspaceSnapshot, rootId: string | null): Decision[] {
  const andon = snapshot.state.andon;
  if (!andon || andon.cleared || !(andon.raisedAt || andon.reason)) return [];
  const stuck = snapshot.state.tasks.filter(task => !TERMINAL.has(task.status)).map(task => task.name);
  const decision: Decision = {
    id: "andon",
    text: `The run is stopped${andon.raisedBy ? ` by ${andon.raisedBy}` : ""}: ${andon.reason?.trim() || "no reason recorded"}. Resume it, or end the run here?`,
    recommendation: "Clear the Andon once the reason is settled; otherwise stop the run and keep the finished work.",
    task_ids: stuck,
    unblocks: "Spawning the remaining tasks",
  };
  if (rootId) decision.discussion = { owner_id: rootId, label: "Root planner thread", href: agentUrl(rootId) };
  return [decision];
}

export interface BuildOptions {
  /** `updated_at`; defaults to now. */
  now?: string;
  /** The renderer's `--contract-version` output. */
  contractVersion: string;
  /** The page the record will be rendered to; handoff links are relative to its directory. */
  outPath: string;
  /** Leave local handoff links out so the renderer's hosted check passes. */
  hosted?: boolean;
}

export function buildStatusRecord(snapshot: WorkspaceSnapshot, options: BuildOptions): StatusRecord {
  const outPath = resolve(options.outPath);
  const outDir = dirname(outPath);
  const hosted = options.hosted ?? false;
  const rootSlug = snapshot.state.rootSlug;
  const delivery = snapshot.native?.deliveryOwner;
  const rootId = delivery
    ? delivery.harness === "amp" && delivery.kind === "thread" && isThreadId(delivery.id) ? delivery.id : null
    : isThreadId(snapshot.plan.selfAgentId) ? snapshot.plan.selfAgentId : null;
  const rows: Row[] = [];
  const evidence: Evidence[] = [];
  for (const task of snapshot.state.tasks) {
    const built = rowFor(task, snapshot, outDir, hosted);
    rows.push(built.row);
    if (built.evidence) evidence.push(built.evidence);
  }
  const record: StatusRecord = {
    schema_version: 2,
    run_id: snapshot.native?.runId ?? (rootId ? `${rootSlug}-${rootId}` : rootSlug),
    title: snapshot.plan.summary?.trim() || rootSlug,
    updated_at: options.now ?? new Date().toISOString(),
    contract_version: options.contractVersion,
    harness_name: delivery?.harness ?? "amp",
    presentation: {
      destination: "local",
      local_path: outPath,
      interaction: "This page is a snapshot of the run workspace; copied questions go to the root planner thread.",
    },
    tasks: rows,
    evidence,
    decisions: decisionsFor(snapshot, rootId),
    history: [...snapshot.attention.slice(-50), ...(snapshot.native ? [`Scope ${snapshot.native.scope.revision}: ${snapshot.native.scope.reference}. Native execution; readiness is not a new consent request.`] : [])],
  };
  if (snapshot.plan.goal?.trim()) record.goal = snapshot.plan.goal.trim();
  if (rootId) record.presentation.coordinator_href = agentUrl(rootId);
  return record;
}

// ---------------------------------------------------------------------------
// Locating and running the dashboard skill
// ---------------------------------------------------------------------------

const RENDERER = join("scripts", "render_dashboard.py");

/**
 * Amp's skill cache installs each skill as `<name>@<hash>` and keeps older
 * hashes around; the same lookup `core/runtime.ts` makes for `pstack-sync@*`.
 * Returns every `dashboard@*` sibling of `root` holding the renderer, newest
 * first; `[]` when `root` cannot be read.
 */
export function hashedDashboardDirs(root: string): string[] {
  let names: string[];
  try {
    names = readdirSync(root);
  } catch {
    return [];
  }
  return names
    .filter(name => name.startsWith("dashboard@"))
    .map(name => join(root, name))
    .filter(dir => existsSync(join(dir, RENDERER)))
    .sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs);
}

export function dashboardCandidateDirs(env: NodeJS.ProcessEnv = process.env): string[] {
  const here = dirname(fileURLToPath(import.meta.url));
  const dirs: string[] = [];
  if (env.ORCHESTRATE_DASHBOARD_DIR) dirs.push(env.ORCHESTRATE_DASHBOARD_DIR);
  // Installed: <skills>/orchestrate/scripts/tools -> <skills>/dashboard
  const skillsRoot = join(here, "..", "..", "..");
  dirs.push(join(skillsRoot, "dashboard"));
  // Orb skill cache: <cache>/orchestrate@<hash>/scripts/tools -> <cache>/dashboard@<hash>
  dirs.push(...hashedDashboardDirs(skillsRoot));
  // Pack: pstack-sync/adapters/amp/agent-runtime/scripts/tools -> <pack>/dashboard
  dirs.push(join(here, "..", "..", "..", "..", "..", "..", "dashboard"));
  return dirs;
}

export function resolveDashboardDir(env: NodeJS.ProcessEnv = process.env): string {
  const candidates = dashboardCandidateDirs(env);
  for (const dir of candidates) {
    if (existsSync(join(dir, RENDERER))) return dir;
  }
  throw new Error(
    `dashboard skill not found; looked in ${candidates.join(", ")}. Install the dashboard skill beside this skill or set ORCHESTRATE_DASHBOARD_DIR.`
  );
}

export interface RenderResult {
  ok: boolean;
  status: number | null;
  stdout: string;
  stderr: string;
}

function runRenderer(dashboardDir: string, args: readonly string[]): RenderResult {
  const proc = spawnSync("python3", ["-I", join(dashboardDir, RENDERER), ...args], { encoding: "utf8" });
  if (proc.error) {
    return { ok: false, status: null, stdout: "", stderr: `python3 failed to start: ${proc.error.message}` };
  }
  return { ok: proc.status === 0, status: proc.status, stdout: proc.stdout, stderr: proc.stderr };
}

/** `python3 render_dashboard.py --contract-version`. */
export function readContractVersion(dashboardDir: string): string {
  const result = runRenderer(dashboardDir, ["--contract-version"]);
  if (!result.ok || !result.stdout.trim()) {
    throw new Error(`could not read the dashboard contract version: ${result.stderr.trim() || `exit ${result.status}`}`);
  }
  return result.stdout.trim();
}

/** `python3 render_dashboard.py <status.json> <out.html> [--hosted]`. */
export function renderStatus(dashboardDir: string, statusPath: string, outPath: string, hosted: boolean): RenderResult {
  return runRenderer(dashboardDir, [statusPath, outPath, ...(hosted ? ["--hosted"] : [])]);
}

export function writeJsonAtomic(path: string, value: unknown): void {
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.tmp`;
  writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`);
  renameSync(temporary, path);
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

interface Args {
  workspace: string;
  out: string | undefined;
  hosted: boolean;
  statusOnly: boolean;
}

function usage(): never {
  console.error("usage: bun tools/dashboard.ts <workspace> [--out <html>] [--hosted] [--status-only]");
  process.exit(2);
}

function parseArgs(argv: readonly string[]): Args {
  let workspace: string | undefined;
  let out: string | undefined;
  let hosted = false;
  let statusOnly = false;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    switch (a) {
      case "--out":
        out = argv[++i];
        if (out === undefined) {
          console.error("flag --out requires a value");
          usage();
        }
        break;
      case "--hosted":
        hosted = true;
        break;
      case "--status-only":
        statusOnly = true;
        break;
      case "-h":
      case "--help":
        return usage();
      default:
        if (a.startsWith("--")) {
          console.error(`unknown flag: ${a}`);
          usage();
        }
        if (workspace !== undefined) {
          console.error(`unexpected positional arg: ${a}`);
          usage();
        }
        workspace = a;
    }
  }
  if (workspace === undefined) {
    console.error("missing <workspace>");
    usage();
  }
  return { workspace, out, hosted, statusOnly };
}

export function main(argv: readonly string[]): number {
  const args = parseArgs(argv);
  let snapshot: WorkspaceSnapshot;
  let dashboardDir: string;
  let contractVersion: string;
  try {
    snapshot = readWorkspace(args.workspace);
    dashboardDir = resolveDashboardDir();
    contractVersion = readContractVersion(dashboardDir);
  } catch (err) {
    console.error(`dashboard: ${err instanceof Error ? err.message : String(err)}`);
    return 2;
  }
  const outPath = resolve(args.out ?? join(snapshot.workspace, "dashboard.html"));
  const statusPath = join(snapshot.workspace, "status.json");
  const record = buildStatusRecord(snapshot, { contractVersion, outPath, hosted: args.hosted });
  writeJsonAtomic(statusPath, record);
  console.log(`wrote ${statusPath} (${record.tasks.length} task row(s), contract ${contractVersion})`);
  if (args.statusOnly) return 0;
  const result = renderStatus(dashboardDir, statusPath, outPath, args.hosted);
  if (!result.ok) {
    process.stderr.write(result.stderr.endsWith("\n") || !result.stderr ? result.stderr : `${result.stderr}\n`);
    if (!result.stderr.trim()) console.error(`dashboard: renderer exited ${result.status ?? "without a status"}`);
    return 1;
  }
  process.stdout.write(result.stdout);
  return 0;
}

if (import.meta.main) {
  process.exit(main(process.argv.slice(2)));
}
