/**
 * orchestrate-bridge: a loopback endpoint, inside the Amp process of the
 * thread that runs the orchestrate loop, that creates child threads with a
 * parent. The `amp` CLI cannot set `parentThreadID`; the plugin API can.
 *
 * On `session.start` the plugin listens on an ephemeral 127.0.0.1 port with a
 * random bearer token and writes `<working dir>/.orchestrate/bridge.json`:
 *
 *   { "url": "http://127.0.0.1:<port>/spawn", "token": "<hex>",
 *     "thread": "T-...", "startedAt": "<iso>" }
 *
 * The loop (the pack's `agent-runtime.ts`) reads that file and sends
 *
 *   POST <url>   Authorization: Bearer <token>
 *   { "name", "prompt", "project", "mode", "labels", "parent"? }
 *
 * and gets `200 {"threadID": "T-...", "parent": "T-..."}`. A bad token is
 * `401 {"error"}`, bad input `400 {"error"}`, an Amp failure `500 {"error"}`,
 * never a stack. The working directory is `AMP_WORKING_DIRECTORY`, else the
 * plugin system's `workspaceRoot`, else the process's cwd. On dispose the
 * server closes and the file is removed.
 *
 * The file imports nothing from the adapter, so it can be copied alone into
 * a plugins directory (`.amp/plugins/orchestrate-bridge/index.ts`). The
 * server factory and the request handler are exported so a test can drive
 * them with a fake `PluginAPI`.
 */

import type { PluginAPI } from "@ampcode/plugin";
import { randomBytes, timingSafeEqual } from "node:crypto";
import { chmodSync, mkdirSync, renameSync, unlinkSync, writeFileSync } from "node:fs";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { dirname, join } from "node:path";

export const description =
  "Loopback endpoint for the orchestrate loop: POST /spawn creates an orb thread nested under the current thread, labels it, and sends its prompt. Writes .orchestrate/bridge.json with the URL and a bearer token.";

export const BRIDGE_DIR = ".orchestrate";
export const BRIDGE_FILE = "bridge.json";
export const SPAWN_PATH = "/spawn";
export const MODES = ["low", "medium", "high", "ultra"] as const;
export const LABEL_PATTERN = /^[A-Za-z0-9][A-Za-z0-9-]*$/;
export const MAX_LABEL_LENGTH = 32;
export const MAX_LABELS = 20;
export const MAX_NAME_LENGTH = 200;
export const MAX_PROMPT_BYTES = 200 * 1024;
/** The whole request body: the prompt plus the other fields. */
export const MAX_BODY_BYTES = MAX_PROMPT_BYTES + 16 * 1024;
export const THREAD_ID_PATTERN = /^T-[A-Za-z0-9-]+$/;

export type Mode = (typeof MODES)[number];
export type ThreadID = `T-${string}`;

export interface SpawnRequest {
  name: string;
  prompt: string;
  project: string;
  mode: Mode;
  labels: string[];
  parent: ThreadID;
}

export interface SpawnResponse {
  threadID: ThreadID;
  parent: ThreadID;
}

export interface BridgeFile {
  url: string;
  token: string;
  thread: ThreadID;
  startedAt: string;
}

/**
 * The slice of `PluginAPI` the bridge uses. A test passes a fake with this
 * shape; the default export passes the real one.
 */
export interface BridgeThread {
  id: ThreadID;
  addLabels(labels: string[]): Promise<unknown>;
  append(messages: { type: "user-message"; content: string }[]): Promise<void>;
}
export interface BridgeAgent {
  createThread(options: {
    parentThreadID: ThreadID;
    executor: "orb";
    project: string;
    visibility: "private";
  }): Promise<BridgeThread>;
}
export interface BridgeAPI {
  logger: { log: (...args: unknown[]) => void };
  getBuiltinAgent(mode: Mode): BridgeAgent;
}

export type Validation = { ok: true; value: SpawnRequest } | { ok: false; error: string };

