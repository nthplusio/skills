/**
 * The planner wake-up in the port's `cli/task.ts` (`nudgeIdlePlanner`, called
 * by `run` once every task is terminal): a follow-up goes to
 * `plan.selfAgentId` when that thread is idle, and nothing goes out when the
 * thread is working, in an unknown state, or unset. The port file imports
 * upstream modules the pack does not carry (the loop, the plan schema, the
 * CLI helpers), so the test assembles the port into a scratch `scripts/`
 * tree with stubs for those, the way probe-models.test.ts assembles the two
 * port directories, and drives the real facade over the fake `amp` on PATH.
 */
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, test } from "bun:test";
import { chmodSync, cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createAmpRuntime, type ThreadExport } from "../agent-runtime.ts";
import { buildAgentApi } from "../agent-runtime/scripts/core/runtime.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const ADAPTER = join(HERE, "..");
const FAKE_DIR = join(HERE, "fake-amp");
const ID = "T-01a13830-78c4-723b-8624-f4b865ca42d8";

type Task = { name: string; status: string };
type NudgeArgs = {
  agentApi: ReturnType<typeof buildAgentApi>;
  selfAgentId: string | null;
  tasks: Task[];
  workspace: string;
  rootSlug: string;
  rootMode: boolean;
  logAttention: (line: string) => void;
};
type TaskModule = {
  nudgeIdlePlanner(args: NudgeArgs): Promise<"sent" | "skipped">;
  allTasksTerminal(tasks: { status: string }[]): boolean;
  buildPlannerNudge(args: Omit<NudgeArgs, "agentApi" | "selfAgentId" | "logAttention">): string;
  registerTaskCommands(program: FakeCommand): void;
};
type StubManager = {
  tasks: Task[];
  selfAgentId: string | null;
  workspace: string;
  plan: { rootSlug: string };
  logAttention: (line: string) => void;
};
type UtilStub = { stubManagers: Map<string, StubManager> };

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

// Upstream modules task.ts imports that the pack does not carry. Only the
// names task.ts imports are needed; the `run` path uses loadOrBail,
// parsePositiveIntegerOrBail, resolveWorkspaceSlackChannelOrBail,
// runOrchestrateLoop, and errorMessage.
const STUBS: Record<string, string> = {
  "adapters/index.ts": "export function createSlackAdapter() { return null; }\n",
  "core/loop.ts": [
    "export const DEFAULT_MAX_RUNTIME_SEC = 3600;",
    "export async function runOrchestrateLoop() { return Number(process.env.STUB_LOOP_CODE ?? '0'); }",
    "",
  ].join("\n"),
  "schemas.ts": [
    "export function parsePlanTaskJson() { throw new Error('stub'); }",
    "export function parsePlanTaskValue() { throw new Error('stub'); }",
    "",
  ].join("\n"),
  "cli/util.ts": [
    "export const stubManagers = new Map();",
    "export function buildInlineTask() { throw new Error('stub'); }",
    "export function buildKickoffAgentName(goal) { return goal.toLowerCase().replace(/[^a-z0-9]+/g, '-'); }",
    "export function buildKickoffPrompt() { throw new Error('stub'); }",
    "export function collect(value, previous) { return [...(previous ?? []), value]; }",
    "export function collectCascadeVictims() { return []; }",
    "export function errorMessage(err) { return err instanceof Error ? err.message : String(err); }",
    "export async function loadOrBail(workspace) {",
    "  const mgr = stubManagers.get(workspace);",
    "  if (!mgr) throw new Error('no stub manager for ' + workspace);",
    "  return mgr;",
    "}",
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
let utilStub: UtilStub;
let dir: string;
let env: NodeJS.ProcessEnv;
let attention: string[];

beforeAll(async () => {
  root = mkdtempSync(join(tmpdir(), "os4-nudge-scripts-"));
  cpSync(join(ADAPTER, "agent-runtime", "scripts"), join(root, "scripts"), { recursive: true });
  cpSync(join(ADAPTER, "models", "scripts"), join(root, "scripts"), { recursive: true });
  for (const [rel, text] of Object.entries(STUBS)) {
    const path = join(root, "scripts", rel);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, text);
  }
  taskModule = (await import(pathToFileURL(join(root, "scripts", "cli", "task.ts")).href)) as TaskModule;
  utilStub = (await import(pathToFileURL(join(root, "scripts", "cli", "util.ts")).href)) as UtilStub;
});

afterAll(() => {
  rmSync(root, { recursive: true, force: true });
});

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "os4-nudge-fake-amp-"));
  chmodSync(join(FAKE_DIR, "amp"), 0o755);
  attention = [];
  env = {
    ...process.env,
    PATH: `${FAKE_DIR}:${process.env.PATH ?? ""}`,
    FAKE_AMP_DIR: dir,
    FAKE_AMP_LOG: join(dir, "calls.log"),
    ORCHESTRATE_AMP_BIN: "",
    ORCHESTRATE_AMP_POLL_MS: "5",
    ORCHESTRATE_AMP_ARCHIVED_CHECK_MS: "3600000",
  };
});

