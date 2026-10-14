#!/usr/bin/env bun
// Amp port: tidy what an interrupted or older orchestrate run left behind.
//
// Usage:
//   bun tools/cleanup.ts <workspace> [--branches] [--repo-path <checkout>] [--integration <branch>] [--dry-run]
//
// Reads `<workspace>/plan.json` and `state.json` and archives the thread of
// every task that is terminal (`handed-off`, `error`, `cancelled`, `pruned`),
// is not the root planner (its `agentId` is `plan.selfAgentId`; the root is
// never a task row of its own workspace, but a row that names its thread is
// kept open all the same), and is not archived yet (`amp threads search
// "id:<id> archived:true"` answers that, the way the runtime's `wait` checks
// it). One `amp threads archive <id>` per thread; a rerun archives nothing
// twice and never unarchives.
//
// With `--branches` the terminal tasks' `orch/<rootSlug>/<task>` branches are
// deleted from the checkout at `--repo-path` (default: the cwd) when their
// head commit is already an ancestor of the integration branch
// (`git merge-base --is-ancestor`); the integration branch itself and any
// branch it does not contain are kept. `--integration` names that branch
// (default: `plan.prBase`, else `plan.baseBranch`); the local ref is read
// when it exists, else `origin/<branch>`. A contained branch is deleted
// locally (`git branch -D`) and on `origin` (`git push origin --delete`),
// whichever of the two exist.
//
// One line per action, one summary line; `--dry-run` prints the plan and
// performs nothing. Exit 0 when every action succeeded, 1 when one failed,
// 2 for a usage or workspace error. Every command runs from an argv array.
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { isThreadId } from "../core/runtime.ts";

export type TaskStatus = "pending" | "running" | "handed-off" | "error" | "cancelled" | "pruned";

export interface CleanupPlanFile {
  rootSlug?: string;
  baseBranch?: string;
  prBase?: string;
  selfAgentId?: string | null;
}

export interface CleanupTaskFile {
  name: string;
  type?: string;
  branch?: string;
  status: TaskStatus;
  agentId?: string | null;
}

export interface CleanupStateFile {
  rootSlug: string;
  tasks: CleanupTaskFile[];
}

export interface CleanupWorkspace {
  workspace: string;
  plan: CleanupPlanFile;
  state: CleanupStateFile;
}

export interface CommandResult {
  code: number | null;
  stdout: string;
  stderr: string;
}

export type CommandRunner = (
  cmd: string,
  args: string[],
  opts?: { cwd?: string; env?: NodeJS.ProcessEnv; timeoutMs?: number }
) => CommandResult;

export interface CleanupOptions {
  workspace: string;
  branches?: boolean;
  repoPath?: string;
  integration?: string;
  dryRun?: boolean;
  env?: NodeJS.ProcessEnv;
  cwd?: string;
  run?: CommandRunner;
  /** Where the action and summary lines go; default: `console.log`. */
  log?: (line: string) => void;
}

export type ThreadDecision =
  | { task: string; agentId: string; action: "archive" }
  | { task: string; agentId: string; action: "skip"; reason: "root" | "archived" }
  | { task: string; agentId: string | null; action: "skip"; reason: "not-terminal" | "no-thread" };

export type BranchDecision =
  | { branch: string; action: "delete"; local: boolean; remote: boolean }
  | { branch: string; action: "keep"; reason: "integration" | "not-contained" | "no-ref" };

export interface CleanupReport {
  threads: ThreadDecision[];
  branches: BranchDecision[];
  integration: string | null;
  archived: number;
  deleted: number;
  failed: number;
  dryRun: boolean;
}

export const TERMINAL: ReadonlySet<TaskStatus> = new Set(["handed-off", "error", "cancelled", "pruned"]);

const DEFAULT_TIMEOUT_MS = 60_000;