/** Check a parsed body field by field; the error names the first bad field. */
export function validateSpawnRequest(body: unknown, defaultParent: ThreadID): Validation {
  if (body === null || typeof body !== "object" || Array.isArray(body)) {
    return { ok: false, error: "body must be a JSON object" };
  }
  const b = body as Record<string, unknown>;

  const name = b.name;
  if (typeof name !== "string" || name.trim() === "") return { ok: false, error: "name must be a non-empty string" };
  if (name.length > MAX_NAME_LENGTH) return { ok: false, error: `name must be at most ${MAX_NAME_LENGTH} characters` };

  const prompt = b.prompt;
  if (typeof prompt !== "string" || prompt.trim() === "") {
    return { ok: false, error: "prompt must be a non-empty string" };
  }
  if (Buffer.byteLength(prompt, "utf8") >= MAX_PROMPT_BYTES) {
    return { ok: false, error: `prompt must be under ${MAX_PROMPT_BYTES} bytes` };
  }

  const project = b.project;
  if (typeof project !== "string" || project.trim() === "") {
    return { ok: false, error: "project must be a non-empty string" };
  }

  const mode = b.mode;
  if (typeof mode !== "string" || !(MODES as readonly string[]).includes(mode)) {
    return { ok: false, error: `mode must be one of ${MODES.join("|")}` };
  }

  const labels = b.labels === undefined ? [] : b.labels;
  if (!Array.isArray(labels)) return { ok: false, error: "labels must be an array of strings" };
  if (labels.length > MAX_LABELS) return { ok: false, error: `labels must hold at most ${MAX_LABELS} items` };
  for (const label of labels) {
    if (typeof label !== "string" || !LABEL_PATTERN.test(label) || label.length > MAX_LABEL_LENGTH) {
      return {
        ok: false,
        error: `label ${JSON.stringify(label)} must match ${LABEL_PATTERN.source} and be at most ${MAX_LABEL_LENGTH} characters`,
      };
    }
  }

  let parent: ThreadID = defaultParent;
  if (b.parent !== undefined) {
    if (typeof b.parent !== "string" || !THREAD_ID_PATTERN.test(b.parent)) {
      return { ok: false, error: "parent must be a thread id (T-...)" };
    }
    parent = b.parent as ThreadID;
  }

  return { ok: true, value: { name, prompt, project, mode: mode as Mode, labels: labels as string[], parent } };
}

/**
 * Create the child thread: create under the parent as a private orb thread,
 * add the labels, then append the prompt, in that order, so the thread
 * carries its labels before it starts working.
 */
export async function spawnThread(amp: BridgeAPI, request: SpawnRequest): Promise<SpawnResponse> {
  const thread = await amp.getBuiltinAgent(request.mode).createThread({
    parentThreadID: request.parent,
    executor: "orb",
    project: request.project,
    visibility: "private",
  });
  if (request.labels.length > 0) await thread.addLabels(request.labels);
  await thread.append([{ type: "user-message", content: request.prompt }]);
  return { threadID: thread.id, parent: request.parent };
}

function tokenMatches(header: string | string[] | undefined, token: string): boolean {
  if (typeof header !== "string") return false;
  const prefix = "Bearer ";
  if (!header.startsWith(prefix)) return false;
  const given = Buffer.from(header.slice(prefix.length), "utf8");
  const want = Buffer.from(token, "utf8");
  return given.length === want.length && timingSafeEqual(given, want);
}

function readBody(req: IncomingMessage, limit: number): Promise<{ text: string } | { tooLarge: true }> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    let size = 0;
    let done = false;
    req.on("data", (chunk: Buffer) => {
      if (done) return;
      size += chunk.length;
      if (size > limit) {
        done = true;
        req.resume();
        resolve({ tooLarge: true });
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => {
      if (!done) resolve({ text: Buffer.concat(chunks).toString("utf8") });
    });
    req.on("error", reject);
  });
}

