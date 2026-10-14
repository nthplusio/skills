/**
 * The `orchestrate-bridge` plugin without Amp: a fake `PluginAPI` whose
 * `getBuiltinAgent` returns a fake agent that records `createThread`'s
 * options and hands back a fake thread recording `addLabels` and `append`.
 * The plugin's default export is driven through the fake's `session.start`
 * and dispose callbacks; requests go over real loopback HTTP.
 */
import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { existsSync, mkdtempSync, readFileSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import plugin, {
  type BridgeAPI,
  type BridgeFile,
  LABEL_PATTERN,
  MAX_PROMPT_BYTES,
  type Mode,
  resolveWorkingDir,
  type SpawnRequest,
  startBridge,
  validateSpawnRequest,
} from "../plugin/orchestrate-bridge/index.ts";

const VEHICLE = "T-01a13b70-0000-0000-0000-000000000001" as const;
const CHILD = "T-01a13b70-0000-0000-0000-000000000002" as const;
const PROJECT = "https://github.com/IL-SCoussens/playgrounds";

type Call = { op: string; args: unknown };

interface FakeAmp extends BridgeAPI {
  calls: Call[];
  logs: string[];
  handlers: Record<string, (...args: unknown[]) => unknown>;
  disposers: (() => void | Promise<void>)[];
  failWith?: Error;
  system: { workspaceRoot: { toString(): string } | null };
  helpers: { filePathFromURI(uri: { toString(): string }): string };
  on(name: string, fn: (...args: unknown[]) => unknown): { unsubscribe(): void };
  onDispose(fn: () => void | Promise<void>): { unsubscribe(): void };
}

function fakeAmp(workspaceRoot: string | null = null): FakeAmp {
  const amp: FakeAmp = {
    calls: [],
    logs: [],
    handlers: {},
    disposers: [],
    system: { workspaceRoot: workspaceRoot === null ? null : { toString: () => `file://${workspaceRoot}` } },
    helpers: { filePathFromURI: (uri) => uri.toString().replace(/^file:\/\//, "") },
    logger: { log: (...args) => amp.logs.push(args.map(String).join(" ")) },
    on(name, fn) {
      amp.handlers[name] = fn;
      return { unsubscribe() {} };
    },
    onDispose(fn) {
      amp.disposers.push(fn);
      return { unsubscribe() {} };
    },
    getBuiltinAgent(mode: Mode) {
      amp.calls.push({ op: "getBuiltinAgent", args: mode });
      return {
        async createThread(options) {
          amp.calls.push({ op: "createThread", args: options });
          if (amp.failWith) throw amp.failWith;
          return {
            id: CHILD,
            async addLabels(labels: string[]) {
              amp.calls.push({ op: "addLabels", args: labels });
              return labels;
            },
            async append(messages) {
              amp.calls.push({ op: "append", args: messages });
            },
          };
        },
      };
    },
  };
  return amp;
}

function goodRequest(extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    name: "th-e-child",
    prompt: "Reply with exactly the single word pong and nothing else.",
    project: PROJECT,
    mode: "low",
    labels: ["orchestrate", "orch-probe"],
    ...extra,
  };
}

async function post(file: BridgeFile, body: unknown, token: string | null = file.token): Promise<{ status: number; json: Record<string, unknown> }> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (token !== null) headers.authorization = `Bearer ${token}`;
  const res = await fetch(file.url, { method: "POST", headers, body: typeof body === "string" ? body : JSON.stringify(body) });
  return { status: res.status, json: (await res.json()) as Record<string, unknown> };
}

function readBridge(dir: string): BridgeFile {
  return JSON.parse(readFileSync(join(dir, ".orchestrate", "bridge.json"), "utf8")) as BridgeFile;
}

let dir: string;
let savedEnv: string | undefined;

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "th-e-bridge-"));
  savedEnv = process.env.AMP_WORKING_DIRECTORY;
  process.env.AMP_WORKING_DIRECTORY = dir;
});

afterEach(() => {
  if (savedEnv === undefined) delete process.env.AMP_WORKING_DIRECTORY;
  else process.env.AMP_WORKING_DIRECTORY = savedEnv;
  rmSync(dir, { recursive: true, force: true });
});

