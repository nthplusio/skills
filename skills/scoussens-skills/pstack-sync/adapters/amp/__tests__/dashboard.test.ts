/**
 * The dashboard producer in the port's `tools/dashboard.ts`: a status record
 * built from a fixture run workspace, then the dashboard skill's real
 * renderer run on it. The pack layout resolves the skill at
 * `skills/scoussens-skills/dashboard`, the same directory the installed
 * layout finds beside `orchestrate/`.
 */
import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  buildStatusRecord,
  dashboardCandidateDirs,
  hashedDashboardDirs,
  parseHandoff,
  readContractVersion,
  readWorkspace,
  renderStatus,
  resolveDashboardDir,
  writeJsonAtomic,
} from "../agent-runtime/scripts/tools/dashboard.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const TOOL = join(HERE, "..", "agent-runtime", "scripts", "tools", "dashboard.ts");
const PACK_DASHBOARD = join(HERE, "..", "..", "..", "..", "dashboard");

const ROOT_ID = "T-01a13ae5-cb4f-75db-afe6-d0ac92ca7306";
const API_ID = "T-01a13ae9-a4f1-7058-9b7f-7707729e56d2";
const PAGE_ID = "T-01a13ae9-b11f-7400-87ed-38e984048585";
const README_ID = "T-01a13ae9-c0b9-7099-9a47-197569596be0";

let root: string;
let workspace: string;

function writeFixture(dir: string): void {
  mkdirSync(join(dir, "handoffs"), { recursive: true });
  writeFileSync(
    join(dir, "plan.json"),
    JSON.stringify({
      goal: "Add intraday sparklines to the index board.",
      summary: "Sparklines on every index card",
      rootSlug: "index-sparklines",
      baseBranch: "main",
      repoUrl: "https://github.com/example/playgrounds",
      selfAgentId: ROOT_ID,
      tasks: [
        { name: "api", type: "worker", scopedGoal: "Return a series per index from /api/quotes. Keep the cache.", acceptance: ["bun test index-board passes"] },
        { name: "page", type: "worker", scopedGoal: "Draw each series as an inline SVG.", dependsOn: ["api"] },
        { name: "readme", type: "worker", scopedGoal: "Add one README sentence.", openPR: false },
      ],
    })
  );
  const row = (name: string, extra: Record<string, unknown>) => ({
    name,
    type: "worker",
    branch: `orch/index-sparklines/${name}`,
    startingRef: "main",
    dependsOn: [],
    agentId: null,
    runId: null,
    parentAgentId: ROOT_ID,
    status: "pending",
    resultStatus: null,
    handoffPath: null,
    startedAt: null,
    finishedAt: null,
    lastUpdate: null,
    note: null,
    slackTs: null,
    prNumber: null,
    failureMode: null,
    verification: null,
    ...extra,
  });
  writeFileSync(
    join(dir, "state.json"),
    JSON.stringify({
      rootSlug: "index-sparklines",
      tasks: [
        row("api", {
          agentId: API_ID,
          runId: "m0",
          status: "handed-off",
          resultStatus: "finished",
          handoffPath: "handoffs/api.md",
          startedAt: "2026-10-14T14:55:51.731Z",
          finishedAt: "2026-10-14T14:58:54.296Z",
          verification: "unit-test-verified",
        }),
        row("page", {
          agentId: PAGE_ID,
          runId: "m0",
          status: "running",
          dependsOn: ["api"],
          startedAt: "2026-10-14T14:59:00.000Z",
          lastUpdate: "2026-10-14T15:01:00.000Z",
          note: "Drawing the SVG paths.",
        }),
        row("readme", {
          agentId: README_ID,
          runId: "m0",
          status: "error",
          resultStatus: "error",
          handoffPath: "handoffs/readme.md",
          startedAt: "2026-10-14T14:55:59.219Z",
          finishedAt: "2026-10-14T14:57:28.120Z",
          failureMode: "tool-error",
          attempts: 1,
        }),
      ],
      attention: [{ at: "2026-10-14T14:57:28.125Z", message: "readme: run ended with status=error; see handoffs/readme-failure.md" }],
    })
  );
  writeFileSync(
    join(dir, "handoffs", "api.md"),
    [
      "<!-- orchestrate handoff",
      "task: api",
      "branch: orch/index-sparklines/api",
      `agentId: ${API_ID}`,
      "runId: m0",
      "resultStatus: finished",
      "finishedAt: 2026-10-14T14:58:54.296Z",
      "-->",
      "",
      "## Status",
      "success",
      "",
      "## Branch",
      "`orch/index-sparklines/api`",
      "",
      "## What I did",
      "- Added `series` to the quotes response.",
      "",
      "## Verification",
      "unit-test-verified",
      "",
    ].join("\n")
  );
  writeFileSync(
    join(dir, "handoffs", "readme-failure.md"),
    [
      "<!-- orchestrate failure handoff",
      "task: readme",
      "branch: orch/index-sparklines/readme",
      `agentId: ${README_ID}`,
      "runId: m0",
      "failureMode: tool-error",
      "terminatedAt: 2026-10-14T14:57:28.120Z",
      "-->",
      "",
      "# readme — failure handoff",
      "",
      "Status: error (worker thread terminated without writing a handoff)",
      "Failure mode: tool-error",
      "Branch: orch/index-sparklines/readme",
      "",
      "## Suggested next steps",
      "- Retry with a different model",
      "",
    ].join("\n")
  );
  writeFileSync(
    join(dir, "attention.log"),
    "[2026-10-14T14:57:28.125Z] readme: run ended with status=error; see handoffs/readme-failure.md\n"
  );
}

