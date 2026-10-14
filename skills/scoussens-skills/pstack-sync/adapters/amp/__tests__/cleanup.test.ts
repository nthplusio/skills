/**
 * The cleanup tool in the port's `tools/cleanup.ts`: the archive set over a
 * fixture workspace against the fake `amp` on PATH, and the branch rule over
 * a scratch git repository with a bare `origin`.
 */
import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";
import {
  type BranchDecision,
  candidateBranches,
  parseArgs,
  planThreads,
  readCleanupWorkspace,
  runCleanup,
  type TaskStatus,
  TERMINAL,
  type ThreadDecision,
} from "../agent-runtime/scripts/tools/cleanup.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const FAKE_DIR = join(HERE, "fake-amp");
const TOOL = join(HERE, "..", "agent-runtime", "scripts", "tools", "cleanup.ts");

const ROOT_ID = "T-01a13ae5-cb4f-75db-afe6-d0ac92ca7306";
const API_ID = "T-01a13ae9-a4f1-7058-9b7f-7707729e56d2";
const PAGE_ID = "T-01a13ae9-b11f-7400-87ed-38e984048585";
const README_ID = "T-01a13ae9-c0b9-7099-9a47-197569596be0";
const VERIFY_ID = "T-01a13ae9-d2c1-7a1b-8c3d-4e5f60718293";
const LATE_ID = "T-01a13ae9-e3d2-7b2c-9d4e-5f6071829304";
const SLUG = "index-sparklines";

let root: string;
let fakeAmpDir: string;
let workspace: string;
let env: NodeJS.ProcessEnv;
let lines: string[];

function row(name: string, status: TaskStatus, agentId: string | null, extra: Record<string, unknown> = {}) {
  return { name, type: "worker", branch: `orch/${SLUG}/${name}`, dependsOn: [], status, agentId, ...extra };
}

function writeWorkspace(tasks: unknown[], plan: Record<string, unknown> = {}): void {
  mkdirSync(workspace, { recursive: true });
  writeFileSync(
    join(workspace, "plan.json"),
    JSON.stringify({ goal: "Sparklines", rootSlug: SLUG, baseBranch: "main", repoUrl: "https://github.com/example/playgrounds", selfAgentId: ROOT_ID, tasks: [], ...plan })
  );
  writeFileSync(join(workspace, "state.json"), JSON.stringify({ rootSlug: SLUG, tasks }));
}

/** The fixture: two handed-off workers, one error, one running, one pending, an archived cancelled one, a verifier on the worker's branch, and a row that names the root's own thread. */
function fixtureTasks(): unknown[] {
  return [
    row("api", "handed-off", API_ID),
    row("page", "handed-off", PAGE_ID),
    row("readme", "error", README_ID),
    row("verify-api", "handed-off", VERIFY_ID, { type: "verifier", branch: `orch/${SLUG}/api` }),
    row("late", "running", LATE_ID),
    row("docs", "pending", null),
    row("dropped", "cancelled", "T-01a13ae9-f4e3-7c3d-ae5f-607182930415"),
    row("self", "handed-off", ROOT_ID),
  ];
}

function calls(): string[][] {
  const path = join(fakeAmpDir, "calls.log");
  if (!existsSync(path)) return [];
  return readFileSync(path, "utf8").split("\n").filter(Boolean).map(line => line.split("\t"));
}

function archivedIds(): string[] {
  return calls().filter(c => c[0] === "threads" && c[1] === "archive").map(c => c[2]);
}

function git(repo: string, ...args: string[]): string {
  return execFileSync("git", ["-C", repo, ...args], { encoding: "utf8", env, stdio: ["ignore", "pipe", "pipe"] }).trim();
}