/** Runs `cmd` with an argv array and waits; a missing binary is a result, not a throw. */
export const defaultRunner: CommandRunner = (cmd, args, opts = {}) => {
  const proc = spawnSync(cmd, args, {
    cwd: opts.cwd,
    env: opts.env ?? process.env,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    timeout: opts.timeoutMs ?? DEFAULT_TIMEOUT_MS,
  });
  if (proc.error) return { code: null, stdout: proc.stdout ?? "", stderr: `${proc.stderr ?? ""}${proc.error.message}` };
  return { code: proc.status, stdout: proc.stdout ?? "", stderr: proc.stderr ?? "" };
};

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/** Last non-empty line of stderr, else stdout; what a person would read first. */
function lastLine(result: CommandResult): string {
  const text = (result.stderr.trim() || result.stdout.trim()).split("\n").filter(Boolean);
  return (text[text.length - 1] ?? "").trim();
}

function readJson<T>(path: string, what: string): T {
  let text: string;
  try {
    text = readFileSync(path, "utf8");
  } catch (err) {
    throw new Error(`${what} not readable at ${path}: ${errorMessage(err)}`);
  }
  try {
    return JSON.parse(text) as T;
  } catch (err) {
    throw new Error(`${what} at ${path} is not valid JSON: ${errorMessage(err)}`);
  }
}

export function readCleanupWorkspace(workspaceArg: string): CleanupWorkspace {
  const workspace = resolve(workspaceArg);
  const plan = readJson<CleanupPlanFile>(join(workspace, "plan.json"), "plan.json");
  const state = readJson<CleanupStateFile>(join(workspace, "state.json"), "state.json");
  if (!Array.isArray(state.tasks) || typeof state.rootSlug !== "string") {
    throw new Error(`state.json at ${workspace} has no rootSlug and tasks array`);
  }
  return { workspace, plan, state };
}

/** True when `amp threads search "id:<id> archived:true"` lists the thread; a failed search reads as not archived, as in the runtime's `wait`. */
export function isArchived(run: CommandRunner, bin: string, agentId: string, env: NodeJS.ProcessEnv): boolean {
  const result = run(bin, ["threads", "search", `id:${agentId} archived:true`, "--json"], { env });
  if (result.code !== 0) return false;
  try {
    const parsed = JSON.parse(result.stdout) as unknown;
    return Array.isArray(parsed) && parsed.some(item => typeof item === "object" && item !== null && (item as { id?: string }).id === agentId);
  } catch {
    return false;
  }
}

/** What to do with each task's thread: archive the terminal non-root ones that are still open. */
export function planThreads(ws: CleanupWorkspace, archived: (agentId: string) => boolean): ThreadDecision[] {
  const root = typeof ws.plan.selfAgentId === "string" && isThreadId(ws.plan.selfAgentId) ? ws.plan.selfAgentId : null;
  const out: ThreadDecision[] = [];
  for (const task of ws.state.tasks) {
    const agentId = isThreadId(task.agentId) ? task.agentId : null;
    if (!TERMINAL.has(task.status)) {
      out.push({ task: task.name, agentId, action: "skip", reason: "not-terminal" });
    } else if (agentId === null) {
      out.push({ task: task.name, agentId: null, action: "skip", reason: "no-thread" });
    } else if (root !== null && agentId === root) {
      out.push({ task: task.name, agentId, action: "skip", reason: "root" });
    } else if (archived(agentId)) {
      out.push({ task: task.name, agentId, action: "skip", reason: "archived" });
    } else {
      out.push({ task: task.name, agentId, action: "archive" });
    }
  }
  return out;
}

/** The run's branches: `orch/<rootSlug>/<task>` of every terminal task row, once each, in row order. */
export function candidateBranches(ws: CleanupWorkspace): string[] {
  const prefix = `orch/${ws.state.rootSlug}/`;
  const seen = new Set<string>();
  for (const task of ws.state.tasks) {
    const branch = task.branch?.trim() ?? "";
    if (TERMINAL.has(task.status) && branch.startsWith(prefix) && branch.length > prefix.length) seen.add(branch);
  }
  return [...seen];
}