beforeAll(() => {
  root = mkdtempSync(join(tmpdir(), "rf-d-dashboard-"));
  workspace = join(root, ".orchestrate", "index-sparklines");
  writeFixture(workspace);
});

afterAll(() => {
  rmSync(root, { recursive: true, force: true });
});

describe("parseHandoff", () => {
  test("reads the Status, Verification and Branch sections of a worker handoff", () => {
    const parsed = parseHandoff("/x/handoffs/api.md", "## Status\nsuccess\n\n## Branch\n`orch/a/b`\n\n## Verification\nlive-ui-verified\n");
    expect(parsed).toEqual({ path: "/x/handoffs/api.md", status: "success", verification: "live-ui-verified", branch: "orch/a/b", publication: null });
  });

  test("reads the Status: and Branch: lines of a failure handoff, not the traceability comment", () => {
    const parsed = parseHandoff(
      "/x/handoffs/t-failure.md",
      "<!-- orchestrate failure handoff\ntask: t\nbranch: placeholder\n-->\n\nStatus: error (worker thread terminated)\nBranch: orch/x/t\n"
    );
    expect(parsed.status).toBe("error");
    expect(parsed.branch).toBe("orch/x/t");
    expect(parsed.verification).toBeNull();
  });

  test("a body without the sections yields nulls", () => {
    expect(parseHandoff("/x/h.md", "I ran out of context.\n")).toEqual({ path: "/x/h.md", status: null, verification: null, branch: null, publication: null });
  });
});