/** `main` with `orch/<slug>/api` merged in, `orch/<slug>/page` ahead of it, both on a bare origin, and no ref for `readme`. */
function scratchRepo(): { repo: string; origin: string } {
  const origin = join(root, "origin.git");
  const repo = join(root, "checkout");
  execFileSync("git", ["init", "-q", "--bare", "-b", "main", origin], { env });
  execFileSync("git", ["init", "-q", "-b", "main", repo], { env });
  writeFileSync(join(repo, "README.md"), "hello\n");
  git(repo, "add", "README.md");
  git(repo, "commit", "-q", "-m", "init");
  git(repo, "checkout", "-q", "-b", `orch/${SLUG}/api`);
  writeFileSync(join(repo, "api.txt"), "series\n");
  git(repo, "add", "api.txt");
  git(repo, "commit", "-q", "-m", "api");
  git(repo, "checkout", "-q", "main");
  git(repo, "merge", "-q", "--no-ff", "-m", "merge api", `orch/${SLUG}/api`);
  git(repo, "checkout", "-q", "-b", `orch/${SLUG}/page`);
  writeFileSync(join(repo, "page.txt"), "svg\n");
  git(repo, "add", "page.txt");
  git(repo, "commit", "-q", "-m", "page");
  git(repo, "checkout", "-q", "main");
  git(repo, "remote", "add", "origin", origin);
  git(repo, "push", "-q", "origin", "main", `orch/${SLUG}/api`, `orch/${SLUG}/page`);
  return { repo, origin };
}

function branches(repo: string): string[] {
  return git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes/origin").split("\n").filter(Boolean).sort();
}

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "os4-cleanup-"));
  fakeAmpDir = join(root, "fake");
  mkdirSync(fakeAmpDir);
  workspace = join(root, ".orchestrate", SLUG);
  chmodSync(join(FAKE_DIR, "amp"), 0o755);
  lines = [];
  env = {
    ...process.env,
    PATH: `${FAKE_DIR}:${process.env.PATH ?? ""}`,
    FAKE_AMP_DIR: fakeAmpDir,
    FAKE_AMP_LOG: join(fakeAmpDir, "calls.log"),
    ORCHESTRATE_AMP_BIN: "",
    GIT_AUTHOR_NAME: "cleanup test",
    GIT_AUTHOR_EMAIL: "cleanup@example.invalid",
    GIT_COMMITTER_NAME: "cleanup test",
    GIT_COMMITTER_EMAIL: "cleanup@example.invalid",
    GIT_CONFIG_GLOBAL: join(root, "no-gitconfig"),
    GIT_CONFIG_SYSTEM: join(root, "no-gitconfig"),
  };
});

afterEach(() => {
  rmSync(root, { recursive: true, force: true });
});

