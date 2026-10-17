import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { AgentRuntimeError, type StreamEvent } from "../../interface.ts";
import {
  bridgeCandidates,
  createAmpRuntime,
  DEFAULT_HANDOFF_GRACE_MS,
  describeRun,
  hasHandoffSection,
  isLoopbackUrl,
  isThreadId,
  labelArgs,
  parseBranchLine,
  readBridgeFile,
  readRuntimeOptionsFromEnv,
  type ThreadExport,
  titleFor,
  withStartingRef,
} from "../agent-runtime.ts";
import { AMP_BUILTIN_MODES, createAmpModelCatalog, pluginModesFrom } from "../models.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const FAKE_DIR = join(HERE, "fake-amp");
const ID = "T-01a13830-78c4-723b-8624-f4b865ca42d8";
const CHILD = "T-01a13b70-1111-7222-8333-444455556666";
const PARENT = "T-01a13b6a-aaaa-7bbb-8ccc-ddddeeeeffff";
const REPO = "https://github.com/nthplusio/skills";

let dir: string;
let env: NodeJS.ProcessEnv;
let servers: Server[];

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "os4-fake-amp-"));
  chmodSync(join(FAKE_DIR, "amp"), 0o755);
  writeFileSync(join(dir, "spawn-id"), ID);
  servers = [];
  // The fake is found through PATH, as a real `amp` would be; the runtime's
  // default binary name is what gets resolved. The orb that runs the tests
  // sets AMP_WORKING_DIRECTORY, and a bridge file there must not be found.
  env = {
    ...process.env,
    PATH: `${FAKE_DIR}:${process.env.PATH ?? ""}`,
    FAKE_AMP_DIR: dir,
    FAKE_AMP_LOG: join(dir, "calls.log"),
    ORCHESTRATE_AMP_BIN: "",
    ORCHESTRATE_AMP_POLL_MS: "5",
    ORCHESTRATE_AMP_ARCHIVED_CHECK_MS: "3600000",
    ORCHESTRATE_AMP_MAX_EXPORT_FAILURES: "5",
    ORCHESTRATE_AMP_BRIDGE: "",
    AMP_WORKING_DIRECTORY: "",
    // Off unless a test turns it on: most fixtures end on a plain reply.
    ORCHESTRATE_AMP_HANDOFF_GRACE_MS: "0",
  };
});

afterEach(async () => {
  for (const server of servers) await new Promise<void>(resolve => server.close(() => resolve()));
  rmSync(dir, { recursive: true, force: true });
});

interface BridgeRequest {
  method: string | undefined;
  url: string | undefined;
  authorization: string | undefined;
  body: Record<string, unknown>;
}

/**
 * A stand-in for the orchestrate-bridge plugin: a loopback `node:http`
 * server that records each request and answers 200 `{threadID, parent}` or
 * the status and body it was told to. Writes the bridge file the runtime
 * reads to `path` (default `<dir>/bridge.json`).
 */
async function startBridge(
  opts: { status?: number; reply?: Record<string, unknown>; path?: string } = {}
): Promise<{ requests: BridgeRequest[]; url: string; token: string; path: string }> {
  const requests: BridgeRequest[] = [];
  const server = createServer((req, res) => {
    let data = "";
    req.on("data", chunk => {
      data += chunk;
    });
    req.on("end", () => {
      requests.push({
        method: req.method,
        url: req.url,
        authorization: req.headers.authorization,
        body: data ? (JSON.parse(data) as Record<string, unknown>) : {},
      });
      const status = opts.status ?? 200;
      res.writeHead(status, { "content-type": "application/json" });
      res.end(
        JSON.stringify(
          status === 200 ? { threadID: CHILD, parent: PARENT } : (opts.reply ?? { error: "refused" })
        )
      );
    });
  });
  servers.push(server);
  await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;
  const url = `http://127.0.0.1:${port}/spawn`;
  const token = `tok-${port}-${Date.now()}`;
  const path = opts.path ?? join(dir, "bridge.json");
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(
    path,
    JSON.stringify({ url, token, thread: PARENT, startedAt: "2026-10-14T02:14:24.000Z" })
  );
  return { requests, url, token, path };
}

const SPAWN = {
  name: "demo/task-a",
  repoUrl: REPO,
  startingRef: "main",
  model: "inherit",
  prompt: "You are a worker.\n\nDo the thing.",
};

function calls(): string[][] {
  const path = join(dir, "calls.log");
  if (!existsSync(path)) return [];
  return readFileSync(path, "utf8")
    .split("\n")
    .filter(Boolean)
    .map(line => line.split("\t"));
}

function exportsOf(id: string): number {
  return calls().filter(c => c[0] === "threads" && c[1] === "export" && c[2] === id).length;
}

type Msg =
  | { user: string; at?: string }
  | { assistant: string; at?: string; stop?: string }
  | { tool: string; id?: string; at?: string }
  | { toolResult: true };

function thread(state: string, msgs: Msg[], meta: Record<string, unknown> = {}): ThreadExport {
  let t = Date.parse("2026-10-14T02:14:24.000Z");
  const messages = msgs.map(m => {
    t += 5_000;
    const createdAt = ("at" in m && m.at) || new Date(t).toISOString();
    if ("user" in m) return { role: "user", content: [{ type: "text", text: m.user }], createdAt };
    if ("assistant" in m) {
      return {
        role: "assistant",
        content: [{ type: "text", text: m.assistant }],
        createdAt,
        state: { type: m.stop ?? "complete", stopReason: "end_turn" },
      };
    }
    if ("tool" in m) {
      return {
        role: "assistant",
        content: [{ type: "tool_use", name: m.tool, id: m.id ?? "TU-1" }],
        createdAt,
        state: { type: "complete", stopReason: "tool_use" },
      };
    }
    return { role: "user", content: [{ type: "tool_result", toolUseID: "TU-1" }], createdAt };
  });
  return {
    id: ID,
    title: "fixture",
    messages,
    meta: { lastKnownAgentState: { state }, deleted: false, ...meta },
  };
}

function serve(id: string, n: number, exp: ThreadExport | "fail"): void {
  if (exp === "fail") writeFileSync(join(dir, `export-${id}-${n}.fail`), "");
  else writeFileSync(join(dir, `export-${id}-${n}.json`), JSON.stringify(exp));
}