describe("buildStatusRecord", () => {
  const now = "2026-10-14T16:00:00.000Z";

  test("one row per task with the thread as owner and the agent state from the task status", () => {
    const snapshot = readWorkspace(workspace);
    const record = buildStatusRecord(snapshot, { now, contractVersion: "2", outPath: join(workspace, "dashboard.html") });
    expect(record.schema_version).toBe(2);
    expect(record.run_id).toBe(`index-sparklines-${ROOT_ID}`);
    expect(record.title).toBe("Sparklines on every index card");
    expect(record.goal).toBe("Add intraday sparklines to the index board.");
    expect(record.updated_at).toBe(now);
    expect(record.contract_version).toBe("2");
    expect(record.presentation.coordinator_href).toBe(`https://ampcode.com/threads/${ROOT_ID}`);
    expect("closed_at" in record).toBe(false);

    expect(record.tasks).toHaveLength(3);
    expect(record.tasks.map(row => row.id)).toEqual(["api", "page", "readme"]);
    expect(record.tasks.map(row => row.owner.id)).toEqual([API_ID, PAGE_ID, README_ID]);
    expect(record.tasks.map(row => row.owner.label)).toEqual(["api", "page", "readme"]);
    expect(record.tasks.map(row => row.owner.state)).toEqual(["complete", "active", "blocked"]);
    expect(record.tasks.map(row => row.owner.href)).toEqual([
      `https://ampcode.com/threads/${API_ID}`,
      `https://ampcode.com/threads/${PAGE_ID}`,
      `https://ampcode.com/threads/${README_ID}`,
    ]);
    expect(record.tasks.map(row => row.work.state)).toEqual(["delivered", "working", "blocked"]);
    expect(record.tasks[0].title).toBe("Return a series per index from /api/quotes.");
    expect(record.tasks[1].owner.activity).toBe("Drawing the SVG paths.");
    expect(record.tasks[1].blocked_by).toEqual([]);
    expect(record.tasks[2].blocker).toContain("tool-error");
  });

  test("a branch-only handoff is implemented but unpublished, verification from state.json", () => {
    const record = buildStatusRecord(readWorkspace(workspace), { now, contractVersion: "2", outPath: join(workspace, "dashboard.html") });
    const [api, page, readme] = record.tasks;
    expect(api.milestones.pr_readiness?.state).toBe("verified");
    expect(api.milestones.code_publication?.state).toBe("pending");
    expect(api.milestones.code_publication?.note).toContain("No valid publication receipt");
    expect(api.milestones.verification?.state).toBe("verified");
    expect(api.milestones.deployment?.state).toBe("not_requested");
    expect(page.milestones.pr_readiness?.state).toBe("pending");
    expect(page.milestones.code_publication?.state).toBe("pending");
    expect(readme.milestones.pr_readiness?.state).toBe("blocked");
    expect(readme.milestones.code_publication?.state).toBe("pending");
  });

  test("an explicit exact-code receipt is retained as publication evidence", () => {
    const snapshot = readWorkspace(workspace);
    const receipt = { repo: "https://github.com/example/playgrounds", remote_ref: "refs/heads/orch/index-sparklines/api", observed_commit_sha: "0123456789abcdef0123456789abcdef01234567" };
    snapshot.handoffs.set("api", parseHandoff("/x/handoffs/api.md", `## Status\nsuccess\n## Publication receipt\n${JSON.stringify(receipt)}\n`));
    const record = buildStatusRecord(snapshot, { now, contractVersion: "2", outPath: join(workspace, "dashboard.html") });
    expect(record.tasks[0].milestones.code_publication?.state).toBe("verified");
    for (const value of Object.values(receipt)) {
      expect(record.tasks[0].milestones.code_publication?.note).toContain(value);
      expect(record.evidence[0].output).toContain(value);
    }
    expect(record.tasks[0].milestones.business_acceptance?.state).toBe("not_requested");
  });

  test("invalid receipts never establish publication", () => {
    const receipt = { repo: "https://github.com/example/playgrounds", remote_ref: "refs/heads/api", observed_commit_sha: "a".repeat(40) };
    for (const invalid of ["not JSON", "null", "{}", JSON.stringify({ ...receipt, observed_commit_sha: "abc123" }), JSON.stringify({ ...receipt, observed_commit_sha: "0".repeat(40) }), JSON.stringify({ ...receipt, remote_ref: "api" }), JSON.stringify({ ...receipt, repo: "file:///tmp/repo" })]) {
      const snapshot = readWorkspace(workspace);
      const handoff = parseHandoff("/x/handoffs/api.md", `## Status\nsuccess\n## Branch\napi\n## Publication receipt\n${invalid}\n`);
      expect(handoff.publication).toBeNull();
      snapshot.handoffs.set("api", handoff);
      const record = buildStatusRecord(snapshot, { now, contractVersion: "2", outPath: join(workspace, "dashboard.html") });
      expect(record.tasks[0].milestones.code_publication?.state).toBe("pending");
    }
  });

  test("unit and typecheck evidence never establishes business acceptance", () => {
    for (const verdict of ["unit-test-verified", "type-check-only"]) {
      const snapshot = readWorkspace(workspace);
      snapshot.handoffs.set("api", parseHandoff("/x/handoffs/api.md", `## Status\nsuccess\n## Verification\n${verdict}\n`));
      const record = buildStatusRecord(snapshot, { now, contractVersion: "2", outPath: join(workspace, "dashboard.html") });
      expect(record.evidence[0].assessment).toBe("limited");
      expect(record.evidence[0].note).toContain(verdict);
      expect(record.tasks[0].milestones.business_acceptance?.state).toBe("not_requested");
    }
  });

  test("evidence comes from each handoff's status and branch lines and names the file", () => {
    const record = buildStatusRecord(readWorkspace(workspace), { now, contractVersion: "2", outPath: join(workspace, "dashboard.html") });
    expect(record.evidence.map(item => item.id)).toEqual(["handoff-api", "handoff-readme"]);
    const [api, readme] = record.evidence;
    expect(api.result).toBe("passed");
    expect(api.assessment).toBe("limited");
    expect(api.note).toBe("Status: success · Verification: unit-test-verified · Branch: orch/index-sparklines/api");
    expect(api.href).toBe("handoffs/api.md");
    expect(api.output).toContain("File: handoffs/api.md");
    expect(readme.result).toBe("failed");
    expect(readme.href).toBe("handoffs/readme-failure.md");
    expect(record.tasks[0].work.evidence).toEqual(["handoff-api"]);
    expect(record.tasks[0].owner.handoff).toBe("handoffs/api.md: Status: success · Verification: unit-test-verified · Branch: orch/index-sparklines/api");
    expect(record.history).toEqual(["[2026-10-14T14:57:28.125Z] readme: run ended with status=error; see handoffs/readme-failure.md"]);
    expect(record.decisions).toEqual([]);
  });

  test("--hosted leaves local handoff links out and keeps the literal output", () => {
    const record = buildStatusRecord(readWorkspace(workspace), { now, contractVersion: "2", outPath: join(workspace, "dashboard.html"), hosted: true });
    expect(record.evidence.every(item => item.href === "" && item.output.length > 0)).toBe(true);
  });

  test("a page outside the workspace gets absolute handoff links", () => {
    const record = buildStatusRecord(readWorkspace(workspace), { now, contractVersion: "2", outPath: join(root, "elsewhere", "page.html") });
    expect(record.evidence[0].href).toBe(join(workspace, "handoffs", "api.md"));
  });

  test("an uncleared Andon becomes the one decision, routed to the root planner thread", () => {
    const snapshot = readWorkspace(workspace);
    snapshot.state.andon = { raisedAt: "2026-10-14T15:00:00.000Z", raisedBy: "operator", reason: "Yahoo is rate limiting", lastCheckedAt: "2026-10-14T15:00:00.000Z" } as never;
    const record = buildStatusRecord(snapshot, { now, contractVersion: "2", outPath: join(workspace, "dashboard.html") });
    expect(record.decisions).toHaveLength(1);
    expect(record.decisions[0].id).toBe("andon");
    expect(record.decisions[0].text).toContain("Yahoo is rate limiting");
    expect(record.decisions[0].task_ids).toEqual(["page"]);
    expect(record.decisions[0].discussion).toEqual({ owner_id: ROOT_ID, label: "Root planner thread", href: `https://ampcode.com/threads/${ROOT_ID}` });
  });

  test("a task without a thread yet waits with a placeholder owner and names its unmet dependencies", () => {
    const snapshot = readWorkspace(workspace);
    snapshot.state.tasks[1] = { ...snapshot.state.tasks[1], status: "pending", agentId: null, startedAt: null, note: null };
    snapshot.state.tasks[0] = { ...snapshot.state.tasks[0], status: "running" };
    const record = buildStatusRecord(snapshot, { now, contractVersion: "2", outPath: join(workspace, "dashboard.html") });
    expect(record.tasks[1].owner).toMatchObject({ id: "unassigned-page", state: "waiting" });
    expect(record.tasks[1].work.state).toBe("waiting");
    expect(record.tasks[1].blocked_by).toEqual(["api"]);
  });
});

