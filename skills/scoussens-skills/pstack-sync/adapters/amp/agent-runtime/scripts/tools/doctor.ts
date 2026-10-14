#!/usr/bin/env bun
// Amp port: preflight for the orchestrate loop. Runs the checks that cost the
// first real runs their loop starts, one line each, and exits 1 when any fails.
//
// Usage:
//   bun tools/doctor.ts [--repo <url>] [--workspace <dir>] [--json]
//
// Each line is `pass|warn|fail <name>: <what was found> — <fix>`. Every
// external command goes through a `CommandRunner` so tests can fake it, and
// user input only ever lands in an argv array, never in a shell string.
import { accessSync, constants, existsSync, readFileSync, statSync } from "node:fs";
import { spawn } from "node:child_process";
import { delimiter, dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { repoKey, resolveRuntimeDir } from "../core/runtime.ts";
// Type-only: names the installed layout, where `tsc --noEmit` runs; bun
// erases it, and the check below imports the file by path at run time.
import type * as Schemas from "../schemas.ts";

export type Level = "pass" | "warn" | "fail";

export interface CheckResult {
  name: string;
  level: Level;
  found: string;
  fix: string;
}

export interface DoctorReport {
  ok: boolean;
  checks: CheckResult[];
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
) => Promise<CommandResult>;

export interface DoctorOptions {
  repo?: string;
  workspace?: string;
  env?: NodeJS.ProcessEnv;
  cwd?: string;
  run?: CommandRunner;
  /** The `scripts/` directory holding package.json and schemas.ts; default: the doctor's parent. */
  scriptsDir?: string;
  resolveRuntime?: () => string;
}

interface AmpProject {
  repositoryURL?: string;
  url?: string;
}

const DEFAULT_TIMEOUT_MS = 60_000;
const PUSH_PROBE_REF = "refs/heads/orchestrate-doctor-probe";
// Mirrors `readPlanFile` in core/agent-manager.ts: the adapter's opt-in key is
// lifted out before the strict upstream schema sees the plan.
const PLAN_EXTRA_KEYS = ["measurementsEnabled"] as const;

/** Spawns `cmd` with an argv array; a missing binary is a result, not a throw. */
export const defaultRunner: CommandRunner = (cmd, args, opts = {}) =>
  new Promise(resolvePromise => {
    let child: ReturnType<typeof spawn>;
    try {
      child = spawn(cmd, args, {
        cwd: opts.cwd,
        env: opts.env ?? process.env,
        stdio: ["ignore", "pipe", "pipe"],
      });
    } catch (err) {
      resolvePromise({ code: null, stdout: "", stderr: errorMessage(err) });
      return;
    }
    let stdout = "";
    let stderr = "";
    let settled = false;
    const finish = (result: CommandResult) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolvePromise(result);
    };
    const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      finish({ code: null, stdout, stderr: `${stderr}\n${cmd} timed out after ${timeoutMs}ms`.trim() });
    }, timeoutMs);
    child.stdout?.setEncoding("utf8");
    child.stderr?.setEncoding("utf8");
    child.stdout?.on("data", chunk => {
      stdout += chunk;
    });
    child.stderr?.on("data", chunk => {
      stderr += chunk;
    });
    child.on("error", err => finish({ code: null, stdout, stderr: errorMessage(err) }));
    child.on("close", code => finish({ code, stdout, stderr }));
  });

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/** Last non-empty line of stderr, else stdout; what a person would read first. */
function lastLine(result: CommandResult): string {
  const text = (result.stderr.trim() || result.stdout.trim()).split("\n").filter(Boolean);
  return (text[text.length - 1] ?? "").trim();
}

function describeExit(result: CommandResult): string {
  return result.code === null ? "did not run" : `exit ${result.code}`;
}

/** The absolute path `name` resolves to on PATH, or null; a name with a slash is checked as given. */
export function findOnPath(name: string, env: NodeJS.ProcessEnv): string | null {
  const executable = (p: string): boolean => {
    try {
      accessSync(p, constants.X_OK);
      return statSync(p).isFile();
    } catch {
      return false;
    }
  };
  if (name.includes("/")) return executable(name) ? resolve(name) : null;
  for (const dir of (env.PATH ?? "").split(delimiter)) {
    if (!dir) continue;
    const candidate = join(dir, name);
    if (executable(candidate)) return candidate;
  }
  return null;
}

