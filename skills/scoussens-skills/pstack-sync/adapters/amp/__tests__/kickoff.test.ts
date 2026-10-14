/**
 * The port's `kickoff` command (`cli/task.ts`) over the real facade and the
 * fake `amp` on PATH: what the root prompt carries on Amp and how a second
 * kickoff for the same goal adopts the running root instead of spawning
 * another. The port file imports upstream modules the pack does not carry,
 * so the test assembles it into a scratch `scripts/` tree with stubs, the
 * way planner-nudge.test.ts does.
 */
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, test } from "bun:test";
import { chmodSync, cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import type { ThreadExport } from "../agent-runtime.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const ADAPTER = join(HERE, "..");
const FAKE_DIR = join(HERE, "fake-amp");
const ID = "T-01a13830-78c4-723b-8624-f4b865ca42d8";
const REPO = "https://github.com/nthplusio/skills";

type KickoffOpts = { repo?: string; ref: string; model: string; force?: boolean; slackChannel?: string; dispatcherName?: string };
type TaskModule = {
  CI_NOTE: string;
  withCiNote(prompt: string): string;
  registerTaskCommands(program: FakeCommand): void;
};
type CoreModule = { __resetRuntimeForTests(): void; goalLabel(rootSlug: string): string };

/** Just enough of commander for `registerTaskCommands` to hand over its actions. */
class FakeCommand {
  readonly actions = new Map<string, (...args: unknown[]) => Promise<void>>();
  private current = "";
  command(name: string): this {
    this.current = name;
    return this;
  }
  argument(): this {
    return this;
  }
  option(): this {
    return this;
  }
  requiredOption(): this {
    return this;
  }
  description(): this {
    return this;
  }
  action(fn: (...args: unknown[]) => Promise<void>): this {
    this.actions.set(this.current, fn);
    return this;
  }
}

class ExitSignal extends Error {
  constructor(readonly code: number | undefined) {
    super(`process.exit(${code})`);
  }
}

// Upstream modules task.ts imports that the pack does not carry; only the
// names the kickoff path touches do anything.
const STUBS: Record<string, string> = {
  "adapters/index.ts": "export function createSlackAdapter() { return null; }\n",
  "core/loop.ts": [
    "export const DEFAULT_MAX_RUNTIME_SEC = 3600;",
    "export async function runOrchestrateLoop() { return 0; }",
    "",
  ].join("\n"),
  "schemas.ts": [
    "export function parsePlanTaskJson() { throw new Error('stub'); }",
    "export function parsePlanTaskValue() { throw new Error('stub'); }",
    "",
  ].join("\n"),
  "cli/util.ts": [
    "export function buildInlineTask() { throw new Error('stub'); }",
    "export function buildKickoffAgentName(goal) { return goal.split('\\n')[0].trim().slice(0, 100); }",
    "export function buildKickoffPrompt({ goal, agentId }) { return `You are the root planner for: ${goal}\\n\\nYour thread id is ${agentId}.`; }",
    "export function collect(value, previous) { return [...(previous ?? []), value]; }",
    "export function collectCascadeVictims() { return []; }",
    "export function errorMessage(err) { return err instanceof Error ? err.message : String(err); }",
    "export async function loadOrBail() { throw new Error('stub'); }",
    "export function parsePositiveIntegerOrBail({ value }) { return Number(value); }",
    "export function parseRespawnSourceOrBail(source) { return source; }",
    "export function resolveKickoffRepoUrl(url) { return url; }",
    "export function resolveKickoffSlackChannelOrBail(channel) { return channel; }",
    "export function resolveWorkspaceSlackChannelOrBail() { return undefined; }",
    "export function transitivelyDependsOn() { return false; }",
    "",
  ].join("\n"),
};

let root: string;
let taskModule: TaskModule;
let coreModule: CoreModule;
let dir: string;
let savedEnv: NodeJS.ProcessEnv;
let printed: string[];
// Every `process.exit` call in order: kickoff's own catch block exits 1 after
// the fake exit of a success throws through it, so the first code is the verdict.
let exits: (number | undefined)[];
const realExit = process.exit;
const realLog = console.log;

beforeAll(async () => {
  root = mkdtempSync(join(tmpdir(), "os4-kickoff-scripts-"));
  cpSync(join(ADAPTER, "agent-runtime", "scripts"), join(root, "scripts"), { recursive: true });
  cpSync(join(ADAPTER, "models", "scripts"), join(root, "scripts"), { recursive: true });
  for (const [rel, text] of Object.entries(STUBS)) {
    const path = join(root, "scripts", rel);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, text);
  }
  taskModule = (await import(pathToFileURL(join(root, "scripts", "cli", "task.ts")).href)) as TaskModule;
  coreModule = (await import(pathToFileURL(join(root, "scripts", "core", "runtime.ts")).href)) as CoreModule;
});

