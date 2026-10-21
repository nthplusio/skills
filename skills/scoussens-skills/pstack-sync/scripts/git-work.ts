import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { isAbsolute, join, resolve } from "node:path";
import { z } from "zod/v3";

const text = z.string().min(1);
const absolutePath = text.refine(isAbsolute, "use an absolute filesystem path");
export const Commit = z.string().regex(/^(?:[a-f0-9]{40}|[a-f0-9]{64})$/, "use a full commit ID");
export const PathPatterns = z.array(text.refine(pattern => !pattern.startsWith("/") && !pattern.startsWith("!") && !pattern.includes("\\") && !pattern.split("/").some(part => part === ".." || part === "."), "use repository-relative path globs"));
export const CodeConfig = z.object({
  repository: absolutePath,
  integrationRef: z.string().startsWith("refs/heads/"),
  checks: z.array(z.object({ command: text, timeoutSeconds: z.number().int().positive() }).strict()).min(1),
}).strict();
export const Assignment = z.object({
  id: text, repository: text, baseCommit: Commit, branch: text,
}).strict();
export const Receiver = Assignment.extend({ checkout: absolutePath }).strict();
export const RefUpdate = z.object({
  repository: absolutePath, ref: z.string().startsWith("refs/heads/"), before: Commit, after: Commit,
}).strict();

