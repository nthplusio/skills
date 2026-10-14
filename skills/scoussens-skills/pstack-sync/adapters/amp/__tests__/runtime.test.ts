/**
 * Drives the port's facade (`agent-runtime/scripts/core/runtime.ts`), the
 * SDK-shaped `Agent` surface upstream calls, over the real runtime and the
 * fake `amp` on PATH. The facade's type-only imports name the installed
 * layout; bun erases them, so the pack layout runs here.
 */
import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, utimesSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createAmpRuntime, type ThreadExport } from "../agent-runtime.ts";
import {
  __resetRuntimeForTests,
  buildAgentApi,
  hashedSiblingDirs,
  isAgentRuntimeError,
  loadSDK,
  PENDING_AGENT_ID,
  requireThreadId,
  resolveRuntimeDir,
} from "../agent-runtime/scripts/core/runtime.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const FAKE_DIR = join(HERE, "fake-amp");
const ID = "T-01a13830-78c4-723b-8624-f4b865ca42d8";
const REPO = "https://github.com/nthplusio/skills";

let dir: string;
let env: NodeJS.ProcessEnv;

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "os4-facade-"));
  chmodSync(join(FAKE_DIR, "amp"), 0o755);
  writeFileSync(join(dir, "spawn-id"), ID);
  env = {
    ...process.env,
    PATH: `${FAKE_DIR}:${process.env.PATH ?? ""}`,
    FAKE_AMP_DIR: dir,
    FAKE_AMP_LOG: join(dir, "calls.log"),
    ORCHESTRATE_AMP_BIN: "",
    ORCHESTRATE_AMP_POLL_MS: "5",
    ORCHESTRATE_AMP_ARCHIVED_CHECK_MS: "3600000",
    // The facade is under test, not the grace window; agent-runtime.test.ts covers that.
    ORCHESTRATE_AMP_HANDOFF_GRACE_MS: "0",
    // Never a real bridge: with the orchestrate-bridge plugin installed, the
    // orb that runs the tests has a live one under AMP_WORKING_DIRECTORY, and
    // a spawn through it creates a real thread.
    ORCHESTRATE_AMP_BRIDGE: "",
    AMP_WORKING_DIRECTORY: "",
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

function serve(n: number, exp: ThreadExport): void {
  writeFileSync(join(dir, `export-${ID}-${n}.json`), JSON.stringify(exp));
}

function idle(assistantText: string): ThreadExport {
  return {
    id: ID,
    messages: [
      { role: "user", content: [{ type: "text", text: "prompt" }], createdAt: "2026-10-14T02:14:29.000Z" },
      {
        role: "assistant",
        content: [{ type: "text", text: assistantText }],
        createdAt: "2026-10-14T02:14:44.000Z",
        state: { type: "complete", stopReason: "end_turn" },
      },
    ],
    meta: { lastKnownAgentState: { state: "idle" }, deleted: false },
  };
}

describe("agent ids", () => {
  test("resume refuses anything that is not a whole thread id", async () => {
    const Agent = buildAgentApi(createAmpRuntime({ env }));
    for (const bad of ["--help", "--last", PENDING_AGENT_ID, ""]) {
      const err = await Agent.resume(bad).catch(e => e);
      expect(isAgentRuntimeError(err)).toBe(true);
      expect(err.message).toContain(bad === PENDING_AGENT_ID ? "unexpanded placeholder" : JSON.stringify(bad));
    }
    expect(calls()).toEqual([]);
  });

  test("getRun refuses a bad agent id and a bad run id", async () => {
    const Agent = buildAgentApi(createAmpRuntime({ env }));
    const badAgent = await Agent.getRun("m0", { runtime: "cloud", agentId: "--last" }).catch(e => e);
    expect(isAgentRuntimeError(badAgent)).toBe(true);
    const badRun = await Agent.getRun("--last", { runtime: "cloud", agentId: ID }).catch(e => e);
    expect(isAgentRuntimeError(badRun)).toBe(true);
    expect(calls()).toEqual([]);
  });

  test("requireThreadId names what was rejected", () => {
    expect(requireThreadId(ID)).toBe(ID);
    expect(() => requireThreadId("--help", "--agent-id")).toThrow('--agent-id "--help" is not an Amp thread id');
  });
});

describe("Agent.create, send, wait", () => {
  test("the placeholder id becomes the real thread id at send, and wait returns the run's result", async () => {
    const Agent = buildAgentApi(createAmpRuntime({ env }));
    const agent = await Agent.create({
      name: "demo-root",
      cloud: { repos: [{ url: REPO, startingRef: "main" }], autoCreatePR: false },
      model: { id: "high" },
    });
    expect(agent.agentId).toBe(PENDING_AGENT_ID);
    const prompt = `You are the root planner.\n\nYour thread id is \`${agent.agentId}\`.`;
    const run = await agent.send(prompt);
    expect(agent.agentId).toBe(ID);
    expect(run.agentId).toBe(ID);
    expect(run.id).toBe("m0");
    expect(run.status).toBe("running");
    const spawn = calls()[0];
    expect(spawn[0]).toBe("-ox");
    expect(spawn[spawn.indexOf("--project") + 1]).toBe(REPO);
    expect(spawn[spawn.indexOf("--title") + 1]).toBe("demo-root");
    expect(spawn[spawn.indexOf("-m") + 1]).toBe("high");
    const stdin = readFileSync(join(dir, "spawn-stdin.txt"), "utf8");
    expect(stdin).toContain(prompt);
    expect(stdin).toContain("echo $AMP_THREAD_ID");

    serve(1, idle("## Status\nsuccess\n\n## Branch\n`orch/demo/root`\n\n## What I did\n- planned"));
    const result = await run.wait();
    expect(result.status).toBe("finished");
    expect(result.id).toBe("m0");
    expect(result.result?.startsWith("## Status\nsuccess")).toBe(true);
    expect(result.git?.branches).toEqual([{ branch: "orch/demo/root" }]);
    expect(result.durationMs).toBe(15_000);
    expect(result.error).toBeUndefined();
    expect(run.status).toBe("finished");
  });

  test("a prompt without the placeholder gets no thread-id note", async () => {
    const Agent = buildAgentApi(createAmpRuntime({ env }));
    const agent = await Agent.create({ cloud: { repos: [{ url: REPO }] } });
    await agent.send({ text: "plain" });
    expect(readFileSync(join(dir, "spawn-stdin.txt"), "utf8")).toBe("plain");
  });

  test("create without a repository is refused; the Amp runtime spawns on a project", async () => {
    const Agent = buildAgentApi(createAmpRuntime({ env }));
    await expect(Agent.create({ name: "x" })).rejects.toThrow("cloud.repos[0].url");
  });

  test("resume then send is a follow-up whose run id is the next message index", async () => {
    serve(1, idle("ROUNDTRIP-OK"));
    const Agent = buildAgentApi(createAmpRuntime({ env }));
    const agent = await Agent.resume(ID);
    expect(agent.agentId).toBe(ID);
    const run = await agent.send({ text: "and now?" });
    expect(run.id).toBe("m2");
    expect(calls().find(c => c[1] === "continue")).toEqual(["threads", "continue", ID, "-ox"]);
    expect(readFileSync(join(dir, "continue-stdin.txt"), "utf8")).toBe("and now?");
  });

  test("getRun, cancel, list, and listRuns map onto the runtime", async () => {
    serve(1, idle("done"));
    writeFileSync(
      join(dir, "list.json"),
      JSON.stringify([{ id: ID, title: "demo-root", updated: "2026-10-14T02:14:24.451Z", messageCount: 2 }])
    );
    const Agent = buildAgentApi(createAmpRuntime({ env }));
    const run = await Agent.getRun("m0", { runtime: "cloud", agentId: ID });
    expect(run.status).toBe("finished");
    expect(run.supports("wait")).toBe(true);
    expect(run.supports("conversation")).toBe(false);
    expect(run.unsupportedReason("conversation")).toContain("conversations");
    expect((await Agent.list({ runtime: "cloud", limit: 3 })).items).toEqual([
      { id: ID, agentId: ID, name: "demo-root", createdAt: "2026-10-14T02:14:24.451Z" },
    ]);
    expect((await Agent.listRuns(ID, { runtime: "cloud", limit: 1 })).items).toEqual([
      { id: "m0", status: "finished" },
    ]);
    await run.cancel();
    expect(run.status).toBe("cancelled");
    expect(existsSync(join(dir, `archived-${ID}`))).toBe(true);
  });

  test("a wait that hits the deadline surfaces as status error with the message", async () => {
    serve(1, {
      id: ID,
      messages: [{ role: "user", content: [{ type: "text", text: "go" }] }],
      meta: { lastKnownAgentState: { state: "working" } },
    });
    const Agent = buildAgentApi(createAmpRuntime({ env, waitTimeoutSec: 0.05 }));
    const run = await Agent.getRun("m0", { runtime: "cloud", agentId: ID });
    const result = await run.wait();
    expect(result.status).toBe("error");
    expect(result.error).toContain("ORCHESTRATE_WAIT_TIMEOUT_SEC");
  });
});

describe("loadSDK in the pack layout", () => {
  test("resolves adapters/amp beside the port and drives the fake amp from process.env", async () => {
    const saved = { ...process.env };
    __resetRuntimeForTests();
    try {
      Object.assign(process.env, env);
      expect(resolveRuntimeDir()).toBe(join(HERE, ".."));
      const Agent = await loadSDK();
      const agent = await Agent.create({ cloud: { repos: [{ url: REPO }] } });
      const run = await agent.send("hello");
      expect(agent.agentId).toBe(ID);
      serve(1, idle("hi"));
      expect((await run.wait()).result).toBe("hi");
    } finally {
      __resetRuntimeForTests();
      for (const key of Object.keys(process.env)) if (!(key in saved)) delete process.env[key];
      Object.assign(process.env, saved);
    }
  });
});

describe("hashedSiblingDirs for the orb skill cache layout", () => {
  test("lists pstack-sync@<hash> adapters newest first and skips hashes without the runtime", () => {
    const root = mkdtempSync(join(tmpdir(), "os4-cache-"));
    try {
      const make = (hash: string, withRuntime: boolean, ageSec: number) => {
        const adapter = join(root, `pstack-sync@${hash}`, "adapters", "amp");
        mkdirSync(adapter, { recursive: true });
        if (withRuntime) writeFileSync(join(adapter, "agent-runtime.ts"), "");
        const when = new Date(Date.now() - ageSec * 1000);
        utimesSync(adapter, when, when);
        return adapter;
      };
      const old = make("1111", true, 600);
      const fresh = make("2222", true, 0);
      make("3333", false, 0);
      mkdirSync(join(root, "orchestrate@abcd", "scripts", "core"), { recursive: true });
      expect(hashedSiblingDirs(root)).toEqual([fresh, old]);
      expect(hashedSiblingDirs(join(root, "missing"))).toEqual([]);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