function attentionSink(): { lines: string[]; onAttention: (line: string) => void } {
  const lines: string[] = [];
  return { lines, onAttention: line => lines.push(line) };
}

function renames(): string[][] {
  return calls().filter(c => c[0] === "threads" && c[1] === "rename");
}

const FINISHED = thread("idle", [
  { user: "do the task" },
  { tool: "shell_command" },
  { toolResult: true },
  {
    assistant:
      "## Status\nsuccess\n\n## Branch\n`orch/demo/task-a`\n\n## What I did\n- replied",
  },
]);

describe("spawn", () => {
  test("runs amp -ox against the repository with the prompt on stdin and returns the thread id", async () => {
    const rt = createAmpRuntime({ env });
    const result = await rt.spawn(SPAWN);
    expect(result).toEqual({
      agentId: ID,
      runId: "m0",
      via: "cli",
      note: expect.stringContaining("used the CLI: no bridge file at"),
    });
    const [call] = calls();
    expect(call[0]).toBe("-ox");
    expect(call).toContain("--project");
    expect(call[call.indexOf("--project") + 1]).toBe(REPO);
    expect(call[call.indexOf("--title") + 1]).toBe("demo/task-a");
    expect(call[call.indexOf("--visibility") + 1]).toBe("private");
    expect(call).toContain("--no-archive-after-execute");
    expect(call).not.toContain("-m");
    expect(call).not.toContain("-l");
    const stdin = readFileSync(join(dir, "spawn-stdin.txt"), "utf8");
    expect(stdin.startsWith("Start from git ref `main`")).toBe(true);
    expect(stdin.endsWith("You are a worker.\n\nDo the thing.")).toBe(true);
  });

  test("labels the thread after the spawn, with the default label first, and titles it from the run tag", async () => {
    const rt = createAmpRuntime({ env });
    await rt.spawn({ ...SPAWN, labels: ["run-ab12cd", "orchestrate"], runTag: "ab12cd" });
    const [spawn, label] = calls();
    expect(spawn[spawn.indexOf("--title") + 1]).toBe("ab12cd demo/task-a");
    expect(label).toEqual(["threads", "label", ID, "orchestrate", "run-ab12cd"]);
    expect(readFileSync(join(dir, `labels-${ID}`), "utf8")).toBe("orchestrate\nrun-ab12cd\n");
  });

  test("an already tagged title keeps one prefix, and an empty ORCHESTRATE_AMP_LABEL drops the default label", async () => {
    const rt = createAmpRuntime({ env: { ...env, ORCHESTRATE_AMP_LABEL: "" } });
    await rt.spawn({ ...SPAWN, labels: ["run-ab12cd"], runTag: "ab12cd", title: "ab12cd root" });
    const [spawn, label] = calls();
    expect(spawn[spawn.indexOf("--title") + 1]).toBe("ab12cd root");
    expect(label).toEqual(["threads", "label", ID, "run-ab12cd"]);
  });

  test("a custom title cannot remove the run identity, including when truncated", async () => {
    const rt = createAmpRuntime({ env });
    await rt.spawn({ ...SPAWN, runTag: "ab12cd", title: "Custom " + "x".repeat(120) });
    const [spawn] = calls();
    const title = spawn[spawn.indexOf("--title") + 1];
    expect(title).toBe("ab12cd Custom " + "x".repeat(86));
  });

  test("refuses a label outside the CLI's pattern before any command runs", async () => {
    const rt = createAmpRuntime({ env });
    for (const bad of ["--help", "run:ab12", "-x", "", "a b"]) {
      const err = await rt.spawn({ ...SPAWN, labels: [bad] }).catch(e => e);
      expect(err).toBeInstanceOf(AgentRuntimeError);
      expect(err.message).toContain(JSON.stringify(bad));
    }
    expect(calls()).toEqual([]);
    expect(labelArgs(["a", "a", "b-2"])).toEqual(["a", "b-2"]);
  });

  test("does not rename a CLI-spawned thread whose export already carries the title", async () => {
    const rt = createAmpRuntime({ env });
    await rt.spawn({ ...SPAWN, runTag: "ab12cd" });
    serve(ID, 1, { ...FINISHED, title: "ab12cd demo/task-a" });
    expect((await rt.wait({ agentId: ID, runId: "m0" })).status).toBe("finished");
    expect(renames()).toEqual([]);
  });

  test("titleFor keeps one line of at most 100 characters that cannot read as a flag", () => {
    expect(titleFor("  ab12cd   task-a \n")).toBe("ab12cd task-a");
    expect(titleFor("--last")).toBe("last");
    expect(titleFor("")).toBe("orchestrate");
    expect(titleFor("x".repeat(120))).toHaveLength(100);
  });

  test("passes a non-inherit model as the agent mode", async () => {
    const rt = createAmpRuntime({ env });
    await rt.spawn({ name: "n", repoUrl: REPO, startingRef: "main", model: "high", prompt: "p" });
    const [call] = calls();
    expect(call[call.indexOf("-m") + 1]).toBe("high");
  });

  test("throws a retryable AgentRuntimeError when the CLI prints no thread URL", async () => {
    writeFileSync(join(dir, "spawn-id"), "not-a-thread");
    const rt = createAmpRuntime({ env });
    const err = await rt
      .spawn({ name: "n", repoUrl: REPO, startingRef: "main", model: "inherit", prompt: "p" })
      .catch(e => e);
    expect(err).toBeInstanceOf(AgentRuntimeError);
    expect(err.isRetryable).toBe(true);
  });

  test("withStartingRef leaves the prompt alone when the ref is empty", () => {
    expect(withStartingRef("p", "  ")).toBe("p");
  });
});