interface GitRefs {
  local: boolean;
  remote: boolean;
}

function gitRefs(run: CommandRunner, repo: string, env: NodeJS.ProcessEnv, branch: string): GitRefs {
  const exists = (ref: string): boolean => run("git", ["-C", repo, "rev-parse", "--verify", "--quiet", `${ref}^{commit}`], { env }).code === 0;
  return { local: exists(`refs/heads/${branch}`), remote: exists(`refs/remotes/origin/${branch}`) };
}

/** What to do with each candidate branch against the integration ref. Throws when the integration branch has no ref. */
export function planBranches(run: CommandRunner, repo: string, env: NodeJS.ProcessEnv, integration: string, candidates: string[]): BranchDecision[] {
  const target = gitRefs(run, repo, env, integration);
  if (!target.local && !target.remote) {
    throw new Error(`integration branch ${integration} has no local or origin ref in ${repo}; pass --integration <branch> or fetch first`);
  }
  const targetRef = target.local ? `refs/heads/${integration}` : `refs/remotes/origin/${integration}`;
  const out: BranchDecision[] = [];
  for (const branch of candidates) {
    if (branch === integration) {
      out.push({ branch, action: "keep", reason: "integration" });
      continue;
    }
    const refs = gitRefs(run, repo, env, branch);
    if (!refs.local && !refs.remote) {
      out.push({ branch, action: "keep", reason: "no-ref" });
      continue;
    }
    const checks: boolean[] = [];
    if (refs.local) checks.push(isAncestor(run, repo, env, `refs/heads/${branch}`, targetRef));
    if (refs.remote) checks.push(isAncestor(run, repo, env, `refs/remotes/origin/${branch}`, targetRef));
    if (checks.every(Boolean)) out.push({ branch, action: "delete", local: refs.local, remote: refs.remote });
    else out.push({ branch, action: "keep", reason: "not-contained" });
  }
  return out;
}

function isAncestor(run: CommandRunner, repo: string, env: NodeJS.ProcessEnv, ref: string, target: string): boolean {
  const result = run("git", ["-C", repo, "merge-base", "--is-ancestor", ref, target], { env });
  if (result.code === 0) return true;
  if (result.code === 1) return false;
  throw new Error(`git merge-base --is-ancestor ${ref} ${target} in ${repo} failed: ${lastLine(result) || `exit ${result.code ?? "signal"}`}`);
}

