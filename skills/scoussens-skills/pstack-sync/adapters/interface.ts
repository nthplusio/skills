/**
 * The agent runtime seam for ported sets.
 *
 * Upstream `orchestrate` drives its workers through the Cursor SDK. A port
 * replaces those calls with an `AgentRuntime`, one object per harness, so the
 * loop, handoff, state, and Slack logic upstream wrote stays as it is while
 * the harness underneath changes. `adapters/<harness>/agent-runtime.ts`
 * implements this interface; `adapters/<harness>/models.ts` implements
 * `ModelCatalog`.
 *
 * The second half of this module names the types the installed, unported
 * files still import from `@cursor/sdk` (`Run`, `RunResult`, `SDKAgent`,
 * `SDKMessage`, `ModelSelection`, `CursorAgentError`). They are type-only
 * imports, which bun erases, so the installed tree runs without the SDK
 * package. Redirecting one of those import lines here is a one-line change
 * per file; the port's `scripts/core/runtime.ts` re-exports them too.
 */

// ---------------------------------------------------------------------------
// AgentRuntime
// ---------------------------------------------------------------------------

/** Identifies one run of one agent. On Amp the agent is a thread. */
export interface RunHandle {
  agentId: string;
  runId: string;
}

/**
 * Status of a run as the runtime reports it. A queued run that has not
 * produced output yet counts as `running`; only the three terminal states
 * are distinguished.
 */
export type RunStatus = "running" | "finished" | "error" | "cancelled";

/** What the agent is in the orchestrate tree. Informational: the runtime records it and the bridge may use it. */
export type NodeType = "planner" | "subplanner" | "worker" | "verifier";

/** How a spawn reached the harness: through the bridge plugin (nested under the calling thread) or the CLI. */
export type SpawnVia = "bridge" | "cli";

export interface SpawnArgs {
  /** Display name for the agent; the thread title when `title` is unset. */
  name: string;
  /** Repository the agent works in. */
  repoUrl: string;
  /** Git ref the agent starts from. */
  startingRef: string;
  /** Model or agent mode; `inherit` means the runtime's default. */
  model: string;
  /** First message; the whole task brief. */
  prompt: string;
  /** Labels to put on the agent, beside the runtime's own default label. Each must match `[A-Za-z0-9][A-Za-z0-9-]*`. */
  labels?: string[];
  /** Thread title; the runtime sets it at spawn when it can and renames the thread to it once the thread has a message. */
  title?: string;
  nodeType?: NodeType;
  /** The run's tag, so the runtime can name the thread `<runTag> <name>` when `title` is unset. */
  runTag?: string;
}

export interface SpawnResult extends RunHandle {
  via: SpawnVia;
  /** Why the spawn took the path it did when that is worth an attention line (the bridge was skipped or refused). */
  note?: string;
}

export interface RunSnapshot {
  status: RunStatus;
}

export interface WaitResult {
  status: RunStatus;
  /** The last assistant text of the run, verbatim; empty when none. */
  finalText: string;
  /** Branches the run reported; parsed from the final message's `## Branch`. */
  branches: string[];
  /** Wall time from the run's first user message to its last assistant message. */
  durationMs: number | null;
  /** Why the status is `error` when the runtime, not the agent, ended the wait (deadline). */
  error?: string;
}

export type StreamEvent =
  | { type: "assistant"; text: string }
  | { type: "tool_call"; name: string; callId: string; status: string }
  | { type: "status"; status: RunStatus; error?: string };

export interface AgentSummary {
  agentId: string;
  name: string;
  /** ISO timestamp of the agent's last change. */
  updatedAt: string | null;
  messageCount: number | null;
}

export interface LatestRun extends RunHandle {
  status: RunStatus;
}

export interface AgentRuntime {
  /** Start an agent on `repoUrl` at `startingRef` with `prompt` as its first message. */
  spawn(args: SpawnArgs): Promise<SpawnResult>;
  /** One status probe; cheap enough to poll. */
  getRun(agentId: string, runId: string): Promise<RunSnapshot>;
  /** Block until the run is terminal and return its final message. */
  wait(run: RunHandle): Promise<WaitResult>;
  /** Yield assistant text, tool calls, and a final status as they appear. */
  stream(run: RunHandle): AsyncIterable<StreamEvent>;
  /** Stop the run and retire the agent. */
  cancel(agentId: string, runId: string): Promise<void>;
  /** Retire a finished agent without marking its run cancelled; a later `wait` still reads its final message. */
  archive(agentId: string): Promise<void>;
  /** Add labels to an existing agent; each must match the label pattern. */
  label(agentId: string, labels: string[]): Promise<void>;
  /** Retitle an existing agent; fails while the agent has no message yet. */
  rename(agentId: string, title: string): Promise<void>;
  /** Most recent agents, newest first; with `labels`, only unarchived agents carrying every one of them. */
  list(args: { limit: number; labels?: string[] }): Promise<AgentSummary[]>;
  /** The agent's current or last run, or null when it has none. */
  latestRun(agentId: string): Promise<LatestRun | null>;
  /** Send a further message to an existing agent; starts a new run. */
  sendFollowUp(agentId: string, text: string): Promise<{ runId: string }>;
  /** Where a person opens the agent. */
  agentUrl(agentId: string): string;
}