function must(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

export function git(repository: string, ...args: string[]): string {
  const result = spawnSync("git", ["-C", repository, ...args], { encoding: "utf8", maxBuffer: 16 * 1024 * 1024 });
  must(result.status === 0, `git ${args[0]} failed: ${result.error?.message ?? result.stderr.trim()}`);
  return result.stdout.trimEnd();
}

export function checkRepository(repository: string, expected: string): void {
  const normalize = (url: string) => url.replace(/\/$/, "").replace(/\.git$/, "");
  must(normalize(git(repository, "remote", "get-url", "origin")) === normalize(expected), "repository origin does not match plan.repoUrl");
  must(git(repository, "rev-parse", "--is-shallow-repository") === "false", "fetch complete history before checking ancestry");
}

export function checkCommit(repository: string, commit: string): void {
  Commit.parse(commit);
  must(git(repository, "rev-parse", "--verify", `${commit}^{commit}`) === commit, `commit unavailable: ${commit}`);
}

export function contains(repository: string, ancestor: string, descendant: string): boolean {
  checkCommit(repository, ancestor);
  checkCommit(repository, descendant);
  const result = spawnSync("git", ["-C", repository, "merge-base", "--is-ancestor", ancestor, descendant]);
  must(result.status === 0 || result.status === 1, "could not check commit ancestry");
  return result.status === 0;
}

export function checkBranch(repository: string, branch: string): void {
  must(!branch.startsWith("refs/"), "worker branch must be a short branch name");
  git(repository, "check-ref-format", `refs/heads/${branch}`);
}

function clean(repository: string): void {
  must(git(repository, "status", "--porcelain", "--untracked-files=all") === "", "checkout has uncommitted or untracked files");
}

export function receive(checkout: string, assignment: z.infer<typeof Assignment>): z.infer<typeof Receiver> {
  checkRepository(checkout, assignment.repository);
  checkBranch(checkout, assignment.branch);
  checkCommit(checkout, assignment.baseCommit);
  must(git(checkout, "rev-parse", "HEAD") === assignment.baseCommit, "receiver HEAD differs from assigned base");
  must(git(checkout, "symbolic-ref", "HEAD") === `refs/heads/${assignment.branch}`, "receiver branch differs from assigned branch");
  clean(checkout);
  return { ...assignment, checkout: realpathSync(checkout) };
}

export function prepareWorktree(repository: string, checkout: string, assignment: z.infer<typeof Assignment>): z.infer<typeof Receiver> {
  checkRepository(repository, assignment.repository);
  checkCommit(repository, assignment.baseCommit);
  checkBranch(repository, assignment.branch);
  const destination = resolve(checkout);
  if (!existsSync(destination)) git(repository, "worktree", "add", "-b", assignment.branch, destination, assignment.baseCommit);
  return receive(destination, assignment);
}

function matches(path: string, pattern: string): boolean {
  return new Bun.Glob(pattern).match(path);
}

export function scopesOverlap(left: string[], right: string[]): boolean {
  const prefix = (pattern: string) => pattern.split(/[*?\[\]{}!]/, 1)[0] ?? "";
  const leftPrefixes = left.map(prefix), rightPrefixes = right.map(prefix);
  return leftPrefixes.some(x => rightPrefixes.some(y => x.startsWith(y) || y.startsWith(x)));
}

export function checkScope(repository: string, base: string, result: string, allowed: string[], forbidden: string[]): string[] {
  must(contains(repository, base, result), "result does not contain its assigned base");
  const paths = git(repository, "diff", "--no-renames", "--name-only", "-z", base, result, "--").split("\0").filter(Boolean);
  for (const path of paths) {
    must(allowed.some(pattern => matches(path, pattern)) && !forbidden.some(pattern => matches(path, pattern)), `out-of-scope change: ${path}`);
  }
  return paths;
}

function uncheckedRef(repository: string, ref: string): void {
  git(repository, "check-ref-format", ref);
  const worktrees = git(repository, "worktree", "list", "--porcelain", "-z").split("\0");
  must(!worktrees.includes(`branch ${ref}`), "integration branch is checked out; use an unoccupied integration branch");
}

export function checkRefUpdate(update: z.infer<typeof RefUpdate>): "before" | "after" {
  uncheckedRef(update.repository, update.ref);
  const current = git(update.repository, "rev-parse", "--verify", update.ref);
  must(current === update.before || current === update.after, "integration ref moved; reconcile before retry");
  must(contains(update.repository, update.before, update.after), "integration must fast-forward the expected parent");
  return current === update.after ? "after" : "before";
}

export function applyRefUpdate(update: z.infer<typeof RefUpdate>): void {
  if (checkRefUpdate(update) === "before") git(update.repository, "update-ref", update.ref, update.after, update.before);
}

export function buildCandidate(config: z.infer<typeof CodeConfig>, expected: string, result: string) {
  uncheckedRef(config.repository, config.integrationRef);
  must(git(config.repository, "rev-parse", config.integrationRef) === expected, "integration ref moved; rebuild from its current head");
  checkCommit(config.repository, result);
  const directory = mkdtempSync(join(tmpdir(), "orchestrate-candidate-"));
  const checkout = join(directory, "checkout");
  try {
    git(config.repository, "worktree", "add", "--detach", checkout, expected);
    git(checkout, "-c", "commit.gpgsign=false", "merge", "--no-ff", "--no-edit", result);
    const candidate = git(checkout, "rev-parse", "HEAD");
    const checks = config.checks.map(check => {
      const executed = spawnSync("bash", ["-c", check.command], { cwd: checkout, encoding: "utf8", timeout: check.timeoutSeconds * 1000, maxBuffer: 4 * 1024 * 1024 });
      const evidence = { ...check, exitCode: executed.status, stdout: executed.stdout ?? "", stderr: executed.stderr ?? "" };
      must(executed.status === 0, `candidate check failed: ${check.command}\n${executed.error?.message ?? evidence.stderr}\n${evidence.stdout}`);
      clean(checkout);
      must(git(checkout, "rev-parse", "HEAD") === candidate, "candidate check changed HEAD; verification is stale");
      return evidence;
    });
    git(config.repository, "update-ref", `refs/orchestrate/candidates/${candidate}`, candidate);
    return { candidate, checks };
  } finally {
    if (existsSync(checkout)) git(config.repository, "worktree", "remove", "--force", checkout);
    rmSync(directory, { recursive: true, force: true });
  }
}

const Request = z.discriminatedUnion("action", [
  z.object({ action: z.literal("worktree"), repository: text, checkout: text, assignment: Assignment }).strict(),
  z.object({ action: z.literal("receive"), checkout: text, assignment: Assignment }).strict(),
]);

if (import.meta.main) {
  try {
    const path = process.argv[2];
    must(path, "usage: bun scripts/tools/git-work.ts <request.json>");
    const request = Request.parse(JSON.parse(readFileSync(path, "utf8")));
    const receipt = request.action === "worktree"
      ? prepareWorktree(request.repository, request.checkout, request.assignment)
      : receive(request.checkout, request.assignment);
    process.stdout.write(JSON.stringify(receipt, null, 2) + "\n");
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  }
}
