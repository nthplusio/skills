/**
 * The preflight in the port's `tools/doctor.ts`. The `amp` calls reach the
 * fake `amp` on PATH through the real spawner where the fake can answer
 * (`threads list`); everything else (`projects get`, `git`, `gh`) is answered
 * by a fake command runner that records the argv arrays it was given.
 */
import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  type CheckResult,
  type CommandResult,
  type CommandRunner,
  defaultRunner,
  type DoctorReport,
  findOnPath,
  formatLine,
  githubOwnerRepo,
  parseArgs,
  renderJson,
  renderText,
  runDoctor,
} from "../agent-runtime/scripts/tools/doctor.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const ADAPTER = join(HERE, "..");
const FAKE_DIR = join(HERE, "fake-amp");
const DOCTOR = join(ADAPTER, "agent-runtime", "scripts", "tools", "doctor.ts");
const REPO = "https://github.com/nthplusio/skills";
const NOT_SIGNED_IN = "Error: Invalid or missing API key. Run 'amp login' to authenticate.";

const CHECK_NAMES = [
  "dependencies",
  "runtime",
  "amp-cli",
  "amp-auth",
  "amp-project",
  "push-access",
  "repo-url-env",
  "slack",
  "plan",
];

let root: string;
let fakeAmpDir: string;
let scriptsDir: string;
let workspace: string;
let binDir: string;
let env: NodeJS.ProcessEnv;

/** Answers by `<cmd> <args...>`; `amp threads ...` goes to the real fake on PATH. */
class FakeRunner {
  calls: { cmd: string; args: string[] }[] = [];
  answers = new Map<string, CommandResult>();

  answer(key: string, result: Partial<CommandResult>): void {
    this.answers.set(key, { code: 0, stdout: "", stderr: "", ...result });
  }

  run: CommandRunner = async (cmd, args, opts) => {
    this.calls.push({ cmd, args });
    const name = basename(cmd) === "amp" ? "amp" : cmd;
    const key = [name, ...args].join(" ");
    const canned = this.answers.get(key);
    if (canned) return canned;
    if (name === "amp" && args[0] === "threads") return defaultRunner(cmd, args, opts);
    return { code: 1, stdout: "", stderr: `fake runner: no answer for ${key}` };
  };
}

let runner: FakeRunner;

function validPlan(repoUrl = REPO): string {
  return JSON.stringify({
    goal: "say hi",
    rootSlug: "hi",
    baseBranch: "main",
    repoUrl,
    measurementsEnabled: true,
    tasks: [{ name: "hi", type: "worker", scopedGoal: "say hi" }],
  });
}

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "rf-doctor-"));
  fakeAmpDir = join(root, "fake-amp");
  scriptsDir = join(root, "scripts");
  workspace = join(root, "workspace");
  binDir = join(root, "bin");
  for (const d of [fakeAmpDir, join(scriptsDir, "node_modules"), workspace, binDir]) mkdirSync(d, { recursive: true });
  chmodSync(join(FAKE_DIR, "amp"), 0o755);
  writeFileSync(join(scriptsDir, "package.json"), "{}");
  // A stand-in for upstream's strict schema: the doctor must hand it the plan
  // text with the adapter's `measurementsEnabled` lifted out.
  writeFileSync(
    join(scriptsDir, "schemas.ts"),
    [
      "export function parsePlanJson(text: string, source: string) {",
      "  const plan = JSON.parse(text);",
      '  if ("measurementsEnabled" in plan) throw new Error(`${source}: unrecognized key measurementsEnabled`);',
      '  if (typeof plan.repoUrl !== "string" || !Array.isArray(plan.tasks) || plan.tasks.length === 0) {',
      "    throw new Error(`${source}: tasks must be a non-empty array`);",
      "  }",
      "  return plan;",
      "}",
      "",
    ].join("\n")
  );
  writeFileSync(join(workspace, "plan.json"), validPlan());
  writeFileSync(join(binDir, "gh"), "#!/bin/sh\nexit 0\n");
  chmodSync(join(binDir, "gh"), 0o755);
  env = {
    ...process.env,
    PATH: `${FAKE_DIR}:${process.env.PATH ?? ""}`,
    FAKE_AMP_DIR: fakeAmpDir,
    FAKE_AMP_LOG: join(fakeAmpDir, "calls.log"),
    ORCHESTRATE_AMP_BIN: "",
    ORCHESTRATE_REPO_URL: "https://github.com/NthPlusIO/skills.git",
    SLACK_BOT_TOKEN: "",
  };
  runner = new FakeRunner();
  runner.answer(`amp projects get ${REPO} --json`, {
    stdout: JSON.stringify({ url: "https://ampcode.com/@nthplusio/skills", repositoryURL: REPO }),
  });
  runner.answer(`git -C ${workspace} rev-parse --show-toplevel`, { stdout: `${workspace}\n` });
  runner.answer(`git -C ${workspace} remote get-url origin`, { stdout: "git@github.com:NthPlusIO/skills.git\n" });
  runner.answer(`git -C ${workspace} push --dry-run origin HEAD:refs/heads/orchestrate-doctor-probe`, { code: 0 });
});