/** `owner/repo` for a github.com URL, or null for anything else. */
export function githubOwnerRepo(url: string): string | null {
  const key = repoKey(url);
  if (!key) return null;
  const [host, owner, repo, ...rest] = key.split("/");
  if (host !== "github.com" || !owner || !repo || rest.length > 0) return null;
  return `${owner}/${repo}`;
}

export function formatLine(check: CheckResult): string {
  const fix = check.fix ? ` — ${check.fix}` : "";
  return `${check.level} ${check.name}: ${check.found}${fix}`;
}

export function renderText(report: DoctorReport): string {
  return report.checks.map(formatLine).join("\n");
}

export function renderJson(report: DoctorReport): string {
  return JSON.stringify(report, null, 2);
}

export async function runDoctor(opts: DoctorOptions = {}): Promise<DoctorReport> {
  const env = opts.env ?? process.env;
  const cwd = opts.cwd ?? process.cwd();
  const run = opts.run ?? defaultRunner;
  const here = dirname(fileURLToPath(import.meta.url));
  const scriptsDir = opts.scriptsDir ?? dirname(here);
  const resolveRuntime = opts.resolveRuntime ?? resolveRuntimeDir;
  const repo = opts.repo?.trim() || undefined;
  const workspace = opts.workspace ? resolve(cwd, opts.workspace) : undefined;
  const checks: CheckResult[] = [];
  const add = (name: string, level: Level, found: string, fix = ""): void => {
    checks.push({ name, level, found, fix });
  };

  // 1. scripts dependencies
  {
    const pkg = join(scriptsDir, "package.json");
    const nodeModules = join(scriptsDir, "node_modules");
    const fix = `run \`bun install --frozen-lockfile\` in ${scriptsDir}`;
    if (!existsSync(pkg)) {
      add("dependencies", "fail", `no package.json in ${scriptsDir}`, `run the doctor from the installed skill's scripts/ directory, then ${fix}`);
    } else if (!existsSync(nodeModules) || !statSync(nodeModules).isDirectory()) {
      add("dependencies", "fail", `node_modules missing beside ${pkg}`, fix);
    } else {
      add("dependencies", "pass", `node_modules present beside ${pkg}`);
    }
  }

  // 2. Amp runtime
  {
    try {
      add("runtime", "pass", `Amp agent runtime at ${resolveRuntime()}`);
    } catch (err) {
      add(
        "runtime",
        "fail",
        errorMessage(err),
        "install pstack-sync beside this skill (python3 -I sync.py sync --set orchestrate) or set ORCHESTRATE_AMP_RUNTIME_DIR to a directory holding agent-runtime.ts and models.ts"
      );
    }
  }

  // 3. amp on PATH
  const binName = env.ORCHESTRATE_AMP_BIN || "amp";
  const ampPath = findOnPath(binName, env);
  if (ampPath) {
    add("amp-cli", "pass", `${binName} at ${ampPath}${env.ORCHESTRATE_AMP_BIN ? " (ORCHESTRATE_AMP_BIN)" : ""}`);
  } else {
    add(
      "amp-cli",
      "fail",
      env.ORCHESTRATE_AMP_BIN ? `ORCHESTRATE_AMP_BIN=${binName} is not an executable file or PATH entry` : "amp is not on PATH",
      "install the Amp CLI (curl -fsSL https://ampcode.com/install.sh | bash) or set ORCHESTRATE_AMP_BIN to the binary"
    );
  }

  // 4. signed in: the cheapest call that needs the API; the runtime's `list` uses it too.
  let signedIn = false;
  if (!ampPath) {
    add("amp-auth", "fail", "not checked: amp CLI not found", "fix amp-cli first");
  } else {
    const result = await run(ampPath, ["threads", "list", "--json", "--limit", "1"], { env });
    if (result.code === 0) {
      signedIn = true;
      add("amp-auth", "pass", "signed in (amp threads list answered)");
    } else {
      add(
        "amp-auth",
        "fail",
        `amp threads list ${describeExit(result)}: ${lastLine(result) || "no output"}`,
        "run `amp login` on this machine, or set AMP_API_KEY (orbs set it)"
      );
    }
  }

  // 5. repository is an accessible Amp project
  if (!repo) {
    add("amp-project", "warn", "no --repo given; not checked", "pass --repo <url> to check the Amp project mapping");
  } else if (!ampPath || !signedIn) {
    add("amp-project", "fail", "not checked: amp CLI not usable", "fix amp-cli and amp-auth first");
  } else {
    const result = await run(ampPath, ["projects", "get", repo, "--json"], { env });
    let project: AmpProject | null = null;
    if (result.code === 0) {
      try {
        project = JSON.parse(result.stdout) as AmpProject;
      } catch {
        project = null;
      }
    }
    if (project) {
      add("amp-project", "pass", `${repo} maps to Amp project ${project.url ?? project.repositoryURL ?? "(id only)"}`);
    } else {
      add(
        "amp-project",
        "fail",
        `amp projects get ${describeExit(result)}: ${lastLine(result) || "non-JSON output"}`,
        `run \`amp projects create ${repo} --personal\` (or map it in the workspace) so kickoff can open an orb on it`
      );
    }
  }

  // 6. the repository accepts a push
  if (!repo) {
    add("push-access", "warn", "no --repo given; not checked", "pass --repo <url> to check push access");
  } else {
    const checkout = await findCheckout(run, env, repo, [workspace, cwd]);
    const ownerRepo = githubOwnerRepo(repo);
    const grantFix = `grant the identity this machine pushes with (in an orb, the Amp GitHub App) write access to ${ownerRepo ?? repo}`;
    if (checkout) {
      const result = await run("git", ["-C", checkout, "push", "--dry-run", "origin", `HEAD:${PUSH_PROBE_REF}`], { env });
      if (result.code === 0) {
        add("push-access", "pass", `git push --dry-run from ${checkout} accepted`);
      } else {
        add("push-access", "fail", `git push --dry-run from ${checkout} ${describeExit(result)}: ${lastLine(result)}`, grantFix);
      }
    } else if (ownerRepo && findOnPath("gh", env)) {
      const result = await run("gh", ["api", `repos/${ownerRepo}`, "--jq", ".permissions.push"], { env });
      const answer = result.stdout.trim();
      if (result.code === 0 && answer === "true") {
        add("push-access", "pass", `gh reports push permission on ${ownerRepo}`);
      } else if (result.code === 0) {
        add("push-access", "fail", `gh reports permissions.push=${answer || "(empty)"} on ${ownerRepo}`, grantFix);
      } else {
        add("push-access", "fail", `gh api repos/${ownerRepo} ${describeExit(result)}: ${lastLine(result)}`, `check \`gh auth status\`; ${grantFix}`);
      }
    } else {
      add(
        "push-access",
        "warn",
        `no checkout of ${repo} at ${workspace ? `--workspace or ` : ""}cwd and ${ownerRepo ? "gh is not on PATH" : "the URL is not a github.com repository"}; not checked`,
        "run the doctor inside a clone of the repository, or install gh and sign in"
      );
    }
  }

  // 7. ORCHESTRATE_REPO_URL
  {
    const configured = env.ORCHESTRATE_REPO_URL?.trim() ?? "";
    if (!configured) {
      add(
        "repo-url-env",
        "warn",
        "ORCHESTRATE_REPO_URL is unset; every cli.ts command that loads the workspace (run, tree, status, ...) logs one attention line and measurement clones stay refused",
        `export ORCHESTRATE_REPO_URL=${repo ?? "<url>"} in the shell that runs cli.ts`
      );
    } else if (!repo) {
      add("repo-url-env", "pass", `ORCHESTRATE_REPO_URL=${configured} (no --repo to compare)`);
    } else if (repoKey(configured) !== null && repoKey(configured) === repoKey(repo)) {
      add("repo-url-env", "pass", `ORCHESTRATE_REPO_URL=${configured} matches --repo`);
    } else {
      add(
        "repo-url-env",
        "fail",
        `ORCHESTRATE_REPO_URL=${configured} is not --repo ${repo}; AgentManager.load refuses a plan.repoUrl that differs`,
        `export ORCHESTRATE_REPO_URL=${repo}, or pass the --repo it names`
      );
    }
  }

  // 8. Slack: information only
  if (env.SLACK_BOT_TOKEN) {
    add("slack", "pass", "SLACK_BOT_TOKEN set; Andon and the run thread go through Slack");
  } else {
    add("slack", "pass", "SLACK_BOT_TOKEN unset; Andon reads <workspace>/andon.json and nothing mirrors to Slack");
  }

  // 9. plan.json parses with the loop's schema
  if (workspace) {
    await checkPlan(add, scriptsDir, workspace, repo);
  }

  return { ok: checks.every(c => c.level !== "fail"), checks };
}

