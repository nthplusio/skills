/**
 * The seam between upstream orchestrate and the Amp agent runtime.
 *
 * Upstream calls the Cursor SDK's static `Agent` (`create`, `send`,
 * `getRun`, `run.stream`, `run.wait`, `run.cancel`, `list`, `listRuns`,
 * `resume`). This module builds that same surface over the `AgentRuntime`
 * in `pstack-sync/adapters/amp/agent-runtime.ts`, so the ported files keep
 * upstream's call sites and only their import lines change.
 *
 * Two layouts have to resolve: inside the skill pack this file sits at
 * `pstack-sync/adapters/amp/agent-runtime/scripts/core/`, and once the sync
 * installs it, at `<skills>/orchestrate/scripts/core/` beside
 * `<skills>/pstack-sync/adapters/amp/`. `loadSDK` tries both, and
 * `ORCHESTRATE_AMP_RUNTIME_DIR` names a directory explicitly. The type-only
 * imports below name the installed layout, where `npm run typecheck` runs;
 * bun erases them, so the pack layout runs the same code.
 *
 * One Amp-specific fact lives here. A thread id exists only after
 * `amp -ox` runs, but upstream builds the prompt between `Agent.create` and
 * `agent.send`. Until `send`, `agent.agentId` is `$AMP_THREAD_ID`, which
 * orbs set in the environment to the thread's own id; `send` appends a note
 * telling the agent to expand it. After `send`, `agentId` is the real id.
 */

import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import type {
  AgentApi,
  AgentCreateOptions,
  AgentListItem,
  AgentRuntime,
  GetRunOptions,
  ModelCatalog,
  Run,
  RunListItem,
  RunOperation,
  RunResult,
  RunStatus,
  SDKAgent,
  SDKMessage,
} from "../../../pstack-sync/adapters/interface.ts";

export type {
  AgentApi,
  AgentRuntime,
  ModelCatalog,
  ModelSelection,
  Run,
  RunResult,
  SDKAgent,
  SDKMessage,
} from "../../../pstack-sync/adapters/interface.ts";

export const PENDING_AGENT_ID = "$AMP_THREAD_ID";

// The same shape `agent-runtime.ts` enforces; repeated here because this file
// cannot import that module statically (its location depends on the layout).
const THREAD_ID_EXACT_RE = /^T-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** True for a whole Amp thread id and nothing else. */
export function isThreadId(value: unknown): value is string {
  return typeof value === "string" && THREAD_ID_EXACT_RE.test(value);
}

/** True for the unexpanded placeholder, `$AMP_THREAD_ID` or `${AMP_THREAD_ID}`. */
export function isPendingAgentId(value: unknown): boolean {
  return typeof value === "string" && /^\$\{?AMP_THREAD_ID\}?$/.test(value.trim());
}

/** Why `value` cannot be used as an agent id, or null when it can. */
export function badThreadIdReason(value: unknown, what = "agent id"): string | null {
  if (isThreadId(value)) return null;
  if (isPendingAgentId(value)) {
    return `${what} is the unexpanded placeholder ${PENDING_AGENT_ID}; use the value of \`echo $AMP_THREAD_ID\` in that agent's own orb, or the agentId recorded in state.json`;
  }
  return `${what} ${JSON.stringify(value)} is not an Amp thread id`;
}

/**
 * Refuse an agent id that is not a whole thread id before it reaches the
 * runtime, so `--last` or `--help` from state.json or a flag never becomes an
 * `amp` argument. The error carries the runtime's error name, so callers that
 * test `isAgentRuntimeError` treat it as a startup failure, not a run result.
 */
export function requireThreadId(agentId: unknown, what = "agent id"): string {
  const reason = badThreadIdReason(agentId, what);
  if (reason === null) return agentId as string;
  throw agentIdError(reason);
}

/**
 * What the loop takes `plan.selfAgentId` to be. The root prompt names the
 * planner's id as `$AMP_THREAD_ID` and tells it to expand that; when the
 * literal lands in plan.json (or an empty string, or anything that is not a
 * thread id) the loop treats the id as unknown rather than passing it on to
 * every child's `parentAgentId`, the Slack footer, and `kill-tree`. A missing
 * key is upstream's "not set" and raises no attention.
 */