afterEach(() => {
  rmSync(root, { recursive: true, force: true });
});

function doctor(overrides: Parameters<typeof runDoctor>[0] = {}): Promise<DoctorReport> {
  return runDoctor({
    repo: REPO,
    workspace,
    env,
    cwd: root,
    run: runner.run,
    scriptsDir,
    resolveRuntime: () => ADAPTER,
    ...overrides,
  });
}

function byName(report: DoctorReport, name: string): CheckResult {
  const check = report.checks.find(c => c.name === name);
  if (!check) throw new Error(`no check named ${name} in ${renderText(report)}`);
  return check;
}

function fakeAmpCalls(): string[] {
  const log = join(fakeAmpDir, "calls.log");
  return existsSync(log) ? readFileSync(log, "utf8").split("\n").filter(Boolean) : [];
}

describe("a clean run", () => {
  test("every check passes except the informational ones, and the report is ok", async () => {
    const report = await doctor();
    expect(report.checks.map(c => c.name)).toEqual(CHECK_NAMES);
    expect(report.checks.map(c => c.level)).toEqual(CHECK_NAMES.map(() => "pass"));
    expect(report.ok).toBe(true);
    expect(byName(report, "amp-cli").found).toBe(`amp at ${join(FAKE_DIR, "amp")}`);
    expect(byName(report, "amp-project").found).toContain("https://ampcode.com/@nthplusio/skills");
    expect(byName(report, "push-access").found).toBe(`git push --dry-run from ${workspace} accepted`);
    expect(byName(report, "repo-url-env").found).toContain("matches --repo");
    expect(byName(report, "slack").found).toContain("andon.json");
    expect(byName(report, "plan").found).toBe(`${join(workspace, "plan.json")}: rootSlug hi, 1 task, repoUrl ${REPO}`);
  });

  test("the sign-in check reaches the fake amp on PATH with the cheapest listing call", async () => {
    await doctor();
    expect(fakeAmpCalls()).toEqual(["threads\tlist\t--json\t--limit\t1"]);
  });

  test("the repository URL is one argv element, never part of a shell string", async () => {
    const hostile = "https://github.com/nthplusio/skills; touch /tmp/pwned";
    runner.answer(`amp projects get ${hostile} --json`, { stdout: "{}" });
    await doctor({ repo: hostile });
    const projectCall = runner.calls.find(c => c.args[0] === "projects");
    expect(projectCall?.args).toEqual(["projects", "get", hostile, "--json"]);
    for (const call of runner.calls) expect(call.args.every(a => typeof a === "string")).toBe(true);
  });

  test("the push probe prefers the --workspace checkout and compares origins by repository key", async () => {
    await doctor();
    const push = runner.calls.find(c => c.cmd === "git" && c.args.includes("push"));
    expect(push?.args).toEqual(["-C", workspace, "push", "--dry-run", "origin", "HEAD:refs/heads/orchestrate-doctor-probe"]);
  });

  test("without --workspace there is no plan check", async () => {
    const report = await doctor({ workspace: undefined });
    expect(report.checks.map(c => c.name)).toEqual(CHECK_NAMES.filter(n => n !== "plan"));
  });
});