describe("spawn through the bridge", () => {
  test("posts the spawn to the bridge named by ORCHESTRATE_AMP_BRIDGE and nests under its thread", async () => {
    const bridge = await startBridge();
    const rt = createAmpRuntime({ env: { ...env, ORCHESTRATE_AMP_BRIDGE: bridge.path } });
    const result = await rt.spawn({ ...SPAWN, labels: ["run-ab12cd"], title: "ab12cd task-a" });
    expect(result).toEqual({ agentId: CHILD, runId: "m0", via: "bridge" });
    expect(bridge.requests).toHaveLength(1);
    const [request] = bridge.requests;
    expect(request.method).toBe("POST");
    expect(request.url).toBe("/spawn");
    expect(request.authorization).toBe(`Bearer ${bridge.token}`);
    expect(request.body.name).toBe("demo/task-a");
    expect(request.body.project).toBe(REPO);
    expect(request.body.mode).toBe("high");
    expect(request.body.labels).toEqual(["orchestrate", "run-ab12cd"]);
    expect(request.body.parent).toBeUndefined();
    const prompt = request.body.prompt as string;
    expect(prompt.startsWith("Start from git ref `main`")).toBe(true);
    expect(prompt.endsWith(SPAWN.prompt)).toBe(true);
    // No CLI call at all: the bridge created, labelled, and prompted the thread.
    expect(calls()).toEqual([]);
  });

  test("sends nodeType to the bridge and its node-<type> label on both paths", async () => {
    const bridge = await startBridge();
    const rt = createAmpRuntime({ env: { ...env, ORCHESTRATE_AMP_BRIDGE: bridge.path } });
    await rt.spawn({ ...SPAWN, labels: ["run-ab12cd"], nodeType: "planner" });
    expect(bridge.requests[0].body.nodeType).toBe("planner");
    expect(bridge.requests[0].body.labels).toEqual(["orchestrate", "node-planner", "run-ab12cd"]);
    await rt.spawn({ ...SPAWN, labels: ["run-ab12cd"] });
    expect(bridge.requests[1].body).not.toHaveProperty("nodeType");
    expect(bridge.requests[1].body.labels).toEqual(["orchestrate", "run-ab12cd"]);
    const cli = createAmpRuntime({ env });
    await cli.spawn({ ...SPAWN, labels: ["run-ab12cd"], nodeType: "verifier" });
    const label = calls().find(c => c[0] === "threads" && c[1] === "label");
    expect(label).toEqual(["threads", "label", ID, "orchestrate", "node-verifier", "run-ab12cd"]);
  });

  test("maps a non-inherit model to the bridge's mode", async () => {
    const bridge = await startBridge();
    const rt = createAmpRuntime({ env: { ...env, ORCHESTRATE_AMP_BRIDGE: bridge.path } });
    await rt.spawn({ ...SPAWN, model: "low" });
    expect(bridge.requests[0].body.mode).toBe("low");
  });

  test("finds the file under the working directory, then under AMP_WORKING_DIRECTORY", async () => {
    const cwd = join(dir, "cwd");
    const bridge = await startBridge({ path: join(cwd, ".orchestrate", "bridge.json") });
    const fromCwd = createAmpRuntime({ env: { ...env, ORCHESTRATE_AMP_BRIDGE: undefined }, cwd });
    expect((await fromCwd.spawn(SPAWN)).via).toBe("bridge");
    const amp = join(dir, "amp-wd");
    await startBridge({ path: join(amp, ".orchestrate", "bridge.json") });
    const fromAmp = createAmpRuntime({ env: { ...env, ORCHESTRATE_AMP_BRIDGE: undefined, AMP_WORKING_DIRECTORY: amp }, cwd: dir });
    expect((await fromAmp.spawn(SPAWN)).via).toBe("bridge");
    expect(bridge.requests).toHaveLength(1);
    expect(bridgeCandidates({ ORCHESTRATE_AMP_BRIDGE: "/x/b.json", AMP_WORKING_DIRECTORY: amp }, cwd)).toEqual([
      "/x/b.json",
    ]);
    expect(bridgeCandidates({ AMP_WORKING_DIRECTORY: amp }, cwd)).toEqual([
      join(cwd, ".orchestrate", "bridge.json"),
      join(amp, ".orchestrate", "bridge.json"),
    ]);
    expect(bridgeCandidates({}, cwd)).toEqual([join(cwd, ".orchestrate", "bridge.json")]);
  });

  test("explicitly disabling discovery cannot contact a live bridge in the current directory", async () => {
    const bridge = await startBridge({ path: join(dir, ".orchestrate", "bridge.json") });
    const rt = createAmpRuntime({ env, cwd: dir });
    expect((await rt.spawn(SPAWN)).agentId).toBe(ID);
    expect(bridge.requests).toHaveLength(0);
    expect(bridgeCandidates(env, dir)).toEqual([]);
  });

  test("falls back to the CLI with a note naming why when the bridge refuses", async () => {
    const bridge = await startBridge({ status: 401, reply: { error: "bad token" } });
    const rt = createAmpRuntime({ env: { ...env, ORCHESTRATE_AMP_BRIDGE: bridge.path } });
    const result = await rt.spawn({ ...SPAWN, labels: ["run-ab12cd"] });
    expect(result.agentId).toBe(ID);
    expect(result.via).toBe("cli");
    expect(result.note).toContain(`bridge at ${bridge.path} refused the spawn`);
    expect(result.note).toContain("401: bad token");
    expect(bridge.requests).toHaveLength(1);
    const [spawn, label] = calls();
    expect(spawn[0]).toBe("-ox");
    expect(label).toEqual(["threads", "label", ID, "orchestrate", "run-ab12cd"]);
  });

  test("falls back to the CLI when the file is missing, malformed, or not loopback, without a request", async () => {
    const cases: [string, string][] = [
      [join(dir, "nowhere.json"), `no bridge file at ${join(dir, "nowhere.json")}`],
      [join(dir, "junk.json"), "is not JSON"],
      [join(dir, "no-token.json"), "has no url and token"],
      [join(dir, "remote.json"), "is not a loopback address"],
    ];
    writeFileSync(join(dir, "junk.json"), "{");
    writeFileSync(join(dir, "no-token.json"), JSON.stringify({ url: "http://127.0.0.1:1/spawn" }));
    writeFileSync(
      join(dir, "remote.json"),
      JSON.stringify({ url: "http://bridge.example.com/spawn", token: "t" })
    );
    for (const [path, reason] of cases) {
      const lookup = readBridgeFile({ ORCHESTRATE_AMP_BRIDGE: path }, dir);
      expect(lookup.kind).toBe("missing");
      expect(lookup.kind === "missing" && lookup.reason).toContain(reason);
      const rt = createAmpRuntime({ env: { ...env, ORCHESTRATE_AMP_BRIDGE: path } });
      const result = await rt.spawn(SPAWN);
      expect(result.via).toBe("cli");
      expect(result.note).toContain(reason);
    }
    expect(isLoopbackUrl("http://localhost:8/x")).toBe(true);
    expect(isLoopbackUrl("http://[::1]:8/x")).toBe(true);
    expect(isLoopbackUrl("http://127.0.0.1.example.com/x")).toBe(false);
    expect(isLoopbackUrl("file:///etc/passwd")).toBe(false);
  });

  test("renames the thread on the first poll that sees a message, once", async () => {
    const bridge = await startBridge();
    const rt = createAmpRuntime({ env: { ...env, ORCHESTRATE_AMP_BRIDGE: bridge.path } });
    const { agentId } = await rt.spawn({ ...SPAWN, title: "ab12cd task-a" });
    // The first export is the empty thread (the bridge's append has not
    // landed): no rename, which the fake would refuse. The second has the
    // prompt; the third is the finished run.
    serve(agentId, 1, thread("working", []));
    serve(agentId, 2, thread("working", [{ user: "do the task" }]));
    serve(agentId, 3, FINISHED);
    const result = await rt.wait({ agentId, runId: "m0" });
    expect(result.status).toBe("finished");
    expect(renames()).toEqual([["threads", "rename", agentId, "ab12cd task-a"]]);
    expect(readFileSync(join(dir, `title-${agentId}`), "utf8")).toBe("ab12cd task-a");
    const order = calls().map(c => c.slice(0, 2).join(" "));
    expect(order.indexOf("threads rename")).toBe(2);
  });

  test("a rename that fails is one attention line and never the run's status", async () => {
    const bridge = await startBridge();
    const sink = attentionSink();
    const rt = createAmpRuntime({
      env: { ...env, ORCHESTRATE_AMP_BRIDGE: bridge.path },
      onAttention: sink.onAttention,
    });
    const { agentId } = await rt.spawn({ ...SPAWN, title: "ab12cd task-a" });
    writeFileSync(join(dir, "rename-fail"), "");
    serve(agentId, 1, thread("working", [{ user: "do the task" }]));
    serve(agentId, 2, thread("streaming", [{ user: "do the task" }, { tool: "shell_command" }]));
    serve(agentId, 3, FINISHED);
    const events: StreamEvent[] = [];
    for await (const event of rt.stream({ agentId, runId: "m0" })) events.push(event);
    expect(events.at(-1)).toEqual({ type: "status", status: "finished" });
    expect(renames()).toHaveLength(1);
    expect(sink.lines).toHaveLength(1);
    expect(sink.lines[0]).toContain(`${agentId}: rename to "ab12cd task-a" failed`);
    expect(sink.lines[0]).toContain("rename refused");
  });

  test("rename refuses an empty thread the way the real CLI does", async () => {
    const rt = createAmpRuntime({ env });
    const err = await rt.rename(ID, "ab12cd task-a").catch(e => e);
    expect(err).toBeInstanceOf(AgentRuntimeError);
    expect(err.message).toContain("Cannot rename an empty thread.");
    serve(ID, 1, thread("working", [{ user: "go" }]));
    await rt.getRun(ID, "m0");
    await rt.rename(ID, "ab12cd task-a");
    expect(readFileSync(join(dir, `title-${ID}`), "utf8")).toBe("ab12cd task-a");
  });

  test("label adds labels to an existing thread and refuses bad ones", async () => {
    const rt = createAmpRuntime({ env });
    await rt.label(ID, ["orchestrate", "run-ab12cd"]);
    expect(readFileSync(join(dir, `labels-${ID}`), "utf8")).toBe("orchestrate\nrun-ab12cd\n");
    await expect(rt.label(ID, ["--last"])).rejects.toBeInstanceOf(AgentRuntimeError);
    await expect(rt.label("--last", ["a"])).rejects.toBeInstanceOf(AgentRuntimeError);
    expect(calls()).toHaveLength(1);
  });
});

