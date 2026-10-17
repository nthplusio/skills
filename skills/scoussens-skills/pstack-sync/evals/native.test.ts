import { afterAll, beforeAll, beforeEach, describe, expect, test } from "bun:test";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { buildStatusRecord, readWorkspace } from "../adapters/amp/agent-runtime/scripts/tools/dashboard.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const PACK = resolve(HERE, "..");
const UPSTREAM = process.env.NATIVE_UPSTREAM_SCRIPTS;
const MODULES = process.env.NATIVE_NODE_MODULES ?? (UPSTREAM && join(UPSTREAM, "node_modules"));
const suite = UPSTREAM && MODULES ? describe : describe.skip;
const owner = { kind: "thread", harness: "amp", id: "actual-coordinator" };
const init = { action: "init", writer: "recorder", expectedRevision: 0, runId: "stable-run", dispatcher: owner, deliveryOwner: owner, scope: { reference: "approved-plan", revision: "v1" } };
const receipt = (task = "build", attemptId = "attempt-1", kind = "subagent") => ({
  task, attemptId, handle: { kind, harness: "native-test", id: `actual-${attemptId}` },
  coordinator: owner, actualParent: null, logicalParent: "root-plan",
});
const body = "## Status\nsuccess\n## Branch\n`feature/actual`\n## Verification\nunit-test-verified\n## PR\nhttps://github.com/example/repo/pull/42\n";
const pretty = (value: unknown) => JSON.stringify(value, null, 2) + "\n";
const digest = (value: string) => createHash("sha256").update(value).digest("hex");
let root: string;
let workspace: string;
let scripts: string;
function file(path: string) { return readFileSync(join(workspace, path), "utf8"); }
function state() { return JSON.parse(file("state.json")); }
function metadata() { return JSON.parse(file("native.json")); }
function cli(request: unknown) {
  const path = join(root, "request.json");
  writeFileSync(path, JSON.stringify(request));
  const result = Bun.spawnSync([process.execPath, join(scripts, "tools", "native.ts"), workspace, path]);
  return { code: result.exitCode, out: result.stdout.toString(), error: result.stderr.toString() };
}
function ok(request: unknown) {
  const result = cli(request);
  expect(result.error).toBe(""); expect(result.code).toBe(0);
  return JSON.parse(result.out);
}
function write(action: string, revision: number, extra = {}) {
  return ok({ action, writer: "recorder", expectedRevision: revision, ...extra });
}
function dispatch(revision = 1, value = receipt()) { return write("dispatch", revision, { receipt: value }); }
function complete(revision = 2, attemptId = "attempt-1", result = "finished", handoff = body) {
  return write("complete", revision, { attemptId, receipt: { result, body: handoff } });
}
function tree(path = workspace): Record<string, string> {
  return Object.fromEntries(readdirSync(path, { withFileTypes: true }).flatMap(entry => {
    const full = join(path, entry.name);
    return entry.isDirectory() ? Object.entries(tree(full)).map(([p, bytes]) => [`${entry.name}/${p}`, bytes]) : [[entry.name, readFileSync(full, "utf8")]];
  }));
}