export function resolveSelfAgentId(value: unknown): {
  id: string | null;
  attention: string | null;
} {
  if (value === undefined || value === null) return { id: null, attention: null };
  if (isThreadId(value)) return { id: value, attention: null };
  const why = isPendingAgentId(value)
    ? `plan.selfAgentId is the unexpanded placeholder ${PENDING_AGENT_ID}`
    : `plan.selfAgentId ${JSON.stringify(value)} is not an Amp thread id`;
  return {
    id: null,
    attention: `${why}; treating it as unset, so children record parentAgentId: null and kill-tree --agent-id cannot target this planner. Set it to the value of \`echo $AMP_THREAD_ID\` in the root planner's orb.`,
  };
}

function agentIdError(message: string): Error & { isRetryable: boolean } {
  return Object.assign(new Error(message), { name: "AgentRuntimeError", isRetryable: false });
}

// ---------------------------------------------------------------------------
// Operator gates. These read the loop's environment, never plan.json alone,
// because plan.json is written by the root planner (an LLM) and, with
// `syncStateToGit`, by anyone who can push the state branch.
// ---------------------------------------------------------------------------

/**
 * Whether planner-authored `tasks[].measurements[].command` lines may run.
 * They run through `bash -c`, so two parties have to agree: the operator sets
 * `ORCHESTRATE_MEASUREMENTS=1` in the environment of the process that runs the
 * loop, and plan.json sets `"measurementsEnabled": true`. Without the
 * variable the plan's opt-in is inert.
 */
export function measurementGate(args: {
  planOptIn: boolean;
  env?: NodeJS.ProcessEnv;
}): { enabled: true } | { enabled: false; reason: string } {
  const env = args.env ?? process.env;
  const raw = env.ORCHESTRATE_MEASUREMENTS;
  if (raw === undefined || raw === "") {
    return { enabled: false, reason: "ORCHESTRATE_MEASUREMENTS is unset" };
  }
  if (raw !== "1") {
    return { enabled: false, reason: `ORCHESTRATE_MEASUREMENTS is ${JSON.stringify(raw)}, not 1` };
  }
  if (!args.planOptIn) {
    return { enabled: false, reason: 'plan.json does not set "measurementsEnabled": true' };
  }
  return { enabled: true };
}

export type OriginCheck =
  | { kind: "match"; origin: string }
  | { kind: "mismatch"; origin: string; reason: string }
  | { kind: "unknown"; reason: string };

/**
 * Whether `plan.repoUrl` names the repository the operator configured.
 * `ORCHESTRATE_REPO_URL` is the only source of truth: the workspace's
 * `remote.origin.url` is not consulted, because whoever edits plan.json can
 * also run `git remote set-url`. Without the variable the check is `unknown`;
 * callers log that once, let spawns proceed (an orb project is one the
 * signed-in user already has access to), and refuse the measurement clone.
 */
export function checkRepoUrlAgainstOrigin(args: {
  repoUrl: string;
  env?: NodeJS.ProcessEnv;
}): OriginCheck {
  const env = args.env ?? process.env;
  const origin = env.ORCHESTRATE_REPO_URL?.trim() ?? "";
  if (!origin) {
    return { kind: "unknown", reason: "ORCHESTRATE_REPO_URL is unset" };
  }
  const wanted = repoKey(args.repoUrl);
  const configured = repoKey(origin);
  if (!wanted || !configured) {
    return {
      kind: "mismatch",
      origin,
      reason: `could not parse ${!wanted ? args.repoUrl : origin} as a repository URL`,
    };
  }
  if (wanted !== configured) {
    return {
      kind: "mismatch",
      origin,
      reason: `repoUrl ${args.repoUrl} is not the configured origin ${origin}`,
    };
  }
  return { kind: "match", origin };
}

/** `host/owner/repo`, lowercased, for https, ssh, and scp-style remotes; null when unparseable. */
export function repoKey(remote: string): string | null {
  const trimmed = remote.trim();
  if (!trimmed) return null;
  let candidate = trimmed;
  const scp = /^([^@/\s]+)@([^:/\s]+):(.+)$/.exec(trimmed);
  if (scp) candidate = `ssh://${scp[1]}@${scp[2]}/${scp[3]}`;
  let url: URL;
  try {
    url = new URL(candidate);
  } catch {
    try {
      url = new URL(`https://${candidate}`);
    } catch {
      return null;
    }
  }
  if (!url.hostname) return null;
  const path = url.pathname.replace(/\/+$/, "").replace(/\.git$/, "");
  if (!path || path === "/") return null;
  return `${url.hostname.toLowerCase()}${path.toLowerCase()}`;
}