export function runCleanup(opts: CleanupOptions): CleanupReport {
  const env = opts.env ?? process.env;
  const cwd = opts.cwd ?? process.cwd();
  const run = opts.run ?? defaultRunner;
  const log = opts.log ?? ((line: string) => console.log(line));
  const dryRun = opts.dryRun === true;
  const bin = env.ORCHESTRATE_AMP_BIN || "amp";
  const verb = dryRun ? "would " : "";
  const ws = readCleanupWorkspace(resolve(cwd, opts.workspace));
  const report: CleanupReport = { threads: [], branches: [], integration: null, archived: 0, deleted: 0, failed: 0, dryRun };

  report.threads = planThreads(ws, agentId => isArchived(run, bin, agentId, env));
  for (const d of report.threads) {
    if (d.action === "skip") {
      if (d.reason === "root") log(`keep thread ${d.agentId} (${d.task}): root planner`);
      else if (d.reason === "archived") log(`skip thread ${d.agentId} (${d.task}): already archived`);
      continue;
    }
    if (dryRun) {
      log(`would archive thread ${d.agentId} (${d.task})`);
      report.archived++;
      continue;
    }
    const result = run(bin, ["threads", "archive", d.agentId], { env });
    if (result.code === 0) {
      log(`archived thread ${d.agentId} (${d.task})`);
      report.archived++;
    } else {
      log(`failed to archive thread ${d.agentId} (${d.task}): ${lastLine(result) || `exit ${result.code ?? "signal"}`}`);
      report.failed++;
    }
  }

  if (opts.branches) {
    const repo = resolve(cwd, opts.repoPath ?? ".");
    const integration = (opts.integration ?? ws.plan.prBase ?? ws.plan.baseBranch ?? "").trim();
    if (!integration) throw new Error("no integration branch: plan.json has neither prBase nor baseBranch; pass --integration <branch>");
    report.integration = integration;
    report.branches = planBranches(run, repo, env, integration, candidateBranches(ws));
    for (const d of report.branches) {
      if (d.action === "keep") {
        const why = d.reason === "integration" ? "the integration branch" : d.reason === "no-ref" ? "no local or origin ref" : `not contained in ${integration}`;
        log(`keep branch ${d.branch}: ${why}`);
        continue;
      }
      const where = [d.local ? "local" : "", d.remote ? "origin" : ""].filter(Boolean).join(" and ");
      if (dryRun) {
        log(`would delete branch ${d.branch} (${where}): contained in ${integration}`);
        report.deleted++;
        continue;
      }
      let ok = true;
      if (d.local) {
        const result = run("git", ["-C", repo, "branch", "-D", d.branch], { env });
        if (result.code !== 0) {
          ok = false;
          log(`failed to delete local branch ${d.branch}: ${lastLine(result) || `exit ${result.code ?? "signal"}`}`);
        }
      }
      if (d.remote) {
        const result = run("git", ["-C", repo, "push", "origin", "--delete", d.branch], { env, timeoutMs: 120_000 });
        if (result.code !== 0) {
          ok = false;
          log(`failed to delete origin branch ${d.branch}: ${lastLine(result) || `exit ${result.code ?? "signal"}`}`);
        }
      }
      if (ok) {
        log(`deleted branch ${d.branch} (${where}): contained in ${integration}`);
        report.deleted++;
      } else {
        report.failed++;
      }
    }
  }

  const kept = report.threads.filter(d => d.action === "skip" && d.reason === "root").length;
  const parts = [`${verb}archive${dryRun ? "" : "d"} ${report.archived} thread(s)`];
  if (kept) parts.push(`kept the root`);
  if (opts.branches) parts.push(`${verb}delete${dryRun ? "" : "d"} ${report.deleted} branch(es), kept ${report.branches.length - report.deleted}`);
  if (report.failed) parts.push(`${report.failed} failed`);
  log(`cleanup ${ws.state.rootSlug}: ${parts.join(", ")}`);
  return report;
}

interface Args {
  workspace: string;
  branches: boolean;
  repoPath?: string;
  integration?: string;
  dryRun: boolean;
}

function usage(): never {
  console.error("usage: bun tools/cleanup.ts <workspace> [--branches] [--repo-path <checkout>] [--integration <branch>] [--dry-run]");
  process.exit(2);
}

export function parseArgs(argv: readonly string[]): Args {
  let workspace: string | undefined;
  let repoPath: string | undefined;
  let integration: string | undefined;
  let branches = false;
  let dryRun = false;
  const requireValue = (flag: string, value: string | undefined): string => {
    if (value === undefined) {
      console.error(`flag ${flag} requires a value`);
      usage();
    }
    return value;
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    switch (a) {
      case "--branches":
        branches = true;
        break;
      case "--repo-path":
        repoPath = requireValue("--repo-path", argv[++i]);
        break;
      case "--integration":
        integration = requireValue("--integration", argv[++i]);
        break;
      case "--dry-run":
        dryRun = true;
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
  if ((repoPath !== undefined || integration !== undefined) && !branches) {
    console.error("--repo-path and --integration need --branches");
    usage();
  }
  return { workspace, branches, repoPath, integration, dryRun };
}

export function main(argv: readonly string[]): number {
  const args = parseArgs(argv);
  try {
    const report = runCleanup(args);
    return report.failed ? 1 : 0;
  } catch (err) {
    console.error(`cleanup: ${errorMessage(err)}`);
    return 2;
  }
}

if (import.meta.main) {
  process.exit(main(process.argv.slice(2)));
}