describe("the plugin's default export", () => {
  test("session.start writes bridge.json (0600) in the working directory; dispose removes it and closes the server", async () => {
    const amp = fakeAmp();
    plugin(amp as never);
    expect(Object.keys(amp.handlers)).toEqual(["session.start"]);
    expect(amp.disposers).toHaveLength(1);

    await amp.handlers["session.start"]({ thread: { id: VEHICLE } }, {});
    const path = join(dir, ".orchestrate", "bridge.json");
    expect(existsSync(path)).toBe(true);
    expect(statSync(path).mode & 0o777).toBe(0o600);
    const file = readBridge(dir);
    expect(file.url).toMatch(/^http:\/\/127\.0\.0\.1:\d+\/spawn$/);
    expect(file.token).toMatch(/^[0-9a-f]{48}$/);
    expect(file.thread).toBe(VEHICLE);
    expect(Number.isFinite(Date.parse(file.startedAt))).toBe(true);
    expect(amp.logs.join("\n")).not.toContain(file.token);

    await amp.disposers[0]();
    expect(existsSync(path)).toBe(false);
    await expect(fetch(file.url, { method: "POST" })).rejects.toThrow();
  });

  test("a good request creates the child under the session thread with the right options, in order", async () => {
    const amp = fakeAmp();
    plugin(amp as never);
    await amp.handlers["session.start"]({ thread: { id: VEHICLE } }, {});
    const file = readBridge(dir);

    const { status, json } = await post(file, goodRequest());
    expect(status).toBe(200);
    expect(json).toEqual({ threadID: CHILD, parent: VEHICLE });
    expect(amp.calls).toEqual([
      { op: "getBuiltinAgent", args: "low" },
      { op: "createThread", args: { parentThreadID: VEHICLE, executor: "orb", project: PROJECT, visibility: "private" } },
      { op: "addLabels", args: ["orchestrate", "orch-probe"] },
      { op: "append", args: [{ type: "user-message", content: goodRequest().prompt }] },
    ]);
    expect(amp.logs.some((l) => l.includes(`spawned ${CHILD} under ${VEHICLE}`))).toBe(true);
    expect(amp.logs.join("\n")).not.toContain(file.token);
    await amp.disposers[0]();
  });

  test("a nodeType becomes the node-<type> label ahead of the labels, once, and names the log line", async () => {
    const amp = fakeAmp();
    plugin(amp as never);
    await amp.handlers["session.start"]({ thread: { id: VEHICLE } }, {});
    const file = readBridge(dir);

    expect((await post(file, goodRequest({ nodeType: "planner" }))).status).toBe(200);
    expect(amp.calls[2]).toEqual({ op: "addLabels", args: ["node-planner", "orchestrate", "orch-probe"] });
    expect(amp.logs.some((l) => l.includes(`(planner th-e-child)`))).toBe(true);
    // A caller that already sent the label (for a bridge without the field) gets it once.
    amp.calls.length = 0;
    expect((await post(file, goodRequest({ nodeType: "worker", labels: ["orchestrate", "node-worker"] }))).status).toBe(200);
    expect(amp.calls[2]).toEqual({ op: "addLabels", args: ["node-worker", "orchestrate"] });
    // Without the field nothing changes.
    amp.calls.length = 0;
    expect((await post(file, goodRequest({ labels: [] }))).status).toBe(200);
    expect(amp.calls.map((c) => c.op)).toEqual(["getBuiltinAgent", "createThread", "append"]);
    expect(amp.logs.some((l) => l.includes(`(node th-e-child)`))).toBe(true);
    await amp.disposers[0]();
  });

  test("an explicit parent is used instead of the session thread; empty labels skip addLabels", async () => {
    const amp = fakeAmp();
    plugin(amp as never);
    await amp.handlers["session.start"]({ thread: { id: VEHICLE } }, {});
    const file = readBridge(dir);
    const other = "T-01a13b70-0000-0000-0000-00000000000f";

    const { status, json } = await post(file, goodRequest({ parent: other, labels: [] }));
    expect(status).toBe(200);
    expect(json).toEqual({ threadID: CHILD, parent: other });
    expect(amp.calls.map((c) => c.op)).toEqual(["getBuiltinAgent", "createThread", "append"]);
    expect((amp.calls[1].args as { parentThreadID: string }).parentThreadID).toBe(other);
    await amp.disposers[0]();
  });

  test("a second session.start replaces the bridge: the old port closes and the file names the new thread", async () => {
    const amp = fakeAmp();
    plugin(amp as never);
    await amp.handlers["session.start"]({ thread: { id: VEHICLE } }, {});
    const first = readBridge(dir);
    const second_id = "T-01a13b70-0000-0000-0000-000000000003";
    await amp.handlers["session.start"]({ thread: { id: second_id } }, {});
    const second = readBridge(dir);
    expect(second.thread).toBe(second_id);
    expect(second.token).not.toBe(first.token);
    await expect(fetch(first.url, { method: "POST" })).rejects.toThrow();
    expect((await post(second, goodRequest())).status).toBe(200);
    await amp.disposers[0]();
    expect(existsSync(join(dir, ".orchestrate", "bridge.json"))).toBe(false);
  });
});