const THREAD_ID_NOTE =
  "Thread id: `$AMP_THREAD_ID` in this prompt is an environment variable your orb sets to this thread's own id. Expand it (`echo $AMP_THREAD_ID`) wherever the prompt uses it, including values you write into plan.json.";

interface RuntimeModule {
  createAmpRuntime: (options?: { env?: NodeJS.ProcessEnv }) => AgentRuntime;
}

interface ModelsModule {
  createAmpModelCatalog: (options?: { env?: NodeJS.ProcessEnv }) => ModelCatalog;
}

function candidateDirs(): string[] {
  const here = dirname(fileURLToPath(import.meta.url));
  const dirs: string[] = [];
  if (process.env.ORCHESTRATE_AMP_RUNTIME_DIR) dirs.push(process.env.ORCHESTRATE_AMP_RUNTIME_DIR);
  // Installed: <skills>/orchestrate/scripts/core -> <skills>/pstack-sync/adapters/amp
  dirs.push(join(here, "..", "..", "..", "pstack-sync", "adapters", "amp"));
  // Pack: pstack-sync/adapters/amp/agent-runtime/scripts/core -> pstack-sync/adapters/amp
  dirs.push(join(here, "..", "..", ".."));
  return dirs;
}

export function resolveRuntimeDir(): string {
  for (const dir of candidateDirs()) {
    if (existsSync(join(dir, "agent-runtime.ts")) && existsSync(join(dir, "models.ts"))) {
      return dir;
    }
  }
  throw new Error(
    `Amp agent runtime not found; looked in ${candidateDirs().join(", ")}. Install pstack-sync beside this skill or set ORCHESTRATE_AMP_RUNTIME_DIR.`
  );
}

let runtimeSingleton: AgentRuntime | undefined;
let catalogSingleton: ModelCatalog | undefined;
let apiSingleton: AgentApi | undefined;

export async function loadRuntime(): Promise<AgentRuntime> {
  if (runtimeSingleton) return runtimeSingleton;
  const dir = resolveRuntimeDir();
  const mod = (await import(pathToFileURL(join(dir, "agent-runtime.ts")).href)) as RuntimeModule;
  runtimeSingleton = mod.createAmpRuntime();
  return runtimeSingleton;
}

export async function loadModelCatalog(): Promise<ModelCatalog> {
  if (catalogSingleton) return catalogSingleton;
  const dir = resolveRuntimeDir();
  const mod = (await import(pathToFileURL(join(dir, "models.ts")).href)) as ModelsModule;
  catalogSingleton = mod.createAmpModelCatalog();
  return catalogSingleton;
}

/** The `Agent` static surface upstream calls, over the Amp runtime. */
export async function loadSDK(): Promise<AgentApi> {
  if (apiSingleton) return apiSingleton;
  apiSingleton = buildAgentApi(await loadRuntime());
  return apiSingleton;
}

/** Test-only: drop the cached runtime and facade. */
export function __resetRuntimeForTests(): void {
  runtimeSingleton = undefined;
  catalogSingleton = undefined;
  apiSingleton = undefined;
}

/** Where a person opens the agent; mirrors `AgentRuntime.agentUrl` without loading it. */
export function agentUrl(agentId: string): string {
  const base = (process.env.ORCHESTRATE_AMP_URL || "https://ampcode.com").replace(/\/$/, "");
  return `${base}/threads/${agentId}`;
}

/** True for the runtime's startup errors (CLI missing, not signed in, no URL printed). */
export function isAgentRuntimeError(err: unknown): err is Error & { isRetryable: boolean } {
  return err instanceof Error && err.name === "AgentRuntimeError";
}