function send(res: ServerResponse, status: number, body: object): void {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

function errorMessage(e: unknown): string {
  if (e instanceof Error) return e.message;
  return typeof e === "string" ? e : "unknown error";
}

export interface HandlerOptions {
  amp: BridgeAPI;
  token: string;
  /** The session thread: the default parent of every spawn. */
  thread: ThreadID;
}

/**
 * The request handler for one bridge. Checks the token before anything else,
 * so an unauthenticated caller learns nothing about the routes. Spawns run
 * one at a time: a second request waits for the first to finish.
 */
export function createBridgeHandler(options: HandlerOptions): (req: IncomingMessage, res: ServerResponse) => void {
  const { amp, token, thread } = options;
  let queue: Promise<unknown> = Promise.resolve();

  return (req, res) => {
    void (async () => {
      try {
        if (!tokenMatches(req.headers.authorization, token)) {
          send(res, 401, { error: "missing or invalid bearer token" });
          return;
        }
        const path = (req.url ?? "").split("?")[0];
        if (path !== SPAWN_PATH) {
          send(res, 404, { error: `unknown path; POST ${SPAWN_PATH}` });
          return;
        }
        if (req.method !== "POST") {
          send(res, 405, { error: `method must be POST` });
          return;
        }
        const body = await readBody(req, MAX_BODY_BYTES);
        if ("tooLarge" in body) {
          send(res, 400, { error: `body must be under ${MAX_BODY_BYTES} bytes` });
          return;
        }
        let parsed: unknown;
        try {
          parsed = JSON.parse(body.text);
        } catch {
          send(res, 400, { error: "body must be JSON" });
          return;
        }
        const checked = validateSpawnRequest(parsed, thread);
        if (!checked.ok) {
          send(res, 400, { error: checked.error });
          return;
        }
        const request = checked.value;
        const run = queue.then(() => spawnThread(amp, request));
        queue = run.catch(() => undefined);
        try {
          const result = await run;
          amp.logger.log(`orchestrate-bridge: spawned ${result.threadID} under ${result.parent} (${request.name})`);
          send(res, 200, result);
        } catch (e) {
          amp.logger.log(`orchestrate-bridge: spawn of ${request.name} failed: ${errorMessage(e)}`);
          send(res, 500, { error: errorMessage(e) });
        }
      } catch (e) {
        amp.logger.log(`orchestrate-bridge: request failed: ${errorMessage(e)}`);
        if (!res.headersSent) send(res, 500, { error: errorMessage(e) });
        else res.end();
      }
    })();
  };
}

export interface Bridge {
  url: string;
  token: string;
  thread: ThreadID;
  /** The bridge file's path. */
  file: string;
  server: Server;
  /** Close the server and remove the file. Safe to call twice. */
  close(): Promise<void>;
}

export interface StartOptions {
  amp: BridgeAPI;
  thread: ThreadID;
  /** The working directory; the file goes at `<dir>/.orchestrate/bridge.json`. */
  dir: string;
  now?: () => Date;
}

/** Write the file atomically with mode 0600, so a reader never sees half of it. */
function writePrivateJson(file: string, value: object): void {
  mkdirSync(dirname(file), { recursive: true });
  const tmp = `${file}.${process.pid}.tmp`;
  writeFileSync(tmp, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
  chmodSync(tmp, 0o600);
  renameSync(tmp, file);
}

/**
 * Start one bridge: listen on an ephemeral loopback port, mint a token, write
 * the file. The token is never logged.
 */
export async function startBridge(options: StartOptions): Promise<Bridge> {
  const { amp, thread, dir } = options;
  const token = randomBytes(24).toString("hex");
  const server = createServer(createBridgeHandler({ amp, token, thread }));
  server.keepAliveTimeout = 1000;
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      server.off("error", reject);
      resolve();
    });
  });
  const address = server.address();
  if (address === null || typeof address === "string") {
    server.close();
    throw new Error("orchestrate-bridge: server has no TCP address");
  }
  const url = `http://127.0.0.1:${address.port}${SPAWN_PATH}`;
  const file = join(dir, BRIDGE_DIR, BRIDGE_FILE);
  const record: BridgeFile = { url, token, thread, startedAt: (options.now ?? (() => new Date()))().toISOString() };
  try {
    writePrivateJson(file, record);
  } catch (e) {
    server.close();
    throw e;
  }
  amp.logger.log(`orchestrate-bridge: listening at ${url} for ${thread}; file ${file}`);

  let closed = false;
  const close = async (): Promise<void> => {
    if (closed) return;
    closed = true;
    try {
      unlinkSync(file);
    } catch (e) {
      if ((e as NodeJS.ErrnoException).code !== "ENOENT") amp.logger.log(`orchestrate-bridge: could not remove ${file}: ${errorMessage(e)}`);
    }
    server.closeAllConnections?.();
    await new Promise<void>((resolve) => server.close(() => resolve()));
    amp.logger.log(`orchestrate-bridge: closed ${url}`);
  };
  return { url, token, thread, file, server, close };
}

/**
 * The working directory: `AMP_WORKING_DIRECTORY`, else the plugin system's
 * workspace root, else the process's cwd.
 */
export function resolveWorkingDir(env: NodeJS.ProcessEnv, workspaceRoot: string | null, cwd: string): string {
  const fromEnv = env.AMP_WORKING_DIRECTORY;
  if (typeof fromEnv === "string" && fromEnv.trim() !== "") return fromEnv;
  if (workspaceRoot !== null && workspaceRoot.trim() !== "") return workspaceRoot;
  return cwd;
}

function workspaceRootPath(amp: PluginAPI): string | null {
  const root = amp.system.workspaceRoot;
  if (root === null) return null;
  try {
    return amp.helpers.filePathFromURI(root);
  } catch {
    return null;
  }
}

export default function (amp: PluginAPI): void {
  let current: Bridge | undefined;

  amp.on("session.start", async (event) => {
    const dir = resolveWorkingDir(process.env, workspaceRootPath(amp), process.cwd());
    const previous = current;
    current = undefined;
    if (previous !== undefined) await previous.close();
    try {
      current = await startBridge({ amp, thread: event.thread.id, dir });
    } catch (e) {
      amp.logger.log(`orchestrate-bridge: could not start: ${errorMessage(e)}`);
    }
  });

  amp.onDispose(async () => {
    const bridge = current;
    current = undefined;
    if (bridge !== undefined) await bridge.close();
  });
}