describe("wait", () => {
  test("returns the final assistant text, its branch, and the duration once the thread is idle", async () => {
    serve(ID, 1, thread("working", [{ user: "do the task" }]));
    serve(ID, 2, thread("streaming", [{ user: "do the task" }, { tool: "shell_command" }]));
    serve(ID, 3, FINISHED);
    const rt = createAmpRuntime({ env });
    const result = await rt.wait({ agentId: ID, runId: "m0" });
    expect(result.status).toBe("finished");
    expect(result.finalText.startsWith("## Status\nsuccess")).toBe(true);
    expect(result.branches).toEqual(["orch/demo/task-a"]);
    expect(result.durationMs).toBe(15_000);
    expect(exportsOf(ID)).toBe(3);
  });

  test("tolerates exports that fail and then recover", async () => {
    serve(ID, 1, thread("working", [{ user: "do the task" }]));
    serve(ID, 2, "fail");
    serve(ID, 3, "fail");
    serve(ID, 4, FINISHED);
    const rt = createAmpRuntime({ env });
    const result = await rt.wait({ agentId: ID, runId: "m0" });
    expect(result.status).toBe("finished");
    expect(exportsOf(ID)).toBe(4);
  });

  test("gives up after the configured number of consecutive failures", async () => {
    for (let n = 1; n <= 6; n++) serve(ID, n, "fail");
    const rt = createAmpRuntime({ env, maxConsecutiveFailures: 3 });
    const err = await rt.wait({ agentId: ID, runId: "m0" }).catch(e => e);
    expect(err).toBeInstanceOf(AgentRuntimeError);
    expect(err.message).toContain("3 times in a row");
    expect(exportsOf(ID)).toBe(3);
  });

  test("reports a thread another process archived as cancelled", async () => {
    serve(ID, 1, thread("working", [{ user: "do the task" }]));
    writeFileSync(
      join(dir, `search-${ID}.json`),
      JSON.stringify([{ id: ID, title: "fixture", updatedAt: "2026-10-14T02:16:45.852Z" }])
    );
    const rt = createAmpRuntime({ env, archivedCheckMs: 1 });
    const result = await rt.wait({ agentId: ID, runId: "m0" });
    expect(result.status).toBe("cancelled");
    expect(calls().some(c => c[0] === "threads" && c[1] === "search")).toBe(true);
  });

  test("scopes a follow-up run to messages after its start", async () => {
    const withFollowUp = thread("idle", [
      { user: "do the task" },
      { assistant: "ROUNDTRIP-OK" },
      { user: "and now?" },
      { assistant: "FOLLOWUP-OK" },
    ]);
    serve(ID, 1, withFollowUp);
    const rt = createAmpRuntime({ env });
    expect((await rt.wait({ agentId: ID, runId: "m2" })).finalText).toBe("FOLLOWUP-OK");
    const stillRunning = thread("working", [
      { user: "do the task" },
      { assistant: "ROUNDTRIP-OK" },
      { user: "and now?" },
    ]);
    expect(describeRun(stillRunning, "m2").status).toBe("running");
    expect(describeRun(stillRunning, "m0").status).toBe("running");
  });
});