afterEach(() => {
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

function continued(): string | null {
  const path = join(dir, "continue-stdin.txt");
  return existsSync(path) ? readFileSync(path, "utf8") : null;
}

/** The planner thread as `amp threads export` shows it: the kickoff prompt and, when `replied`, the planner's reply. */
function plannerThread(state: string | undefined, replied = true): ThreadExport {
  const messages: ThreadExport["messages"] = [
    { role: "user", content: [{ type: "text", text: "You are the root planner for: demo" }], createdAt: "2026-10-14T02:14:29.000Z" },
  ];
  if (replied) {
    messages.push({
      role: "assistant",
      content: [{ type: "text", text: "Started the loop as a service; I will check back." }],
      createdAt: "2026-10-14T02:20:44.000Z",
      state: { type: "complete", stopReason: "end_turn" },
    });
  }
  return {
    id: ID,
    messages,
    meta: { lastKnownAgentState: state === undefined ? null : { state }, deleted: false },
  };
}

function serve(exp: ThreadExport): void {
  writeFileSync(join(dir, `export-${ID}-1.json`), JSON.stringify(exp));
}

const TERMINAL: Task[] = [
  { name: "task-a", status: "handed-off" },
  { name: "verify-a", status: "handed-off" },
  { name: "task-b", status: "error" },
];

function args(overrides: Partial<NudgeArgs> = {}): NudgeArgs {
  return {
    agentApi: buildAgentApi(createAmpRuntime({ env })),
    selfAgentId: ID,
    tasks: TERMINAL,
    workspace: ".orchestrate/demo",
    rootSlug: "demo",
    rootMode: true,
    logAttention: line => attention.push(line),
    ...overrides,
  };
}

describe("nudgeIdlePlanner", () => {
  test("sends one follow-up naming the terminal tasks when the planner thread is idle", async () => {
    serve(plannerThread("idle"));
    expect(await taskModule.nudgeIdlePlanner(args())).toBe("sent");
    const continueCalls = calls().filter(c => c[0] === "threads" && c[1] === "continue");
    expect(continueCalls).toEqual([["threads", "continue", ID, "-ox"]]);
    const text = continued() ?? "";
    expect(text).toContain("every task terminal");
    expect(text).toContain("- handed-off: task-a, verify-a");
    expect(text).toContain("- error: task-b");
    expect(text).toContain(".orchestrate/demo/handoffs/");
    expect(text).toContain("bun cli.ts run --root .orchestrate/demo");
    expect(attention).toHaveLength(1);
    expect(attention[0]).toContain(`planner nudge sent to ${ID} as run m2`);
  });

  test("sends nothing while the planner thread is working, which is a foreground loop", async () => {
    for (const state of ["working", "streaming", "running_tools"]) {
      serve(plannerThread(state));
      expect(await taskModule.nudgeIdlePlanner(args())).toBe("skipped");
      expect(continued()).toBeNull();
      expect(calls().some(c => c[1] === "continue")).toBe(false);
      rmSync(join(dir, "calls.log"), { force: true });
      rmSync(join(dir, `count-${ID}`), { force: true });
    }
    expect(attention).toHaveLength(3);
    for (const line of attention) {
      expect(line).toContain("planner nudge skipped");
      expect(line).toContain("working or its state is unknown");
    }
  });

  test("sends nothing when the state is unknown or the thread has not replied yet", async () => {
    for (const exp of [plannerThread(undefined), plannerThread("unexpected"), plannerThread("idle", false)]) {
      serve(exp);
      expect(await taskModule.nudgeIdlePlanner(args())).toBe("skipped");
      expect(continued()).toBeNull();
      rmSync(join(dir, "calls.log"), { force: true });
      rmSync(join(dir, `count-${ID}`), { force: true });
    }
    expect(attention).toHaveLength(3);
    expect(attention.every(line => line.includes("planner nudge skipped"))).toBe(true);
  });

  test("logs one line and sends nothing when the thread's state cannot be read", async () => {
    writeFileSync(join(dir, `export-${ID}-1.fail`), "");
    const api = buildAgentApi(createAmpRuntime({ env, maxConsecutiveFailures: 1 }));
    expect(await taskModule.nudgeIdlePlanner(args({ agentApi: api }))).toBe("skipped");
    expect(continued()).toBeNull();
    expect(attention).toHaveLength(1);
    expect(attention[0]).toContain("could not be read");
  });

  test("does nothing without plan.selfAgentId or while a task is still pending or running", async () => {
    serve(plannerThread("idle"));
    expect(await taskModule.nudgeIdlePlanner(args({ selfAgentId: null }))).toBe("skipped");
    for (const status of ["pending", "running"]) {
      const tasks = [...TERMINAL, { name: "task-c", status }];
      expect(taskModule.allTasksTerminal(tasks)).toBe(false);
      expect(await taskModule.nudgeIdlePlanner(args({ tasks }))).toBe("skipped");
    }
    expect(taskModule.allTasksTerminal(TERMINAL)).toBe(true);
    expect(calls()).toEqual([]);
    expect(attention).toEqual([]);
  });

  test("buildPlannerNudge groups tasks by status and omits --root for a subplanner", () => {
    const text = taskModule.buildPlannerNudge({
      tasks: [{ name: "b", status: "pruned" }, { name: "a", status: "cancelled" }],
      workspace: ".orchestrate/sub",
      rootSlug: "sub",
      rootMode: false,
    });
    expect(text).toContain("- cancelled: a\n- pruned: b");
    expect(text).toContain("bun cli.ts run .orchestrate/sub");
    expect(text).not.toContain("--root");
  });
});

describe("the run command", () => {
  test("nudges the idle planner after the loop returns with every task terminal", async () => {
    const saved = { ...process.env };
    const exit = process.exit;
    const workspace = join(dir, "workspace");
    mkdirSync(workspace);
    const mgr: StubManager = {
      tasks: TERMINAL,
      selfAgentId: ID,
      workspace,
      plan: { rootSlug: "demo" },
      logAttention: line => attention.push(line),
    };
    utilStub.stubManagers.set(workspace, mgr);
    serve(plannerThread("idle"));
    try {
      Object.assign(process.env, env, {
        ORCHESTRATE_AMP_RUNTIME_DIR: ADAPTER,
        STUB_LOOP_CODE: "1",
      });
      process.exit = ((code?: number) => {
        throw new ExitSignal(code);
      }) as typeof process.exit;
      const program = new FakeCommand();
      taskModule.registerTaskCommands(program);
      const run = program.actions.get("run");
      expect(run).toBeDefined();
      const signal = await run?.(workspace, { root: true, maxRuntimeSec: "540" }).catch(e => e);
      expect(signal).toBeInstanceOf(ExitSignal);
      expect((signal as ExitSignal).code).toBe(1);
      expect(continued()).toContain("- error: task-b");
      expect(attention).toHaveLength(1);
      expect(attention[0]).toContain("planner nudge sent");
    } finally {
      process.exit = exit;
      utilStub.stubManagers.delete(workspace);
      for (const key of Object.keys(process.env)) if (!(key in saved)) delete process.env[key];
      Object.assign(process.env, saved);
    }
  });
});