suite("native recorder against an offline installed upstream tree", () => {
  beforeAll(() => {
    if (!UPSTREAM || !MODULES) throw new Error("set NATIVE_UPSTREAM_SCRIPTS and NATIVE_NODE_MODULES to offline upstream scripts and installed dependencies");
    root = mkdtempSync(join(tmpdir(), "native-recorder-eval-"));
    scripts = join(root, "orchestrate", "scripts");
    cpSync(UPSTREAM, scripts, { recursive: true, filter: path => !path.split("/").includes("node_modules") });
    cpSync(join(PACK, "adapters", "amp", "agent-runtime", "scripts"), scripts, { recursive: true });
    cpSync(join(PACK, "adapters", "amp", "models", "scripts"), scripts, { recursive: true });
    mkdirSync(join(scripts, "tools"), { recursive: true });
    cpSync(join(PACK, "scripts", "native.ts"), join(scripts, "tools", "native.ts"));
    symlinkSync(MODULES, join(root, "node_modules"), "dir");
  });
  beforeEach(() => {
    workspace = join(root, "workspace");
    rmSync(workspace, { recursive: true, force: true }); mkdirSync(workspace);
    writeFileSync(join(workspace, "plan.json"), pretty({
      rootSlug: "demo", goal: "Build and verify", baseBranch: "main", repoUrl: "https://github.com/example/repo",
      tasks: [{ name: "build", type: "worker", scopedGoal: "Build", maxAttempts: 2 },
        { name: "check", type: "verifier", verifies: "build", scopedGoal: "Verify" }],
    }));
  });
  afterAll(() => { if (root) rmSync(root, { recursive: true, force: true }); });

  test("derives visible names from immutable run identity without writing another registry", () => {
    expect(ok({ action: "preflight" }).naming).toBeNull();
    const initialized = ok(init);
    expect(initialized.naming).toEqual({
      prefix: "orch-843a13a480",
      dispatcherTitle: "[orch-843a13a480] dispatcher · demo",
      rootTitle: "[orch-843a13a480] root · demo",
      tasks: [
        { task: "build", title: "[orch-843a13a480] worker · build" },
        { task: "check", title: "[orch-843a13a480] verifier · check" },
      ],
    });
    const before = tree();
    expect(ok({ action: "inspect" }).naming).toEqual(initialized.naming);
    expect(tree()).toEqual(before);
    dispatch(); complete();
    expect(ok({ action: "preflight" }).naming).toEqual(initialized.naming);
    expect(cli({ ...init, runId: "another-run" }).error).toContain("run identity or owner conflict");
  });

  test("records exact state, real typed identities, parsed fields and handoff bytes", () => {
    const initialized = ok(init);
    expect(initialized.problems).toEqual([]);
    expect(state().tasks[0]).toEqual({ name: "build", type: "worker", branch: "orch/demo/build", startingRef: "main", dependsOn: [], agentId: null, runId: null, parentAgentId: null, status: "pending", resultStatus: null, handoffPath: null, startedAt: null, finishedAt: null, lastUpdate: null, note: null, slackTs: null, prNumber: null, failureMode: null, verification: null });
    dispatch();
    expect(state().tasks[0]).toMatchObject({ status: "running", agentId: "actual-attempt-1", runId: "attempt-1", parentAgentId: "actual-coordinator", attempts: 1 });
    expect(metadata().attempts[0]).toMatchObject({ handle: { kind: "subagent", harness: "native-test", id: "actual-attempt-1" }, actualParent: null, logicalParent: "root-plan" });
    complete();
    const row = state().tasks[0];
    expect(row).toMatchObject({ status: "handed-off", resultStatus: "finished", branch: "feature/actual", verification: "unit-test-verified", failureMode: null, prNumber: 42, handoffPath: `handoffs/${digest("attempt-1")}.md` });
    expect(file(row.handoffPath)).toBe(body);
    expect(metadata().attempts[0].completion).toEqual({ result: "finished", bodyHash: digest(body) });
    expect(metadata().attempts[0]).not.toHaveProperty("status");
    dispatch(3, receipt("check", "verify-1", "tool-call"));
    expect(state().tasks[1]).toMatchObject({ startingRef: "feature/actual", status: "running", agentId: "actual-verify-1", runId: "verify-1" });
  });

  test("exact receipts converge without changing bytes; changed owners and completions conflict", () => {
    ok(init); dispatch(); complete(); const before = tree();
    dispatch(); complete(); ok(init);
    expect(tree()).toEqual(before);
    expect(cli({ ...init, deliveryOwner: { ...owner, id: "someone-else" } }).error).toContain("owner conflict");
    expect(cli({ action: "dispatch", writer: "someone-else", expectedRevision: 3, receipt: receipt() }).error).toContain("writer conflict");
    expect(cli({ action: "dispatch", writer: "recorder", expectedRevision: 3, receipt: { ...receipt(), coordinator: { ...owner, id: "other-coordinator" } } }).error).toContain("duplicate dispatch");
    expect(cli({ action: "dispatch", writer: "recorder", expectedRevision: 3, receipt: receipt("build", "another") }).error).toContain("duplicate dispatch");
    expect(cli({ action: "complete", writer: "recorder", expectedRevision: 3, attemptId: "attempt-1", receipt: { result: "finished", body: "different bytes" } }).error).toContain("conflicting terminal");
    expect(tree()).toEqual(before);
  });

  test("unmet verifier dependency, stale revisions, unknown running outcome and invalid handles fail closed", () => {
    ok(init);
    expect(cli({ action: "dispatch", writer: "recorder", expectedRevision: 1, receipt: receipt("check", "verify-1") }).error).toContain("unmet dependency");
    expect(cli({ action: "dispatch", writer: "recorder", expectedRevision: 0, receipt: receipt() }).error).toContain("expectedRevision conflict");
    expect(cli({ action: "dispatch", writer: "recorder", expectedRevision: 1, receipt: { ...receipt(), handle: { kind: "unknown", harness: "native-test", id: "x" } } }).code).toBe(1);
    dispatch(); const before = tree();
    const preflight = ok({ action: "preflight" });
    expect(preflight.problems.join("\n")).toContain("unknown execution outcome: build");
    expect(preflight.safeNextAction).toContain("do not automatically spawn or retry");
    expect(tree()).toEqual(before);
    expect(cli({ action: "dispatch", writer: "recorder", expectedRevision: 2, receipt: receipt("build", "another") }).error).toContain("duplicate dispatch");
  });

  test("preserves failed attempts and their handoffs on an explicit new attempt", () => {
    ok(init); dispatch(); complete(2, "attempt-1", "error", "## Failure Mode\ntool-error\n");
    const firstPath = state().tasks[0].handoffPath;
    expect(state().tasks[0]).toMatchObject({ status: "error", failureMode: "tool-error" });
    dispatch(3, receipt("build", "attempt-2")); complete(4, "attempt-2");
    expect(file(firstPath)).toBe("## Failure Mode\ntool-error\n");
    expect(metadata().attempts.map((a: { completion: unknown }) => a.completion)).toHaveLength(2);
    expect(state().tasks[0]).toMatchObject({ status: "handed-off", attempts: 2, failureMode: null });
  });

  test("a collected blocked handoff does not satisfy a dependent task", () => {
    ok(init); dispatch(); complete(2, "attempt-1", "finished", "## Status\nblocked\n");
    expect(state().tasks[0].status).toBe("handed-off");
    expect(cli({ action: "dispatch", writer: "recorder", expectedRevision: 3, receipt: receipt("check", "verify-1") }).error).toContain("dependency did not report success");
  });

  test("independent verifier verdicts supersede self-reports on the exact target and gate dependents", () => {
    for (const verdict of ["verifier-failed", "live-ui-verified"]) {
      rmSync(workspace, { recursive: true }); mkdirSync(workspace);
      writeFileSync(join(workspace, "plan.json"), pretty({
        rootSlug: "demo", goal: "Build and verify", baseBranch: "main", repoUrl: "https://github.com/example/repo",
        tasks: [{ name: "build", type: "worker", scopedGoal: "Build" },
          { name: "check", type: "verifier", verifies: "build", scopedGoal: "Verify" },
          { name: "next", type: "worker", scopedGoal: "Use build", dependsOn: ["build"] }],
      }));
      ok(init); dispatch();
      complete(2, "attempt-1", "finished", verdict === "verifier-failed" ? body : "## Status\nsuccess\n");
      dispatch(3, receipt("check", "verify-1"));
      expect(metadata().attempts[1].verificationTarget).toEqual({ task: "build", attemptId: "attempt-1" });
      complete(4, "verify-1", "finished", `## Verification\n${verdict}\n`);
      expect(state().tasks[0].verification).toBe(verdict);
      const status = buildStatusRecord(readWorkspace(workspace), { contractVersion: "2", now: "2026-10-17T00:00:00Z", hosted: false, outPath: join(root, "preview.html") });
      expect(status.tasks[0].milestones.verification.state).toBe(verdict === "verifier-failed" ? "blocked" : "verified");
      expect(status.tasks[0].work.state).toBe(verdict === "verifier-failed" ? "needs_decision" : "delivered");
      expect(status.tasks[1].milestones.verification.state).toBe(verdict === "verifier-failed" ? "blocked" : "verified");
      const next = cli({ action: "dispatch", writer: "recorder", expectedRevision: 5, receipt: receipt("next", "next-1") });
      if (verdict === "verifier-failed") expect(next.error).toContain("unmet dependency: build");
      else expect(next.code).toBe(0);
    }
  });

  test("a running verifier cannot be silently retargeted by a plan revision", () => {
    ok(init); dispatch(); complete(); dispatch(3, receipt("check", "verify-1"));
    const plan = JSON.parse(file("plan.json"));
    plan.tasks.push({ name: "other", type: "worker", scopedGoal: "Other target" });
    plan.tasks[1].verifies = "other";
    writeFileSync(join(workspace, "plan.json"), pretty(plan));
    const before = tree();
    expect(cli({ action: "reconcile", writer: "recorder", expectedRevision: 4 }).error).toContain("cannot retarget active verifier");
    expect(tree()).toEqual(before);
  });

  test("one retained owner can own sequential work units with distinct actual attempts", () => {
    ok(init); dispatch(); complete();
    dispatch(3, { ...receipt("check", "verify-1"), handle: receipt().handle });
    expect(state().tasks.map((t: { agentId: string }) => t.agentId)).toEqual(["actual-attempt-1", "actual-attempt-1"]);
    expect(state().tasks.map((t: { runId: string }) => t.runId)).toEqual(["attempt-1", "verify-1"]);
  });

  test("unknown writes require reconciliation, which preserves Andon on scope supersession", () => {
    ok(init);
    const changed = state();
    const hold = { raisedAt: "2026-10-17T00:00:00.000Z", reason: "security review", cleared: false, lastCheckedAt: "2026-10-17T00:00:00.000Z" };
    changed.andon = hold; writeFileSync(join(workspace, "state.json"), pretty(changed));
    const before = tree();
    expect(ok({ action: "preflight" }).problems).toContain("unknown write requires explicit reconciliation");
    expect(tree()).toEqual(before);
    expect(cli({ action: "dispatch", writer: "recorder", expectedRevision: 1, receipt: receipt() }).error).toContain("unknown write");
    write("reconcile", 1, { scope: { reference: "new decision", revision: "v2" } });
    expect(state().andon).toEqual(hold);
    expect(cli({ action: "dispatch", writer: "recorder", expectedRevision: 2, receipt: receipt() }).error).toContain("Andon hold");
    expect(state().andon).toEqual(hold);
  });

  test("recovers a partial multi-file completion by identical request or explicit recover", () => {
    for (const recovery of ["repeat", "recover"]) {
      if (existsSync(join(workspace, "state.json"))) { rmSync(join(workspace, "state.json")); rmSync(join(workspace, "native.json")); rmSync(join(workspace, "handoffs"), { recursive: true, force: true }); }
      ok(init); dispatch();
      const beforeState = file("state.json"), beforeMeta = file("native.json");
      complete(); const expected = tree(); const afterState = file("state.json"), afterMeta = file("native.json");
      const path = state().tasks[0].handoffPath;
      const request = { action: "complete", expectedRevision: 2, writer: "recorder", attemptId: "attempt-1", receipt: { result: "finished", body } };
      writeFileSync(join(workspace, "state.json"), beforeState); writeFileSync(join(workspace, "native.json"), beforeMeta);
      writeFileSync(join(workspace, "native.transaction.json"), pretty({ version: 1, writer: "recorder", revision: 3,
        requestHash: digest(pretty(request)), files: [{ path, before: null, after: body }, { path: "state.json", before: beforeState, after: afterState }, { path: "native.json", before: beforeMeta, after: afterMeta }] }));
      const interrupted = tree();
      const preflight = ok({ action: "preflight" });
      expect(preflight.pendingTransaction).toBe(true);
      expect(preflight.recovery).toEqual({ action: "recover", writer: "recorder", expectedRevision: 2 });
      expect(tree()).toEqual(interrupted);
      if (recovery === "recover") write("recover", 2); else ok(request);
      expect(tree()).toEqual(expected);
    }
  });

  test("missing and changed handoffs are reported without writes", () => {
    ok(init); dispatch(); complete(); const path = state().tasks[0].handoffPath;
    writeFileSync(join(workspace, path), "corrupted"); const changed = tree();
    expect(ok({ action: "preflight" }).problems).toContain("conflicting handoff: build"); expect(tree()).toEqual(changed);
    expect(cli({ action: "complete", expectedRevision: 2, writer: "recorder", attemptId: "attempt-1", receipt: { result: "finished", body } }).error).toContain("conflicting handoff");
    expect(tree()).toEqual(changed);
    rmSync(join(workspace, path)); const missing = tree();
    expect(ok({ action: "preflight" }).problems).toContain("missing handoff: build"); expect(tree()).toEqual(missing);
  });

  test("exclusive writer lock never auto-reclaims another writer", () => {
    ok(init); writeFileSync(join(workspace, "native.lock"), pretty({ pid: process.pid })); const before = tree();
    expect(cli({ action: "reconcile", writer: "recorder", expectedRevision: 1 }).error).toContain("writer lock held");
    expect(tree()).toEqual(before);
  });

  test("scope updates preserve file-based security holds and observations do not invent lifecycle transitions", () => {
    ok(init); dispatch();
    write("observe", 2, { attemptId: "attempt-1", note: "Native tool reports still running" });
    expect(state().tasks[0]).toMatchObject({ status: "running", runId: "attempt-1", finishedAt: null, resultStatus: null });
    expect(metadata().attempts[0].observations).toEqual(["Native tool reports still running"]);
    complete(3);
    writeFileSync(join(workspace, "andon.json"), pretty({ reason: "security stop", raisedBy: "operator" }));
    const hold = file("andon.json");
    write("reconcile", 4, { scope: { reference: "superseding-plan", revision: "v2" } });
    expect(file("andon.json")).toBe(hold);
    expect(ok({ action: "preflight" }).problems).toContain("Andon file hold requires operator resolution");
    expect(cli({ action: "dispatch", writer: "recorder", expectedRevision: 5, receipt: receipt("check", "verify-1") }).error).toContain("Andon hold");
    expect(file("andon.json")).toBe(hold);
  });

  test("scripted manager load and run refuse native ownership before runtime authentication", () => {
    ok(init); const before = tree();
    const manager = Bun.spawnSync([process.execPath, "-e", `const { AgentManager } = await import(${JSON.stringify(join(scripts, "core", "agent-manager.ts"))}); await AgentManager.load(${JSON.stringify(workspace)});`]);
    expect(manager.exitCode).toBe(1); expect(manager.stderr.toString()).toContain("native-owned workspace refuses scripted load/run");
    const run = Bun.spawnSync([process.execPath, join(scripts, "cli.ts"), "run", workspace]);
    expect(run.exitCode).toBe(1); expect(run.stderr.toString()).toContain("native-owned workspace refuses scripted load/run");
    expect(tree()).toEqual(before);
  });
});