describe("deadline", () => {
  test("wait ends with status error and a message once ORCHESTRATE_WAIT_TIMEOUT_SEC passes without a terminal state", async () => {
    serve(ID, 1, thread("working", [{ user: "do the task" }, { assistant: "Still going" }]));
    const rt = createAmpRuntime({ env, waitTimeoutSec: 0.05 });
    const result = await rt.wait({ agentId: ID, runId: "m0" });
    expect(result.status).toBe("error");
    expect(result.error).toContain("ORCHESTRATE_WAIT_TIMEOUT_SEC=0.05s");
    expect(result.error).toContain(`https://ampcode.com/threads/${ID}`);
    expect(result.error).toContain("last agent state: working");
    expect(result.finalText).toBe("Still going");
    expect(exportsOf(ID)).toBeGreaterThan(1);
  });

  test("the deadline comes from the environment in seconds", async () => {
    serve(ID, 1, thread("working", [{ user: "go" }]));
    const rt = createAmpRuntime({ env: { ...env, ORCHESTRATE_WAIT_TIMEOUT_SEC: "1" } });
    const started = Date.now();
    const result = await rt.wait({ agentId: ID, runId: "m0" });
    expect(result.status).toBe("error");
    expect(Date.now() - started).toBeGreaterThanOrEqual(900);
  });

  test("stream ends with an error status carrying the same message", async () => {
    serve(ID, 1, thread("working", [{ user: "go" }, { tool: "shell_command" }]));
    const rt = createAmpRuntime({ env, waitTimeoutSec: 0.05 });
    const events: StreamEvent[] = [];
    for await (const event of rt.stream({ agentId: ID, runId: "m0" })) events.push(event);
    const last = events.at(-1);
    expect(last?.type).toBe("status");
    expect(last?.type === "status" && last.status).toBe("error");
    expect(last?.type === "status" && last.error).toContain("gave up waiting");
    expect(events.filter(e => e.type === "tool_call")).toHaveLength(1);
  });

  test("a run that finishes before the deadline is unaffected", async () => {
    serve(ID, 1, FINISHED);
    const rt = createAmpRuntime({ env, waitTimeoutSec: 0.05 });
    expect((await rt.wait({ agentId: ID, runId: "m0" })).status).toBe("finished");
  });
});