describe("refusals", () => {
  let amp: FakeAmp;
  let file: BridgeFile;

  beforeEach(async () => {
    amp = fakeAmp();
    plugin(amp as never);
    await amp.handlers["session.start"]({ thread: { id: VEHICLE } }, {});
    file = readBridge(dir);
  });

  afterEach(async () => {
    await amp.disposers[0]();
  });

  test("a bad or missing token is 401 and nothing is created", async () => {
    expect(await post(file, goodRequest(), "not-the-token")).toEqual({ status: 401, json: { error: "missing or invalid bearer token" } });
    expect((await post(file, goodRequest(), null)).status).toBe(401);
    expect((await post(file, goodRequest(), `${file.token}0`)).status).toBe(401);
    expect(amp.calls).toEqual([]);
  });

  test("a bad label is 400 with the pattern in the reason", async () => {
    const { status, json } = await post(file, goodRequest({ labels: ["orchestrate", "run:ab12"] }));
    expect(status).toBe(400);
    expect(json.error).toContain('"run:ab12"');
    expect(json.error).toContain(LABEL_PATTERN.source);
    expect(amp.calls).toEqual([]);
  });

  test("a bad mode is 400", async () => {
    const { status, json } = await post(file, goodRequest({ mode: "smart" }));
    expect(status).toBe(400);
    expect(json.error).toBe("mode must be one of low|medium|high|ultra");
    expect(amp.calls).toEqual([]);
  });

  test("an oversized prompt is 400, whether it is caught by the field check or the body cap", async () => {
    const atLimit = await post(file, goodRequest({ prompt: "x".repeat(MAX_PROMPT_BYTES) }));
    expect(atLimit.status).toBe(400);
    expect(atLimit.json.error).toBe(`prompt must be under ${MAX_PROMPT_BYTES} bytes`);
    const wayOver = await post(file, goodRequest({ prompt: "x".repeat(MAX_PROMPT_BYTES * 2) }));
    expect(wayOver.status).toBe(400);
    expect(String(wayOver.json.error)).toMatch(/must be under \d+ bytes/);
    expect(amp.calls).toEqual([]);
  });

  test("a parent that is not a thread id, a missing project, and a non-JSON body are 400", async () => {
    expect((await post(file, goodRequest({ parent: "--last" }))).json.error).toBe("parent must be a thread id (T-...)");
    expect((await post(file, goodRequest({ project: "" }))).json.error).toBe("project must be a non-empty string");
    expect((await post(file, "{not json")).json).toEqual({ error: "body must be JSON" });
    expect((await post(file, [1, 2])).json).toEqual({ error: "body must be a JSON object" });
    expect(amp.calls).toEqual([]);
  });

  test("an Amp failure is 500 with the message and no stack", async () => {
    amp.failWith = new Error("project matches no project you can access");
    const { status, json } = await post(file, goodRequest());
    expect(status).toBe(500);
    expect(json).toEqual({ error: "project matches no project you can access" });
    expect(JSON.stringify(json)).not.toContain("at ");
    expect(amp.logs.some((l) => l.includes("spawn of th-e-child failed"))).toBe(true);
  });

  test("the token is checked before the route: a wrong path or method with a good token is 404 or 405, without it 401", async () => {
    const base = file.url.replace(/\/spawn$/, "");
    const auth = { authorization: `Bearer ${file.token}` };
    expect((await fetch(`${base}/other`, { method: "POST", headers: auth })).status).toBe(404);
    expect((await fetch(file.url, { method: "GET", headers: auth })).status).toBe(405);
    expect((await fetch(`${base}/other`, { method: "POST" })).status).toBe(401);
    expect((await fetch(file.url, { method: "GET" })).status).toBe(401);
  });
});