afterAll(() => {
  rmSync(root, { recursive: true, force: true });
});

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "os4-kickoff-fake-amp-"));
  chmodSync(join(FAKE_DIR, "amp"), 0o755);
  writeFileSync(join(dir, "spawn-id"), ID);
  savedEnv = { ...process.env };
  Object.assign(process.env, {
    PATH: `${FAKE_DIR}:${process.env.PATH ?? ""}`,
    FAKE_AMP_DIR: dir,
    FAKE_AMP_LOG: join(dir, "calls.log"),
    ORCHESTRATE_AMP_BIN: "",
    ORCHESTRATE_AMP_POLL_MS: "5",
    ORCHESTRATE_AMP_ARCHIVED_CHECK_MS: "3600000",
    ORCHESTRATE_AMP_HANDOFF_GRACE_MS: "0",
    ORCHESTRATE_AMP_BRIDGE: "",
    AMP_WORKING_DIRECTORY: "",
    ORCHESTRATE_AMP_RUNTIME_DIR: ADAPTER,
  });
  coreModule.__resetRuntimeForTests();
  printed = [];
  exits = [];
  console.log = (...args: unknown[]) => {
    printed.push(args.map(String).join(" "));
  };
  process.exit = ((code?: number) => {
    exits.push(code);
    throw new ExitSignal(code);
  }) as typeof process.exit;
});

afterEach(() => {
  process.exit = realExit;
  console.log = realLog;
  for (const key of Object.keys(process.env)) if (!(key in savedEnv)) delete process.env[key];
  Object.assign(process.env, savedEnv);
  coreModule.__resetRuntimeForTests();
  rmSync(dir, { recursive: true, force: true });
});

function calls(): string[][] {
  const path = join(dir, "calls.log");
  if (!existsSync(path)) return [];
  return readFileSync(path, "utf8")
    .split("\n")
    .filter(Boolean)
    .map(line => line.split("\t"));
}

async function kickoff(goal: string, opts: Partial<KickoffOpts> = {}): Promise<{ code: number | undefined; out: Record<string, unknown> }> {
  printed = [];
  exits = [];
  const program = new FakeCommand();
  taskModule.registerTaskCommands(program);
  const action = program.actions.get("kickoff");
  if (!action) throw new Error("kickoff not registered");
  const signal = await action(goal, { repo: REPO, ref: "main", model: "high", ...opts }).catch(e => e);
  expect(signal).toBeInstanceOf(ExitSignal);
  const json = printed.find(line => line.startsWith("{"));
  return { code: exits[0], out: json ? (JSON.parse(json) as Record<string, unknown>) : {} };
}

function spawnPrompt(): string {
  return readFileSync(join(dir, "spawn-stdin.txt"), "utf8");
}

describe("the root prompt on Amp", () => {
  test("carries the run tag line and the CI opt-out after the kickoff prompt", async () => {
    const { code, out } = await kickoff("Add a sparkline to the dashboard");
    expect(code).toBe(0);
    expect(out.agentId).toBe(ID);
    expect(out.runId).toBe("m0");
    expect(out.runTag).toMatch(/^[a-z0-9]{6}$/);
    const prompt = spawnPrompt();
    expect(prompt).toContain("You are the root planner for: Add a sparkline to the dashboard");
    const tagLine = prompt.indexOf(`Run tag: this run's tag is \`${out.runTag}\``);
    const ciLine = prompt.indexOf(taskModule.CI_NOTE);
    expect(tagLine).toBeGreaterThan(0);
    expect(ciLine).toBeGreaterThan(tagLine);
    // The facade's thread-id note is the only thing after it.
    expect(prompt.slice(ciLine + taskModule.CI_NOTE.length)).toMatch(/^\n\nThread id: `\$AMP_THREAD_ID` in this prompt/);
    expect(taskModule.CI_NOTE).toContain("opts out of CI subscriptions");
    expect(taskModule.CI_NOTE).toContain("`.github/workflows/`");
    expect(taskModule.CI_NOTE).toContain("`No CI checks found`");
    expect(taskModule.withCiNote("p")).toBe(`p\n\n${taskModule.CI_NOTE}`);
    const spawn = calls().find(c => c[0] === "-ox");
    expect(spawn).toBeDefined();
    expect(spawn?.[spawn.indexOf("--title") + 1]).toBe(`${out.runTag} root`);
    const label = calls().find(c => c[0] === "threads" && c[1] === "label");
    expect(label).toEqual(["threads", "label", ID, "orchestrate", `run-${out.runTag}`, coreModule.goalLabel("Add a sparkline to the dashboard")]);
  });
});