describe("handoff grace", () => {
  const PROGRESS = "Tests pass; pushing the branch next and will hand off after.";
  const midTurn: Msg[] = [{ user: "do the task" }, { assistant: PROGRESS }, { tool: "shell_command", id: "TU-2" }];
  const handedOff: Msg[] = [...midTurn, { toolResult: true }, { assistant: "## Status\nsuccess\n\n## Branch\n`orch/demo/task-a`" }];

  test("holds a finished run without a handoff section until a later turn produces one", async () => {
    serve(ID, 1, thread("working", [{ user: "do the task" }]));
    serve(ID, 2, thread("idle", [{ user: "do the task" }, { assistant: PROGRESS }]));
    serve(ID, 3, thread("running_tools", midTurn));
    serve(ID, 4, thread("idle", handedOff));
    const sink = attentionSink();
    const rt = createAmpRuntime({ env, handoffGraceMs: 2_000, onAttention: sink.onAttention });
    const result = await rt.wait({ agentId: ID, runId: "m0" });
    expect(result.status).toBe("finished");
    expect(result.finalText.startsWith("## Status\nsuccess")).toBe(true);
    expect(result.branches).toEqual(["orch/demo/task-a"]);
    expect(exportsOf(ID)).toBe(4);
    expect(sink.lines).toHaveLength(1);
    expect(sink.lines[0]).toContain(`${ID} m0: turn ended idle without a \`## Status\``);
    expect(sink.lines[0]).toContain("polling up to 2s more");
  });

  test("returns finished with the last text once the grace expires, and says so", async () => {
    serve(ID, 1, thread("idle", [{ user: "do the task" }, { assistant: PROGRESS }]));
    const sink = attentionSink();
    const rt = createAmpRuntime({ env, handoffGraceMs: 60, onAttention: sink.onAttention });
    const started = Date.now();
    const result = await rt.wait({ agentId: ID, runId: "m0" });
    expect(Date.now() - started).toBeGreaterThanOrEqual(55);
    expect(result.status).toBe("finished");
    expect(result.finalText).toBe(PROGRESS);
    expect(exportsOf(ID)).toBeGreaterThan(1);
    expect(sink.lines).toHaveLength(2);
    expect(sink.lines[1]).toContain(`${ID} m0: no handoff section after 0s of grace`);
  });

  test("stream keeps yielding through the window and ends with the handoff turn's status", async () => {
    serve(ID, 1, thread("idle", [{ user: "do the task" }, { assistant: PROGRESS }]));
    serve(ID, 2, thread("working", midTurn));
    serve(ID, 3, thread("idle", handedOff));
    const rt = createAmpRuntime({ env, handoffGraceMs: 2_000, onAttention: () => {} });
    const events: StreamEvent[] = [];
    for await (const event of rt.stream({ agentId: ID, runId: "m0" })) events.push(event);
    const text = events
      .filter((e): e is Extract<StreamEvent, { type: "assistant" }> => e.type === "assistant")
      .map(e => e.text)
      .join("");
    expect(text).toBe(`${PROGRESS}## Status\nsuccess\n\n## Branch\n\`orch/demo/task-a\``);
    expect(events.filter(e => e.type === "tool_call")).toHaveLength(1);
    expect(events.at(-1)).toEqual({ type: "status", status: "finished" });
    expect(exportsOf(ID)).toBe(3);
  });

  test("a verifier's ## Verification section is a handoff too", async () => {
    serve(ID, 1, thread("idle", [{ user: "verify" }, { assistant: "## Verification\nverified\n\n## Notes\n- ok" }]));
    const sink = attentionSink();
    const rt = createAmpRuntime({ env, handoffGraceMs: 60_000, onAttention: sink.onAttention });
    expect((await rt.wait({ agentId: ID, runId: "m0" })).status).toBe("finished");
    expect(exportsOf(ID)).toBe(1);
    expect(sink.lines).toEqual([]);
    expect(hasHandoffSection("## Status\nsuccess")).toBe(true);
    expect(hasHandoffSection("##  Verification  \nverified")).toBe(true);
    expect(hasHandoffSection("Status: success\n### Status\ndone")).toBe(false);
    expect(hasHandoffSection("")).toBe(false);
  });

  test("no grace for an archived, cancelled, or errored run, or when the window is 0", async () => {
    const sink = attentionSink();
    const cases: [string, ThreadExport, string][] = [
      ["archived", thread("idle", [{ user: "x" }, { assistant: PROGRESS }], { archived: true }), "finished"],
      ["cancelled", thread("idle", [{ user: "x" }, { assistant: PROGRESS, stop: "cancelled" }]), "cancelled"],
      ["errored", thread("idle", [{ user: "x" }, { assistant: PROGRESS, stop: "error" }]), "error"],
    ];
    for (const [label, exp, status] of cases) {
      rmSync(join(dir, `count-${ID}`), { force: true });
      serve(ID, 1, exp);
      const rt = createAmpRuntime({ env, handoffGraceMs: 60_000, onAttention: sink.onAttention });
      expect([label, (await rt.wait({ agentId: ID, runId: "m0" })).status]).toEqual([label, status]);
    }
    rmSync(join(dir, `count-${ID}`), { force: true });
    serve(ID, 1, thread("idle", [{ user: "x" }, { assistant: PROGRESS }]));
    const off = createAmpRuntime({
      env: { ...env, ORCHESTRATE_AMP_HANDOFF_GRACE_MS: "0" },
      onAttention: sink.onAttention,
    });
    expect((await off.wait({ agentId: ID, runId: "m0" })).status).toBe("finished");
    expect(exportsOf(ID)).toBe(4);
    expect(sink.lines).toEqual([]);
  });

  test("the window comes from ORCHESTRATE_AMP_HANDOFF_GRACE_MS and defaults to two minutes", () => {
    expect(DEFAULT_HANDOFF_GRACE_MS).toBe(120_000);
    expect(readRuntimeOptionsFromEnv({}).handoffGraceMs).toBeUndefined();
    expect(readRuntimeOptionsFromEnv({ ORCHESTRATE_AMP_HANDOFF_GRACE_MS: "0" }).handoffGraceMs).toBe(0);
    expect(readRuntimeOptionsFromEnv({ ORCHESTRATE_AMP_HANDOFF_GRACE_MS: "30000" }).handoffGraceMs).toBe(30_000);
    expect(readRuntimeOptionsFromEnv({ ORCHESTRATE_AMP_HANDOFF_GRACE_MS: "-1" }).handoffGraceMs).toBeUndefined();
    expect(readRuntimeOptionsFromEnv({ ORCHESTRATE_AMP_HANDOFF_GRACE_MS: "soon" }).handoffGraceMs).toBeUndefined();
  });
});

describe("describeRun", () => {
  test("an idle thread whose last message is still the user's is running", () => {
    expect(describeRun(thread("idle", [{ user: "x" }]), "m0").status).toBe("running");
  });
  test("only idle ends a run, even when an earlier assistant message carried text", () => {
    const midTurn: Msg[] = [{ user: "x" }, { assistant: "Looking..." }, { tool: "shell_command" }];
    for (const state of ["working", "streaming", "running_tools", "unexpected", ""]) {
      expect(describeRun(thread(state, midTurn), "m0").status).toBe("running");
    }
    expect(describeRun(thread("idle", [{ user: "x" }, { assistant: "done" }]), "m0").status).toBe(
      "finished"
    );
  });
  test("a cancelled assistant turn is cancelled, an errored one is error", () => {
    expect(
      describeRun(thread("idle", [{ user: "x" }, { assistant: "", stop: "cancelled" }]), "m0").status
    ).toBe("cancelled");
    expect(
      describeRun(thread("idle", [{ user: "x" }, { assistant: "boom", stop: "error" }]), "m0").status
    ).toBe("error");
  });
  test("a deleted thread is cancelled", () => {
    expect(describeRun(thread("idle", [{ user: "x" }], { deleted: true }), "m0").status).toBe(
      "cancelled"
    );
  });
  test("parseBranchLine reads backticked values and ignores (no branch)", () => {
    expect(parseBranchLine("## Branch\n`feat/x`\n")).toEqual(["feat/x"]);
    expect(parseBranchLine("## Branch\nfeat/y")).toEqual(["feat/y"]);
    expect(parseBranchLine("## Branch\n(no branch)")).toEqual([]);
    expect(parseBranchLine("no branch section")).toEqual([]);
  });
});

describe("stream", () => {
  test("yields assistant text deltas, tool calls, and the terminal status", async () => {
    serve(ID, 1, thread("working", [{ user: "go" }, { tool: "shell_command", id: "TU-9" }]));
    const partial = thread("streaming", [
      { user: "go" },
      { tool: "shell_command", id: "TU-9" },
      { toolResult: true },
      { assistant: "## Status\nsuc" },
    ]);
    serve(ID, 2, partial);
    serve(ID, 3, FINISHED);
    const rt = createAmpRuntime({ env });
    const events: StreamEvent[] = [];
    for await (const event of rt.stream({ agentId: ID, runId: "m0" })) events.push(event);
    expect(events[0]).toEqual({
      type: "tool_call",
      name: "shell_command",
      callId: "TU-9",
      status: "started",
    });
    const text = events
      .filter((e): e is Extract<StreamEvent, { type: "assistant" }> => e.type === "assistant")
      .map(e => e.text)
      .join("");
    expect(text).toBe(FINISHED.messages?.[3].content?.[0].text ?? "");
    expect(events.at(-1)).toEqual({ type: "status", status: "finished" });
    expect(events.filter(e => e.type === "tool_call")).toHaveLength(1);
  });
});