describe("validateSpawnRequest", () => {
  const good = goodRequest();

  test("accepts a good request and defaults parent to the session thread and labels to none", () => {
    const result = validateSpawnRequest(good, VEHICLE);
    expect(result.ok).toBe(true);
    const value = (result as { ok: true; value: SpawnRequest }).value;
    expect(value).toEqual({ ...good, parent: VEHICLE } as SpawnRequest);
    const { labels: _omit, ...withoutLabels } = good;
    const defaulted = validateSpawnRequest(withoutLabels, VEHICLE) as { ok: true; value: SpawnRequest };
    expect(defaulted.value.labels).toEqual([]);
  });

  test("names the first bad field", () => {
    const cases: [Record<string, unknown>, string][] = [
      [{ ...good, name: "" }, "name must be a non-empty string"],
      [{ ...good, name: "n".repeat(201) }, "name must be at most 200 characters"],
      [{ ...good, prompt: "   " }, "prompt must be a non-empty string"],
      [{ ...good, project: 7 }, "project must be a non-empty string"],
      [{ ...good, mode: "LOW" }, "mode must be one of low|medium|high|ultra"],
      [{ ...good, labels: "orchestrate" }, "labels must be an array of strings"],
      [{ ...good, labels: ["-leading"] }, 'label "-leading" must match'],
      [{ ...good, labels: ["a".repeat(33)] }, "at most 32 characters"],
      [{ ...good, labels: Array.from({ length: 21 }, (_, i) => `l${i}`) }, "labels must hold at most 20 items"],
      [{ ...good, parent: "not-a-thread" }, "parent must be a thread id (T-...)"],
      [{ ...good, nodeType: "root" }, "nodeType must be one of planner|subplanner|worker|verifier"],
      [{ ...good, nodeType: 1 }, "nodeType must be one of"],
    ];
    for (const [body, reason] of cases) {
      const result = validateSpawnRequest(body, VEHICLE);
      expect(result.ok).toBe(false);
      expect((result as { ok: false; error: string }).error).toContain(reason);
    }
  });
});

describe("resolveWorkingDir", () => {
  test("AMP_WORKING_DIRECTORY wins, then the workspace root, then cwd", () => {
    expect(resolveWorkingDir({ AMP_WORKING_DIRECTORY: "/env" }, "/root", "/cwd")).toBe("/env");
    expect(resolveWorkingDir({ AMP_WORKING_DIRECTORY: "  " }, "/root", "/cwd")).toBe("/root");
    expect(resolveWorkingDir({}, null, "/cwd")).toBe("/cwd");
  });
});

describe("startBridge", () => {
  test("serialises spawns: the second request waits for the first thread to be created", async () => {
    const amp = fakeAmp();
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => (release = r));
    const slow: BridgeAPI = {
      logger: amp.logger,
      getBuiltinAgent(mode) {
        const agent = amp.getBuiltinAgent(mode);
        return {
          async createThread(options) {
            const thread = await agent.createThread(options);
            if (amp.calls.filter((c) => c.op === "createThread").length === 1) await gate;
            return thread;
          },
        };
      },
    };
    const bridge = await startBridge({ amp: slow, thread: VEHICLE, dir, now: () => new Date("2026-10-14T00:00:00Z") });
    const file = readBridge(dir);
    expect(file.startedAt).toBe("2026-10-14T00:00:00.000Z");
    expect(bridge.file).toBe(join(dir, ".orchestrate", "bridge.json"));

    const first = post(file, goodRequest({ name: "first" }));
    const second = post(file, goodRequest({ name: "second" }));
    await new Promise((r) => setTimeout(r, 50));
    expect(amp.calls.filter((c) => c.op === "createThread")).toHaveLength(1);
    release();
    expect((await first).status).toBe(200);
    expect((await second).status).toBe(200);
    expect(amp.calls.map((c) => c.op)).toEqual([
      "getBuiltinAgent", "createThread", "addLabels", "append",
      "getBuiltinAgent", "createThread", "addLabels", "append",
    ]);
    await bridge.close();
    await bridge.close();
    expect(existsSync(bridge.file)).toBe(false);
  });
});