export function buildAgentApi(rt: AgentRuntime): AgentApi {
  return {
    async create(opts: AgentCreateOptions): Promise<SDKAgent> {
      const repo = opts.cloud?.repos?.[0];
      if (!repo?.url) {
        throw new Error("Agent.create needs cloud.repos[0].url; the Amp runtime spawns on a repository");
      }
      return new AmpAgent(rt, {
        name: opts.name ?? "orchestrate",
        repoUrl: repo.url,
        startingRef: repo.startingRef ?? "",
        model: opts.model?.id ?? "inherit",
      });
    },
    async resume(agentId: string): Promise<SDKAgent> {
      requireThreadId(agentId);
      return new AmpAgent(rt, { name: "", repoUrl: "", startingRef: "", model: "inherit" }, agentId);
    },
    async getRun(runId: string, opts: GetRunOptions): Promise<Run> {
      requireThreadId(opts.agentId);
      const snapshot = await rt.getRun(opts.agentId, runId);
      return new AmpRun(rt, opts.agentId, runId, snapshot.status);
    },
    async list(opts: { limit: number }): Promise<{ items: AgentListItem[] }> {
      const items = await rt.list({ limit: opts.limit });
      return {
        items: items.map(item => ({
          id: item.agentId,
          agentId: item.agentId,
          name: item.name,
          createdAt: item.updatedAt,
        })),
      };
    },
    async listRuns(agentId: string): Promise<{ items: RunListItem[] }> {
      const latest = await rt.latestRun(agentId);
      return { items: latest ? [{ id: latest.runId, status: latest.status }] : [] };
    },
  };
}

class AmpAgent implements SDKAgent {
  private threadId: string | null;

  constructor(
    private readonly rt: AgentRuntime,
    private readonly spawnArgs: { name: string; repoUrl: string; startingRef: string; model: string },
    existingId?: string
  ) {
    this.threadId = existingId ?? null;
  }

  get agentId(): string {
    return this.threadId ?? PENDING_AGENT_ID;
  }

  async send(message: string | { text: string }): Promise<Run> {
    const raw = typeof message === "string" ? message : message.text;
    const text = raw.includes(PENDING_AGENT_ID) ? `${raw}\n\n${THREAD_ID_NOTE}` : raw;
    if (this.threadId) {
      const { runId } = await this.rt.sendFollowUp(this.threadId, text);
      return new AmpRun(this.rt, this.threadId, runId, "running");
    }
    const spawned = await this.rt.spawn({ ...this.spawnArgs, prompt: text });
    this.threadId = spawned.agentId;
    return new AmpRun(this.rt, spawned.agentId, spawned.runId, "running");
  }

  async [Symbol.asyncDispose](): Promise<void> {}
}

class AmpRun implements Run {
  private current: RunStatus;

  constructor(
    private readonly rt: AgentRuntime,
    readonly agentId: string,
    readonly id: string,
    status: RunStatus
  ) {
    this.current = status;
  }

  get status(): RunStatus {
    return this.current;
  }

  async *stream(): AsyncIterable<SDKMessage> {
    for await (const event of this.rt.stream({ agentId: this.agentId, runId: this.id })) {
      switch (event.type) {
        case "assistant":
          yield { type: "assistant", message: { content: [{ type: "text", text: event.text }] } };
          break;
        case "tool_call":
          yield { type: "tool_call", name: event.name, status: event.status, call_id: event.callId };
          break;
        case "status":
          this.current = event.status;
          yield event.error === undefined
            ? { type: "status", status: event.status }
            : { type: "status", status: event.status, error: event.error };
          break;
      }
    }
  }

  async wait(): Promise<RunResult> {
    const result = await this.rt.wait({ agentId: this.agentId, runId: this.id });
    this.current = result.status;
    return {
      id: this.id,
      status: result.status === "running" ? "error" : result.status,
      result: result.finalText,
      durationMs: result.durationMs,
      git: { branches: result.branches.map(branch => ({ branch })) },
      model: null,
      ...(result.error === undefined ? {} : { error: result.error }),
    };
  }

  async cancel(): Promise<void> {
    await this.rt.cancel(this.agentId, this.id);
    this.current = "cancelled";
  }

  supports(op: RunOperation): boolean {
    return op !== "conversation";
  }

  unsupportedReason(op: RunOperation): string | undefined {
    return this.supports(op) ? undefined : "the Amp runtime does not replay conversations";
  }
}