describe("the dashboard skill lookup", () => {
  test("the pack layout resolves the skill beside pstack-sync, and ORCHESTRATE_DASHBOARD_DIR comes first", () => {
    expect(resolveDashboardDir({})).toBe(PACK_DASHBOARD);
    const dirs = dashboardCandidateDirs({ ORCHESTRATE_DASHBOARD_DIR: "/opt/dash" });
    expect(dirs[0]).toBe("/opt/dash");
    expect(dirs[dirs.length - 1]).toBe(PACK_DASHBOARD);
  });

  test("hashed siblings are those holding the renderer, newest first", () => {
    const cache = join(root, "cache");
    for (const name of ["dashboard@old", "dashboard@new", "dashboard@empty", "pstack-sync@x"]) {
      mkdirSync(join(cache, name, "scripts"), { recursive: true });
    }
    writeFileSync(join(cache, "dashboard@old", "scripts", "render_dashboard.py"), "");
    writeFileSync(join(cache, "dashboard@new", "scripts", "render_dashboard.py"), "");
    const past = new Date(Date.now() - 60_000);
    require("node:fs").utimesSync(join(cache, "dashboard@old"), past, past);
    expect(hashedDashboardDirs(cache)).toEqual([join(cache, "dashboard@new"), join(cache, "dashboard@old")]);
    expect(hashedDashboardDirs(join(root, "missing"))).toEqual([]);
  });
});