describe("threads", () => {
  test("archives exactly the terminal non-root tasks that are still open", () => {
    writeWorkspace(fixtureTasks());
    const dropped = "T-01a13ae9-f4e3-7c3d-ae5f-607182930415";
    writeFileSync(join(fakeAmpDir, `search-${dropped}.json`), JSON.stringify([{ id: dropped, archived: true }]));
    const report = runCleanup({ workspace, env, cwd: root, log: line => lines.push(line) });
    expect(archivedIds()).toEqual([API_ID, PAGE_ID, README_ID, VERIFY_ID]);
    expect(report.archived).toBe(4);
    expect(report.failed).toBe(0);
    // One search per terminal non-root thread, before its archive; none for the root or the running task.
    const searched = calls().filter(c => c[0] === "threads" && c[1] === "search").map(c => c[2]);
    expect(searched).toEqual([API_ID, PAGE_ID, README_ID, VERIFY_ID, dropped].map(id => `id:${id} archived:true`));
    expect(lines).toContain(`skip thread ${dropped} (dropped): already archived`);
    expect(lines).toContain(`keep thread ${ROOT_ID} (self): root planner`);
    expect(lines[lines.length - 1]).toBe(`cleanup ${SLUG}: archived 4 thread(s), kept the root`);
    expect(existsSync(join(fakeAmpDir, `archived-${LATE_ID}`))).toBe(false);
    expect(existsSync(join(fakeAmpDir, `archived-${ROOT_ID}`))).toBe(false);
  });

  test("never archives the root planner and reruns archive nothing twice", () => {
    writeWorkspace(fixtureTasks());
    runCleanup({ workspace, env, cwd: root, log: () => {} });
    // The first pass archived four; make the fake's search report them, as the real CLI would.
    for (const id of archivedIds()) writeFileSync(join(fakeAmpDir, `search-${id}.json`), JSON.stringify([{ id }]));
    const before = archivedIds().length;
    const report = runCleanup({ workspace, env, cwd: root, log: line => lines.push(line) });
    expect(archivedIds().length).toBe(before);
    expect(report.archived).toBe(0);
    expect(archivedIds()).not.toContain(ROOT_ID);
    expect(calls().some(c => c.includes("--unarchive"))).toBe(false);
  });

  test("planThreads classifies every row", () => {
    writeWorkspace([...fixtureTasks(), row("gone", "pruned", null)]);
    const ws = readCleanupWorkspace(workspace);
    const decisions = planThreads(ws, id => id === VERIFY_ID);
    const byTask = Object.fromEntries(decisions.map(d => [d.task, d])) as Record<string, ThreadDecision>;
    expect(byTask.api).toEqual({ task: "api", agentId: API_ID, action: "archive" });
    expect(byTask["verify-api"]).toEqual({ task: "verify-api", agentId: VERIFY_ID, action: "skip", reason: "archived" });
    expect(byTask.late).toEqual({ task: "late", agentId: LATE_ID, action: "skip", reason: "not-terminal" });
    expect(byTask.docs).toEqual({ task: "docs", agentId: null, action: "skip", reason: "not-terminal" });
    expect(byTask.gone).toEqual({ task: "gone", agentId: null, action: "skip", reason: "no-thread" });
    expect(byTask.self).toEqual({ task: "self", agentId: ROOT_ID, action: "skip", reason: "root" });
    expect([...TERMINAL]).toEqual(["handed-off", "error", "cancelled", "pruned"]);
  });

  test("a failed archive is counted and reported, not thrown", () => {
    writeWorkspace([row("api", "handed-off", API_ID)]);
    const failing = (cmd: string, args: string[]) =>
      args[1] === "archive" ? { code: 1, stdout: "", stderr: "Error: network down" } : { code: 0, stdout: "[]", stderr: "" };
    const report = runCleanup({ workspace, env, cwd: root, run: failing, log: line => lines.push(line) });
    expect(report.failed).toBe(1);
    expect(lines).toContain(`failed to archive thread ${API_ID} (api): Error: network down`);
    expect(lines[lines.length - 1]).toBe(`cleanup ${SLUG}: archived 0 thread(s), 1 failed`);
  });
});

describe("branches", () => {
  test("deletes the branches the integration branch contains and keeps the rest", () => {
    const { repo } = scratchRepo();
    writeWorkspace(fixtureTasks());
    expect(candidateBranches(readCleanupWorkspace(workspace))).toEqual([
      `orch/${SLUG}/api`,
      `orch/${SLUG}/page`,
      `orch/${SLUG}/readme`,
      `orch/${SLUG}/dropped`,
      `orch/${SLUG}/self`,
    ]);
    const report = runCleanup({ workspace, branches: true, repoPath: repo, env, cwd: root, log: line => lines.push(line) });
    expect(report.integration).toBe("main");
    const byBranch = Object.fromEntries(report.branches.map(d => [d.branch, d])) as Record<string, BranchDecision>;
    expect(byBranch[`orch/${SLUG}/api`]).toEqual({ branch: `orch/${SLUG}/api`, action: "delete", local: true, remote: true });
    expect(byBranch[`orch/${SLUG}/page`]).toEqual({ branch: `orch/${SLUG}/page`, action: "keep", reason: "not-contained" });
    expect(byBranch[`orch/${SLUG}/readme`]).toEqual({ branch: `orch/${SLUG}/readme`, action: "keep", reason: "no-ref" });
    expect(report.deleted).toBe(1);
    expect(report.failed).toBe(0);
    expect(branches(repo)).toEqual(["main", `orch/${SLUG}/page`, `origin/main`, `origin/orch/${SLUG}/page`]);
    expect(lines).toContain(`deleted branch orch/${SLUG}/api (local and origin): contained in main`);
    expect(lines).toContain(`keep branch orch/${SLUG}/page: not contained in main`);
    // No search fixture for `dropped` here, so it is open and archived too.
    expect(lines[lines.length - 1]).toBe(`cleanup ${SLUG}: archived 5 thread(s), kept the root, deleted 1 branch(es), kept 4`);
  });

  test("--integration names the branch and the integration branch itself is kept", () => {
    const { repo } = scratchRepo();
    // `page` contains `api` (it branched from the merge commit), so against `page` both are contained; `page` is the integration branch and stays.
    writeWorkspace([row("api", "handed-off", API_ID), row("page", "handed-off", PAGE_ID)]);
    const report = runCleanup({ workspace, branches: true, repoPath: repo, integration: `orch/${SLUG}/page`, env, cwd: root, log: line => lines.push(line) });
    expect(report.branches).toEqual([
      { branch: `orch/${SLUG}/api`, action: "delete", local: true, remote: true },
      { branch: `orch/${SLUG}/page`, action: "keep", reason: "integration" },
    ]);
    expect(branches(repo)).toContain(`orch/${SLUG}/page`);
    expect(branches(repo)).not.toContain(`orch/${SLUG}/api`);
  });

  test("a branch of a task that is not terminal is not a candidate", () => {
    const { repo } = scratchRepo();
    writeWorkspace([row("api", "running", API_ID)]);
    const report = runCleanup({ workspace, branches: true, repoPath: repo, env, cwd: root, log: () => {} });
    expect(report.branches).toEqual([]);
    expect(branches(repo)).toContain(`orch/${SLUG}/api`);
  });

  test("an integration branch with no ref is an error, not a deletion", () => {
    const { repo } = scratchRepo();
    writeWorkspace([row("api", "handed-off", API_ID)]);
    expect(() => runCleanup({ workspace, branches: true, repoPath: repo, integration: "release", env, cwd: root, log: () => {} })).toThrow(/integration branch release has no local or origin ref/);
    expect(branches(repo)).toContain(`orch/${SLUG}/api`);
  });
});

