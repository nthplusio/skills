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
      return new AmpAgent(rt, { name: "", repoUrl: "", startingRef: "", model: "inherit" }, agentId);
    },
    async getRun(runId: string, opts: GetRunOptions): Promise<Run> {
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
          yield { type: "status", status: event.status };
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