/** The first candidate inside a git checkout whose `origin` names `repo`. */
async function findCheckout(
  run: CommandRunner,
  env: NodeJS.ProcessEnv,
  repo: string,
  candidates: (string | undefined)[]
): Promise<string | null> {
  const wanted = repoKey(repo);
  if (!wanted) return null;
  const seen = new Set<string>();
  for (const dir of candidates) {
    if (!dir || seen.has(dir) || !existsSync(dir)) continue;
    seen.add(dir);
    const top = await run("git", ["-C", dir, "rev-parse", "--show-toplevel"], { env });
    if (top.code !== 0) continue;
    const origin = await run("git", ["-C", dir, "remote", "get-url", "origin"], { env });
    if (origin.code === 0 && repoKey(origin.stdout) === wanted) return top.stdout.trim() || dir;
  }
  return null;
}

async function checkPlan(
  add: (name: string, level: Level, found: string, fix?: string) => void,
  scriptsDir: string,
  workspace: string,
  repo: string | undefined
): Promise<void> {
  const planPath = join(workspace, "plan.json");
  if (!existsSync(planPath)) {
    add("plan", "fail", `missing ${planPath}`, "the root planner writes plan.json first; pass --workspace <dir> that holds one");
    return;
  }
  const schemasPath = join(scriptsDir, "schemas.ts");
  if (!existsSync(schemasPath)) {
    add("plan", "fail", `${schemasPath} not found, so plan.json cannot be checked with the loop's schema`, "run the doctor from the installed skill (<skills>/orchestrate/scripts/tools/doctor.ts)");
    return;
  }
  let text: string;
  try {
    text = liftPlanExtras(readFileSync(planPath, "utf8"));
  } catch (err) {
    add("plan", "fail", `${planPath}: ${errorMessage(err)}`, "write valid JSON");
    return;
  }
  try {
    const schemas = (await import(pathToFileURL(schemasPath).href)) as typeof Schemas;
    const plan = schemas.parsePlanJson(text, planPath);
    const tasks = plan.tasks ?? [];
    const summary = `${planPath}: rootSlug ${plan.rootSlug}, ${tasks.length} task${tasks.length === 1 ? "" : "s"}, repoUrl ${plan.repoUrl}`;
    if (repo && repoKey(plan.repoUrl) !== repoKey(repo)) {
      add("plan", "fail", `${summary}, which is not --repo ${repo}`, "fix plan.repoUrl or pass the --repo it names");
    } else {
      add("plan", "pass", summary);
    }
  } catch (err) {
    add("plan", "fail", errorMessage(err).split("\n").slice(0, 6).join(" | ").slice(0, 600), "fix the fields named, then rerun");
  }
}