describe("each failing check", () => {
  test("dependencies: node_modules missing names the install command", async () => {
    rmSync(join(scriptsDir, "node_modules"), { recursive: true });
    const report = await doctor();
    expect(report.ok).toBe(false);
    expect(formatLine(byName(report, "dependencies"))).toBe(
      `fail dependencies: node_modules missing beside ${join(scriptsDir, "package.json")} — run \`bun install --frozen-lockfile\` in ${scriptsDir}`
    );
  });

  test("runtime: an unresolvable runtime is reported with the resolver's message", async () => {
    const report = await doctor({
      resolveRuntime: () => {
        throw new Error("Amp agent runtime not found; looked in /a, /b");
      },
    });
    expect(report.ok).toBe(false);
    const line = formatLine(byName(report, "runtime"));
    expect(line).toStartWith("fail runtime: Amp agent runtime not found; looked in /a, /b — ");
    expect(line).toContain("ORCHESTRATE_AMP_RUNTIME_DIR");
  });

  test("amp-cli: no amp on PATH fails, and the checks behind it are not attempted", async () => {
    const report = await doctor({ env: { ...env, PATH: binDir } });
    expect(report.ok).toBe(false);
    expect(formatLine(byName(report, "amp-cli"))).toStartWith("fail amp-cli: amp is not on PATH — install the Amp CLI");
    expect(byName(report, "amp-auth")).toMatchObject({ level: "fail", found: "not checked: amp CLI not found" });
    expect(byName(report, "amp-project")).toMatchObject({ level: "fail", found: "not checked: amp CLI not usable" });
    expect(runner.calls.filter(c => basename(c.cmd) === "amp")).toEqual([]);
  });

  test("amp-cli: ORCHESTRATE_AMP_BIN is honoured", async () => {
    const report = await doctor({ env: { ...env, ORCHESTRATE_AMP_BIN: join(FAKE_DIR, "amp"), PATH: binDir } });
    expect(byName(report, "amp-cli")).toMatchObject({
      level: "pass",
      found: `${join(FAKE_DIR, "amp")} at ${join(FAKE_DIR, "amp")} (ORCHESTRATE_AMP_BIN)`,
    });
    const missing = await doctor({ env: { ...env, ORCHESTRATE_AMP_BIN: join(root, "no-such-amp") } });
    expect(byName(missing, "amp-cli")).toMatchObject({ level: "fail" });
    expect(byName(missing, "amp-cli").found).toContain("ORCHESTRATE_AMP_BIN=");
  });

  test("amp-auth: the CLI's not-signed-in error becomes a fail line naming amp login", async () => {
    runner.answer("amp threads list --json --limit 1", { code: 1, stderr: `${NOT_SIGNED_IN}\n` });
    const report = await doctor();
    expect(report.ok).toBe(false);
    expect(formatLine(byName(report, "amp-auth"))).toBe(
      `fail amp-auth: amp threads list exit 1: ${NOT_SIGNED_IN} — run \`amp login\` on this machine, or set AMP_API_KEY (orbs set it)`
    );
    expect(byName(report, "amp-project")).toMatchObject({ level: "fail", found: "not checked: amp CLI not usable" });
  });

  test("amp-project: an unmapped repository fails with the create command", async () => {
    runner.answer(`amp projects get ${REPO} --json`, {
      code: 1,
      stderr: `Error: No accessible Amp project matches "${REPO}"\n`,
    });
    const report = await doctor();
    expect(report.ok).toBe(false);
    expect(formatLine(byName(report, "amp-project"))).toBe(
      `fail amp-project: amp projects get exit 1: Error: No accessible Amp project matches "${REPO}" — run \`amp projects create ${REPO} --personal\` (or map it in the workspace) so kickoff can open an orb on it`
    );
  });

  test("push-access: a refused dry run fails", async () => {
    runner.answer(`git -C ${workspace} push --dry-run origin HEAD:refs/heads/orchestrate-doctor-probe`, {
      code: 128,
      stderr: "remote: Permission to nthplusio/skills.git denied to amp[bot].\nfatal: unable to access: The requested URL returned error: 403\n",
    });
    const report = await doctor();
    expect(report.ok).toBe(false);
    const line = formatLine(byName(report, "push-access"));
    expect(line).toStartWith(`fail push-access: git push --dry-run from ${workspace} exit 128: fatal: unable to access`);
    expect(line).toContain("Amp GitHub App");
    expect(line).toContain("nthplusio/skills");
  });

  test("push-access: without a matching checkout, gh answers; false fails, true passes", async () => {
    runner.answer(`git -C ${workspace} remote get-url origin`, { stdout: "https://github.com/someone/else\n" });
    runner.answer(`git -C ${root} rev-parse --show-toplevel`, { code: 128, stderr: "fatal: not a git repository\n" });
    // A PATH without a system bin cannot run the fake (a bash script), so the
    // listing call is answered here instead of spawned.
    const ghEnv = { ...env, PATH: `${FAKE_DIR}:${binDir}` };
    runner.answer("amp threads list --json --limit 1", { stdout: "[]\n" });
    runner.answer("gh api repos/nthplusio/skills --jq .permissions.push", { stdout: "false\n" });
    const denied = await doctor({ env: ghEnv });
    expect(denied.ok).toBe(false);
    expect(formatLine(byName(denied, "push-access"))).toStartWith(
      "fail push-access: gh reports permissions.push=false on nthplusio/skills — grant"
    );
    runner.answer("gh api repos/nthplusio/skills --jq .permissions.push", { stdout: "true\n" });
    const granted = await doctor({ env: ghEnv });
    expect(byName(granted, "push-access")).toMatchObject({ level: "pass", found: "gh reports push permission on nthplusio/skills" });
    expect(runner.calls.find(c => c.cmd === "gh")?.args).toEqual(["api", "repos/nthplusio/skills", "--jq", ".permissions.push"]);
  });

  test("push-access: no checkout and no gh is a warn, not a fail", async () => {
    runner.answer(`git -C ${workspace} remote get-url origin`, { stdout: "https://github.com/someone/else\n" });
    runner.answer(`git -C ${root} rev-parse --show-toplevel`, { code: 128, stderr: "fatal: not a git repository\n" });
    runner.answer("amp threads list --json --limit 1", { stdout: "[]\n" });
    const report = await doctor({ env: { ...env, PATH: FAKE_DIR } });
    expect(byName(report, "push-access")).toMatchObject({ level: "warn" });
    expect(byName(report, "push-access").found).toContain("gh is not on PATH");
    expect(report.ok).toBe(true);
  });

  test("repo-url-env: unset warns, a different repository fails", async () => {
    const unset = await doctor({ env: { ...env, ORCHESTRATE_REPO_URL: "" } });
    expect(unset.ok).toBe(true);
    expect(formatLine(byName(unset, "repo-url-env"))).toBe(
      `warn repo-url-env: ORCHESTRATE_REPO_URL is unset; every cli.ts command that loads the workspace (run, tree, status, ...) logs one attention line and measurement clones stay refused — export ORCHESTRATE_REPO_URL=${REPO} in the shell that runs cli.ts`
    );
    const other = await doctor({ env: { ...env, ORCHESTRATE_REPO_URL: "https://github.com/nthplusio/other" } });
    expect(other.ok).toBe(false);
    expect(formatLine(byName(other, "repo-url-env"))).toBe(
      `fail repo-url-env: ORCHESTRATE_REPO_URL=https://github.com/nthplusio/other is not --repo ${REPO}; AgentManager.load refuses a plan.repoUrl that differs — export ORCHESTRATE_REPO_URL=${REPO}, or pass the --repo it names`
    );
  });

  test("slack: a token present is reported as information, still a pass", async () => {
    const report = await doctor({ env: { ...env, SLACK_BOT_TOKEN: "xoxb-1" } });
    expect(byName(report, "slack")).toMatchObject({ level: "pass", found: "SLACK_BOT_TOKEN set; Andon and the run thread go through Slack" });
  });

  test("plan: schema errors, a missing file, and a repoUrl that is not --repo each fail", async () => {
    writeFileSync(join(workspace, "plan.json"), JSON.stringify({ repoUrl: REPO, tasks: [] }));
    const invalid = await doctor();
    expect(invalid.ok).toBe(false);
    expect(formatLine(byName(invalid, "plan"))).toBe(
      `fail plan: ${join(workspace, "plan.json")}: tasks must be a non-empty array — fix the fields named, then rerun`
    );

    writeFileSync(join(workspace, "plan.json"), validPlan("https://github.com/nthplusio/other"));
    const mismatch = await doctor();
    expect(formatLine(byName(mismatch, "plan"))).toBe(
      `fail plan: ${join(workspace, "plan.json")}: rootSlug hi, 1 task, repoUrl https://github.com/nthplusio/other, which is not --repo ${REPO} — fix plan.repoUrl or pass the --repo it names`
    );

    rmSync(join(workspace, "plan.json"));
    const missing = await doctor();
    expect(formatLine(byName(missing, "plan"))).toStartWith(`fail plan: missing ${join(workspace, "plan.json")} — `);
  });

  test("plan: without schemas.ts beside the doctor (the pack layout) the check fails and says where to run", async () => {
    rmSync(join(scriptsDir, "schemas.ts"));
    const report = await doctor();
    expect(byName(report, "plan")).toMatchObject({ level: "fail" });
    expect(byName(report, "plan").fix).toContain("<skills>/orchestrate/scripts/tools/doctor.ts");
  });
});