describe("dry run", () => {
  test("prints the plan and performs nothing", () => {
    const { repo } = scratchRepo();
    writeWorkspace(fixtureTasks());
    const report = runCleanup({ workspace, branches: true, repoPath: repo, dryRun: true, env, cwd: root, log: line => lines.push(line) });
    expect(report.dryRun).toBe(true);
    expect(report.archived).toBe(5);
    expect(report.deleted).toBe(1);
    expect(archivedIds()).toEqual([]);
    expect(calls().filter(c => c[1] === "archive")).toEqual([]);
    expect(branches(repo)).toContain(`orch/${SLUG}/api`);
    expect(branches(repo)).toContain(`origin/orch/${SLUG}/api`);
    expect(lines).toContain(`would archive thread ${API_ID} (api)`);
    expect(lines).toContain(`would delete branch orch/${SLUG}/api (local and origin): contained in main`);
    expect(lines[lines.length - 1]).toBe(`cleanup ${SLUG}: would archive 5 thread(s), kept the root, would delete 1 branch(es), kept 4`);
  });
});

describe("cli", () => {
  test("parseArgs reads the flags", () => {
    expect(parseArgs(["ws"])).toEqual({ workspace: "ws", branches: false, repoPath: undefined, integration: undefined, dryRun: false });
    expect(parseArgs(["ws", "--branches", "--repo-path", "/r", "--integration", "main", "--dry-run"])).toEqual({
      workspace: "ws",
      branches: true,
      repoPath: "/r",
      integration: "main",
      dryRun: true,
    });
  });

  test("the tool runs as a script against the fake amp and exits 0", () => {
    writeWorkspace([row("api", "handed-off", API_ID), row("late", "running", LATE_ID)]);
    const out = execFileSync("bun", [TOOL, workspace], { encoding: "utf8", env, cwd: root });
    expect(out.trim().split("\n")).toEqual([`archived thread ${API_ID} (api)`, `cleanup ${SLUG}: archived 1 thread(s)`]);
    expect(archivedIds()).toEqual([API_ID]);
  });

  test("a workspace without state.json exits 2", () => {
    mkdirSync(workspace, { recursive: true });
    writeFileSync(join(workspace, "plan.json"), "{}");
    let status = 0;
    let stderr = "";
    try {
      execFileSync("bun", [TOOL, workspace], { encoding: "utf8", env, cwd: root, stdio: ["ignore", "pipe", "pipe"] });
    } catch (err) {
      status = (err as { status: number }).status;
      stderr = (err as { stderr: string }).stderr;
    }
    expect(status).toBe(2);
    expect(stderr).toContain("state.json not readable");
  });
});