/** The plan text without the adapter's extra keys, which the strict schema rejects. */
function liftPlanExtras(raw: string): string {
  const parsed: unknown = JSON.parse(raw);
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return raw;
  const record = { ...(parsed as Record<string, unknown>) };
  for (const key of PLAN_EXTRA_KEYS) delete record[key];
  return JSON.stringify(record);
}

function usage(): never {
  console.error("usage: bun tools/doctor.ts [--repo <url>] [--workspace <dir>] [--json]");
  process.exit(2);
}

export function parseArgs(argv: readonly string[]): { repo?: string; workspace?: string; json: boolean } {
  const out: { repo?: string; workspace?: string; json: boolean } = { json: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    switch (a) {
      case "--repo":
        out.repo = argv[++i];
        if (out.repo === undefined) usage();
        break;
      case "--workspace":
        out.workspace = argv[++i];
        if (out.workspace === undefined) usage();
        break;
      case "--json":
        out.json = true;
        break;
      case "-h":
      case "--help":
        usage();
        break;
      default:
        console.error(`unknown argument: ${a}`);
        usage();
    }
  }
  if (out.workspace !== undefined && !isAbsolute(out.workspace)) out.workspace = resolve(out.workspace);
  return out;
}

if (import.meta.main) {
  const args = parseArgs(process.argv.slice(2));
  const report = await runDoctor({ repo: args.repo, workspace: args.workspace });
  console.log(args.json ? renderJson(report) : renderText(report));
  process.exit(report.ok ? 0 : 1);
}