describe("output forms", () => {
  test("the JSON form carries the same checks and round-trips", async () => {
    const report = await doctor();
    const parsed = JSON.parse(renderJson(report)) as DoctorReport;
    expect(parsed).toEqual(report);
    expect(renderText(parsed)).toBe(report.checks.map(formatLine).join("\n"));
    for (const line of renderText(parsed).split("\n")) expect(line).toMatch(/^(pass|warn|fail) [a-z-]+: /);
  });

  test("the CLI prints the lines, honours --json, and exits 1 on a failure", async () => {
    // From the pack layout `amp projects get` reaches the fake, which has no
    // answer for it, so the run fails on that check and the exit code is 1.
    const cliEnv = { ...env, ORCHESTRATE_REPO_URL: REPO };
    const json = Bun.spawnSync(["bun", DOCTOR, "--repo", REPO, "--json"], { env: cliEnv, cwd: root });
    expect(json.exitCode).toBe(1);
    const report = JSON.parse(json.stdout.toString()) as DoctorReport;
    expect(report.ok).toBe(false);
    expect(byName(report, "amp-cli")).toMatchObject({ level: "pass", found: `amp at ${join(FAKE_DIR, "amp")}` });
    expect(byName(report, "amp-auth")).toMatchObject({ level: "pass" });
    expect(byName(report, "amp-project").found).toContain("fake amp: unsupported command projects");
    expect(byName(report, "runtime")).toMatchObject({ level: "pass", found: `Amp agent runtime at ${ADAPTER}` });

    const text = Bun.spawnSync(["bun", DOCTOR, "--repo", REPO], { env: cliEnv, cwd: root });
    expect(text.exitCode).toBe(1);
    expect(text.stdout.toString().trim().split("\n")).toEqual(report.checks.map(formatLine));
  });

  test("parseArgs reads the three flags", () => {
    expect(parseArgs(["--repo", REPO, "--workspace", "/ws", "--json"])).toEqual({ repo: REPO, workspace: "/ws", json: true });
    expect(parseArgs([])).toEqual({ json: false });
  });
});

describe("helpers", () => {
  test("findOnPath finds the fake amp and nothing else", () => {
    expect(findOnPath("amp", { PATH: `${binDir}:${FAKE_DIR}` })).toBe(join(FAKE_DIR, "amp"));
    expect(findOnPath("amp", { PATH: binDir })).toBeNull();
    expect(findOnPath(join(FAKE_DIR, "amp"), { PATH: "" })).toBe(join(FAKE_DIR, "amp"));
    expect(findOnPath(join(root, "none"), { PATH: "" })).toBeNull();
  });

  test("githubOwnerRepo accepts github.com URLs in any spelling and rejects the rest", () => {
    expect(githubOwnerRepo("https://github.com/NthPlusIO/Skills.git")).toBe("nthplusio/skills");
    expect(githubOwnerRepo("git@github.com:nthplusio/skills.git")).toBe("nthplusio/skills");
    expect(githubOwnerRepo("https://gitlab.com/nthplusio/skills")).toBeNull();
    expect(githubOwnerRepo("not a url")).toBeNull();
  });
});