describe("stream notices a thread archived elsewhere", () => {
  test("ends with a cancelled status after the archived check", async () => {
    serve(ID, 1, thread("working", [{ user: "go" }]));
    writeFileSync(
      join(dir, `search-${ID}.json`),
      JSON.stringify([{ id: ID, title: "fixture", updatedAt: "2026-10-14T02:16:45.852Z" }])
    );
    const rt = createAmpRuntime({ env, archivedCheckMs: 1 });
    const events: StreamEvent[] = [];
    for await (const event of rt.stream({ agentId: ID, runId: "m0" })) events.push(event);
    expect(events.at(-1)).toEqual({ type: "status", status: "cancelled" });
    expect(calls().some(c => c[0] === "threads" && c[1] === "search")).toBe(true);
  });
});

describe("cancel", () => {
  test("archives the thread and reports the run cancelled afterwards", async () => {
    serve(ID, 1, thread("working", [{ user: "go" }]));
    const rt = createAmpRuntime({ env });
    await rt.cancel(ID, "m0");
    expect(existsSync(join(dir, `archived-${ID}`))).toBe(true);
    expect(calls().some(c => c[0] === "threads" && c[1] === "archive" && c[2] === ID)).toBe(true);
    expect((await rt.getRun(ID, "m0")).status).toBe("cancelled");
    expect((await rt.wait({ agentId: ID, runId: "m0" })).status).toBe("cancelled");
  });

  test("a run cancelled here stays cancelled even when its export later shows an idle reply", async () => {
    serve(ID, 1, { ...FINISHED, meta: { ...FINISHED.meta, archived: true } });
    const rt = createAmpRuntime({ env });
    await rt.cancel(ID, "m0");
    expect((await rt.wait({ agentId: ID, runId: "m0" })).status).toBe("cancelled");
  });
});

describe("archive", () => {
  test("retires the thread without touching the run: an archived idle reply still reads finished", async () => {
    serve(ID, 1, { ...FINISHED, meta: { ...FINISHED.meta, archived: true } });
    const rt = createAmpRuntime({ env });
    await rt.archive(ID);
    expect(existsSync(join(dir, `archived-${ID}`))).toBe(true);
    expect(calls()).toEqual([["threads", "archive", ID]]);
    expect((await rt.getRun(ID, "m0")).status).toBe("finished");
    const result = await rt.wait({ agentId: ID, runId: "m0" });
    expect(result.status).toBe("finished");
    expect(result.branches).toEqual(["orch/demo/task-a"]);
  });

  test("refuses anything but a whole thread id and surfaces a CLI failure", async () => {
    const rt = createAmpRuntime({ env });
    await expect(rt.archive("--last")).rejects.toBeInstanceOf(AgentRuntimeError);
    expect(calls()).toEqual([]);
  });

  test("describeRun: archived after an idle reply is finished, archived mid-turn or before a reply is cancelled", () => {
    const archived = { archived: true };
    expect(
      describeRun(thread("idle", [{ user: "x" }, { assistant: "done" }], archived), "m0").status
    ).toBe("finished");
    expect(
      describeRun(thread("working", [{ user: "x" }, { tool: "shell_command" }], archived), "m0").status
    ).toBe("cancelled");
    expect(describeRun(thread("idle", [{ user: "x" }], archived), "m0").status).toBe("cancelled");
    expect(
      describeRun(
        thread("idle", [{ user: "x" }, { assistant: "A" }, { user: "y" }], archived),
        "m2"
      ).status
    ).toBe("cancelled");
    // Earlier runs of an archived thread read as finished too.
    expect(
      describeRun(
        thread("idle", [{ user: "x" }, { assistant: "A" }, { user: "y" }, { assistant: "B" }], archived),
        "m0"
      ).status
    ).toBe("finished");
  });
});

describe("sendFollowUp", () => {
  test("continues the thread with the text on stdin and names the new run by message index", async () => {
    serve(ID, 1, FINISHED);
    const rt = createAmpRuntime({ env });
    const result = await rt.sendFollowUp(ID, "Reply with exactly FOLLOWUP-OK.");
    // Export 2 is the same thread: the message has not landed, so the count before the send is the id.
    expect(result).toEqual({ runId: "m4" });
    const call = calls().find(c => c[0] === "threads" && c[1] === "continue");
    expect(call).toEqual(["threads", "continue", ID, "-ox"]);
    expect(readFileSync(join(dir, "continue-stdin.txt"), "utf8")).toBe(
      "Reply with exactly FOLLOWUP-OK."
    );
    expect(exportsOf(ID)).toBe(2);
  });

  test("reads the index back after the send, so a message queued behind a turn gets the right run id", async () => {
    const working = thread("running_tools", [{ user: "do the task" }, { assistant: "On it." }, { tool: "shell_command" }]);
    serve(ID, 1, working);
    serve(ID, 2, thread("running_tools", [
      ...[{ user: "do the task" }, { assistant: "On it." }, { tool: "shell_command" }, { toolResult: true }, { tool: "shell_command", id: "TU-2" }] as Msg[],
      { user: "Read the handoffs and continue." },
    ]));
    const rt = createAmpRuntime({ env });
    expect(await rt.sendFollowUp(ID, "Read the handoffs and continue.\n")).toEqual({ runId: "m5" });
    // An earlier message with the same text does not shadow the new one, and the id is the last match.
    rmSync(join(dir, `count-${ID}`));
    serve(ID, 1, thread("idle", [{ user: "same" }, { assistant: "A" }]));
    serve(ID, 2, thread("idle", [{ user: "same" }, { assistant: "A" }, { user: "same" }]));
    expect(await rt.sendFollowUp(ID, "same")).toEqual({ runId: "m2" });
    // The export after a failed read falls back to the count before the send.
    rmSync(join(dir, `count-${ID}`));
    serve(ID, 1, FINISHED);
    serve(ID, 2, "fail");
    expect(await rt.sendFollowUp(ID, "x")).toEqual({ runId: "m4" });
  });
});