/** The root thread as `amp threads search` and `amp threads export` show it. */
function rootThread(state: string, replied: boolean): ThreadExport {
  const messages: ThreadExport["messages"] = [
    { role: "user", content: [{ type: "text", text: "You are the root planner for: demo" }], createdAt: "2026-10-14T02:14:29.000Z" },
  ];
  if (replied) {
    messages.push({
      role: "assistant",
      content: [{ type: "text", text: "Opened the pull request; done." }],
      createdAt: "2026-10-14T02:40:44.000Z",
      state: { type: "complete", stopReason: "end_turn" },
    });
  }
  return { id: ID, title: "ab12cd root", messages, meta: { lastKnownAgentState: { state }, deleted: false } };
}

function listed(file: string, updatedAt: string, title = "ab12cd root"): void {
  const key = file === "list.json" ? "updated" : "updatedAt";
  writeFileSync(join(dir, file), JSON.stringify([{ id: ID, title, [key]: updatedAt, messageCount: 1 }]));
}

describe("kickoff adoption", () => {
  const GOAL = "Add a sparkline to the dashboard";
  const now = () => new Date().toISOString();

  test("a second kickoff for the same goal adopts the running root found by its goal label", async () => {
    listed("search-labels.json", now());
    writeFileSync(join(dir, `export-${ID}-1.json`), JSON.stringify(rootThread("working", false)));
    const { code, out } = await kickoff(GOAL);
    expect(code).toBe(0);
    expect(out).toEqual({ agentId: ID, runId: "m0", status: "running", url: `https://ampcode.com/threads/${ID}`, adopted: true });
    expect(printed[0]).toBe(`adopting ${ID}`);
    const search = calls().find(c => c[0] === "threads" && c[1] === "search");
    expect(search?.[2]).toBe(`label:orchestrate label:${coreModule.goalLabel(GOAL)} archived:false`);
    expect(coreModule.goalLabel(GOAL)).toMatch(/^goal-[0-9a-f]{12}$/);
    expect(coreModule.goalLabel("another goal")).not.toBe(coreModule.goalLabel(GOAL));
    expect(calls().some(c => c[0] === "-ox")).toBe(false);
    // Nothing fell through to the title listing.
    expect(calls().some(c => c[0] === "threads" && c[1] === "list")).toBe(false);
  });

  test("spawns a new root when the labelled one has finished, is older than the boot window, or --force is given", async () => {
    listed("search-labels.json", now());
    writeFileSync(join(dir, `export-${ID}-1.json`), JSON.stringify(rootThread("idle", true)));
    expect((await kickoff(GOAL)).out.adopted).toBeUndefined();
    expect(calls().filter(c => c[0] === "-ox")).toHaveLength(1);

    rmSync(join(dir, "calls.log"));
    rmSync(join(dir, `count-${ID}`));
    listed("search-labels.json", "2026-10-14T01:00:00.000Z");
    writeFileSync(join(dir, `export-${ID}-1.json`), JSON.stringify(rootThread("working", false)));
    expect((await kickoff(GOAL)).out.adopted).toBeUndefined();
    expect(calls().filter(c => c[0] === "-ox")).toHaveLength(1);
    // Too old to adopt: its export was never read.
    expect(calls().some(c => c[0] === "threads" && c[1] === "export")).toBe(false);

    rmSync(join(dir, "calls.log"));
    listed("search-labels.json", now());
    expect((await kickoff(GOAL, { force: true })).out.adopted).toBeUndefined();
    expect(calls()[0][0]).toBe("-ox");
    expect(calls().some(c => c[1] === "search" || c[1] === "list")).toBe(false);
  });

  test("falls back to upstream's exact title match for a root spawned before the goal label existed", async () => {
    listed("list.json", now(), `${GOAL}-root`);
    writeFileSync(join(dir, `export-${ID}-1.json`), JSON.stringify(rootThread("working", false)));
    const { out } = await kickoff(GOAL);
    expect(out.adopted).toBe(true);
    expect(out.agentId).toBe(ID);
    const kinds = calls().map(c => c.slice(0, 2).join(" "));
    expect(kinds.slice(0, 2)).toEqual(["threads search", "threads list"]);
    // A prefix of the slug is not a match.
    rmSync(join(dir, "calls.log"));
    rmSync(join(dir, `count-${ID}`));
    listed("list.json", now(), `${GOAL}-ui-root`);
    expect((await kickoff(GOAL)).out.adopted).toBeUndefined();
  });
});