export interface ModelCatalog {
  /** Names a plan may put in `tasks[].model`, `inherit` first. */
  models(): Promise<string[]>;
  /** Whether the runtime accepts `model` without spawning anything. */
  probe(model: string): Promise<boolean>;
}

// ---------------------------------------------------------------------------
// Names the unported files import from `@cursor/sdk`
// ---------------------------------------------------------------------------

/**
 * Thrown when the runtime could not start or reach a run (CLI missing, not
 * signed in, network), as distinct from a run that ran and ended in `error`.
 * `isRetryable` says whether a retry can help.
 */
export class AgentRuntimeError extends Error {
  readonly isRetryable: boolean;
  constructor(message: string, options: { isRetryable?: boolean; cause?: unknown } = {}) {
    super(message, options.cause === undefined ? undefined : { cause: options.cause });
    this.name = "AgentRuntimeError";
    this.isRetryable = options.isRetryable ?? false;
  }
}

/** Upstream's name for the startup error class. */
export { AgentRuntimeError as CursorAgentError };

export interface ModelSelection {
  id: string;
  params?: { id: string; value: string }[];
}

export interface RunResult {
  id: string;
  status: "finished" | "error" | "cancelled";
  /** Final assistant text. */
  result?: string | null;
  durationMs?: number | null;
  git?: { branches?: { branch?: string | null }[] } | null;
  model?: ModelSelection | null;
  error?: string;
}

export type TextBlock = { type: "text"; text: string };
export type ToolUseBlock = { type: "tool_use"; name: string; id?: string };
export type ContentBlock = TextBlock | ToolUseBlock;

export type SDKMessage =
  | { type: "assistant"; message: { content: ContentBlock[] } }
  | { type: "thinking"; text: string }
  | { type: "tool_call"; name: string; status: string; call_id: string }
  | { type: "status"; status: string; error?: string }
  | { type: "task"; text?: string };

export type RunOperation = "stream" | "wait" | "cancel" | "conversation";

export interface Run {
  readonly id: string;
  readonly agentId: string;
  readonly status: RunStatus;
  /** Set on the run a spawn returned: which path created the agent and, when worth noting, why. */
  readonly via?: SpawnVia;
  readonly spawnNote?: string;
  stream(): AsyncIterable<SDKMessage>;
  wait(): Promise<RunResult>;
  cancel(): Promise<void>;
  supports(op: RunOperation): boolean;
  unsupportedReason(op: RunOperation): string | undefined;
}

export interface SDKAgent {
  readonly agentId: string;
  send(message: string | { text: string }): Promise<Run>;
  [Symbol.asyncDispose](): Promise<void>;
}

export interface AgentCreateOptions {
  apiKey?: string;
  name?: string;
  model?: ModelSelection;
  /** Port additions, passed through to `SpawnArgs` by the facade. */
  labels?: string[];
  title?: string;
  nodeType?: NodeType;
  runTag?: string;
  cloud?: {
    repos: { url: string; startingRef?: string }[];
    autoCreatePR?: boolean;
  };
}

export interface GetRunOptions {
  runtime?: "cloud" | "local";
  apiKey?: string;
  agentId: string;
}

export interface AgentListItem {
  id: string;
  agentId: string;
  name: string;
  createdAt: string | null;
}

export interface RunListItem {
  id: string;
  status: RunStatus;
}

/**
 * The static `Agent` surface upstream calls. A port builds one of these over
 * an `AgentRuntime` so files like `agent-manager.ts` keep their call sites.
 */
export interface AgentApi {
  create(opts: AgentCreateOptions): Promise<SDKAgent>;
  resume(agentId: string): Promise<SDKAgent>;
  getRun(runId: string, opts: GetRunOptions): Promise<Run>;
  list(opts: { runtime?: "cloud"; limit: number; labels?: string[] }): Promise<{ items: AgentListItem[] }>;
  listRuns(
    agentId: string,
    opts: { runtime?: "cloud"; limit: number }
  ): Promise<{ items: RunListItem[] }>;
}