describe("the real renderer", () => {
  test("accepts the produced status.json and the page names the three tasks", () => {
    const dashboardDir = resolveDashboardDir({});
    const contractVersion = readContractVersion(dashboardDir);
    expect(contractVersion).toBe("2");
    const outPath = join(workspace, "dashboard.html");
    const record = buildStatusRecord(readWorkspace(workspace), { contractVersion, outPath });
    const statusPath = join(workspace, "status.json");
    writeJsonAtomic(statusPath, record);
    const result = renderStatus(dashboardDir, statusPath, outPath, false);
    expect(result.stderr).toBe("");
    expect(result.status).toBe(0);
    expect(result.stdout.trim()).toBe(`PASS: rendered ${outPath}`);
    const html = readFileSync(outPath, "utf8");
    expect(html.split("\n")[1]).toBe("<!-- dashboard contract 2 -->");
    for (const name of ["api", "page", "readme"]) {
      expect(html).toContain(`id="row-${name}"`);
      expect(html).toContain(`<small>${name}</small>`);
    }
    expect(html).toContain("Sparklines on every index card");
    expect(html).toContain(`https://ampcode.com/threads/${API_ID}`);
  });

  test("native identities keep logical lineage without inventing Amp thread links", () => {
    const dir = join(root, "native");
    writeFixture(dir);
    writeFileSync(join(dir, "native.json"), JSON.stringify({
      runId: "portable-run", scope: { reference: "approved-brief.md", revision: "2" },
      deliveryOwner: { kind: "subagent", harness: "codex", id: ROOT_ID },
      attempts: [
        { task: "api", attemptId: "m0", handle: { kind: "subagent", harness: "codex", id: API_ID }, logicalParent: "root-task" },
        { task: "page", attemptId: "m0", handle: { kind: "thread", harness: "amp", id: PAGE_ID }, logicalParent: "root-task" },
      ],
    }));
    const snapshot = readWorkspace(dir);
    const record = buildStatusRecord(snapshot, { contractVersion: "test", outPath: join(dir, "dashboard.html") });
    expect(record.run_id).toBe("portable-run");
    expect(record.harness_name).toBe("codex");
    expect(record.presentation.coordinator_href).toBeUndefined();
    expect(record.tasks[0].owner.id).toBe(`codex:subagent:${API_ID}`);
    expect(record.tasks[0].owner.href).toBeUndefined();
    expect(record.tasks[0].owner.activity).toContain("logical parent root-task");
    expect(record.tasks[1].owner.href).toBe(`https://ampcode.com/threads/${PAGE_ID}`);
    expect(record.tasks[1].next_action).toContain("native execution");
    expect(record.decisions).toEqual([]);
    expect(record.history.join("\n")).toContain("Scope 2: approved-brief.md");
  });

  test("the CLI writes status.json and the page, and exits 1 with the renderer's stderr when the record is rejected", () => {
    const run = Bun.spawnSync(["bun", TOOL, workspace, "--out", join(workspace, "cli.html")], { env: { ...process.env, ORCHESTRATE_DASHBOARD_DIR: "" } });
    expect(run.stderr.toString()).toBe("");
    expect(run.exitCode).toBe(0);
    expect(run.stdout.toString()).toContain("PASS: rendered");
    expect(existsSync(join(workspace, "status.json"))).toBe(true);
    expect(existsSync(join(workspace, "cli.html"))).toBe(true);

    // Reusing the actual owner retains both task rows and their answer route.
    const broken = join(root, "broken");
    writeFixture(broken);
    const state = JSON.parse(readFileSync(join(broken, "state.json"), "utf8"));
    state.tasks[1].agentId = API_ID;
    writeFileSync(join(broken, "state.json"), JSON.stringify(state));
    const shared = Bun.spawnSync(["bun", TOOL, broken]);
    expect(shared.exitCode).toBe(0);
    const html = readFileSync(join(broken, "dashboard.html"), "utf8");
    expect(html).toContain('id="row-api"');
    expect(html).toContain('id="row-page"');
    const record = JSON.parse(readFileSync(join(broken, "status.json"), "utf8"));
    expect(record.tasks[0].owner.id).toBe(API_ID);
    expect(record.tasks[1].owner.id).toBe(API_ID);

    state.tasks[1].name = "api";
    writeFileSync(join(broken, "state.json"), JSON.stringify(state));
    rmSync(join(broken, "handoffs", "api.md"));
    rmSync(join(broken, "dashboard.html"));
    const rejected = Bun.spawnSync(["bun", TOOL, broken]);
    expect(rejected.exitCode).toBe(1);
    expect(rejected.stderr.toString()).toContain("duplicate ID: api");
    expect(existsSync(join(broken, "status.json"))).toBe(true);
    expect(existsSync(join(broken, "dashboard.html"))).toBe(false);

    const statusOnly = Bun.spawnSync(["bun", TOOL, workspace, "--status-only", "--out", join(workspace, "never.html")]);
    expect(statusOnly.exitCode).toBe(0);
    expect(existsSync(join(workspace, "never.html"))).toBe(false);
  });
});