describe("getRun, latestRun, list, agentUrl", () => {
  test("getRun reports the current status", async () => {
    serve(ID, 1, thread("working", [{ user: "go" }]));
    const rt = createAmpRuntime({ env });
    expect((await rt.getRun(ID, "m0")).status).toBe("running");
  });

  test("latestRun points at the last user message", async () => {
    serve(
      ID,
      1,
      thread("idle", [{ user: "a" }, { assistant: "A" }, { user: "b" }, { assistant: "B" }])
    );
    const rt = createAmpRuntime({ env });
    expect(await rt.latestRun(ID)).toEqual({ agentId: ID, runId: "m2", status: "finished" });
  });

  test("latestRun skips the user-role messages Amp injects, such as integration hints", async () => {
    serve(
      ID,
      1,
      thread("idle", [
        { user: "do the task" },
        { user: '<integration_hint integration="slack">\nThe user asked from Slack.\n</integration_hint>' },
        { assistant: "ROUNDTRIP-OK" },
      ])
    );
    const rt = createAmpRuntime({ env });
    expect(await rt.latestRun(ID)).toEqual({ agentId: ID, runId: "m0", status: "finished" });
  });

  test("list maps thread titles to agent names", async () => {
    writeFileSync(
      join(dir, "list.json"),
      JSON.stringify([
        { id: ID, title: "demo-root", updated: "2026-10-14T02:14:24.451Z", tree: null, messageCount: 1 },
      ])
    );
    const rt = createAmpRuntime({ env });
    const items = await rt.list({ limit: 5 });
    expect(items).toEqual([
      { agentId: ID, name: "demo-root", updatedAt: "2026-10-14T02:14:24.451Z", messageCount: 1 },
    ]);
    const call = calls().find(c => c[1] === "list");
    expect(call).toEqual(["threads", "list", "--json", "--limit", "5"]);
  });

  test("list with labels searches for unarchived threads carrying every label", async () => {
    writeFileSync(
      join(dir, "search-labels.json"),
      JSON.stringify([{ id: ID, title: "ab12cd root", updatedAt: "2026-10-14T18:33:23.168Z" }])
    );
    const rt = createAmpRuntime({ env });
    const items = await rt.list({ limit: 50, labels: ["orchestrate", "goal-0123456789ab"] });
    expect(items).toEqual([
      { agentId: ID, name: "ab12cd root", updatedAt: "2026-10-14T18:33:23.168Z", messageCount: null },
    ]);
    expect(calls()).toEqual([
      ["threads", "search", "label:orchestrate label:goal-0123456789ab archived:false", "--json", "--limit", "50"],
    ]);
    await expect(rt.list({ limit: 5, labels: ["--last"] })).rejects.toBeInstanceOf(AgentRuntimeError);
    expect(calls()).toHaveLength(1);
    // An empty label list is the plain listing.
    await rt.list({ limit: 5, labels: [] });
    expect(calls()[1]).toEqual(["threads", "list", "--json", "--limit", "5"]);
  });

  test("agentUrl is the ampcode.com thread page", () => {
    const rt = createAmpRuntime({ env });
    expect(rt.agentUrl(ID)).toBe(`https://ampcode.com/threads/${ID}`);
  });

  test("the binary is configurable through ORCHESTRATE_AMP_BIN", async () => {
    const rt = createAmpRuntime({
      env: { ...env, PATH: process.env.PATH ?? "", ORCHESTRATE_AMP_BIN: join(FAKE_DIR, "amp") },
    });
    expect(rt.agentUrl(ID)).toContain(ID);
    serve(ID, 1, FINISHED);
    expect((await rt.getRun(ID, "m0")).status).toBe("finished");
  });
});

describe("argument injection", () => {
  test("an agent id that is not a whole thread id never reaches amp argv", async () => {
    const rt = createAmpRuntime({ env });
    serve(ID, 1, FINISHED);
    for (const bad of ["--help", "--last", "-h", `${ID} --last`, `x${ID}`, "", "$AMP_THREAD_ID"]) {
      const results = await Promise.allSettled([
        rt.sendFollowUp(bad, "hi"),
        rt.cancel(bad, "m0"),
        rt.getRun(bad, "m0"),
        rt.wait({ agentId: bad, runId: "m0" }),
        rt.latestRun(bad),
        (async () => {
          for await (const _ of rt.stream({ agentId: bad, runId: "m0" })) {
          }
        })(),
      ]);
      for (const r of results) {
        expect(r.status).toBe("rejected");
        expect(r.status === "rejected" && r.reason).toBeInstanceOf(AgentRuntimeError);
        expect(r.status === "rejected" && r.reason.message).toContain(JSON.stringify(bad));
      }
    }
    expect(calls()).toEqual([]);
  });

  test("a run id that is not m<index> is refused before any command runs", async () => {
    const rt = createAmpRuntime({ env });
    const err = await rt.getRun(ID, "--last").catch(e => e);
    expect(err).toBeInstanceOf(AgentRuntimeError);
    expect(err.message).toContain('"--last"');
    expect(calls()).toEqual([]);
  });

  test("isThreadId accepts only the full id", () => {
    expect(isThreadId(ID)).toBe(true);
    expect(isThreadId(ID.toUpperCase())).toBe(true);
    expect(isThreadId(`https://ampcode.com/threads/${ID}`)).toBe(false);
    expect(isThreadId("--last")).toBe(false);
  });
});

describe("models", () => {
  test("lists the built-in modes when the CLI cannot list plugin modes", async () => {
    const catalog = createAmpModelCatalog({ env });
    expect(await catalog.models()).toEqual([...AMP_BUILTIN_MODES]);
    expect(await catalog.probe("high")).toBe(true);
    expect(await catalog.probe("HIGH")).toBe(true);
    expect(await catalog.probe("claude-opus-4-8")).toBe(false);
  });

  test("adds plugin modes the listing names", async () => {
    writeFileSync(
      join(dir, "agent-options.json"),
      JSON.stringify({ models: [{ id: "openai/gpt-5" }], agentModes: [{ key: "grok46" }, "kimi-k3"] })
    );
    const catalog = createAmpModelCatalog({ env });
    expect(await catalog.models()).toEqual([...AMP_BUILTIN_MODES, "grok46", "kimi-k3"]);
    expect(await catalog.probe("kimi-k3")).toBe(true);
  });

  test("pluginModesFrom ignores payloads without a mode list", () => {
    expect(pluginModesFrom({ models: [], builtinToolNames: [] })).toEqual([]);
    expect(pluginModesFrom(null)).toEqual([]);
  });
});
