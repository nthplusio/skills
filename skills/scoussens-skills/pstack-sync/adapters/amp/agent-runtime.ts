/**
 * `AgentRuntime` over the `amp` CLI. One agent is one Amp thread running in
 * an orb; one run is one user turn in that thread.
 *
 * Operation to command, as `.amp/in/artifacts/orchestrate-sync/prototype-roundtrip.log`
 * proved them:
 *
 *   spawn         POST to the bridge plugin named by `.orchestrate/bridge.json`
 *                 when that file exists and the bridge answers, so the thread
 *                 nests under the calling thread; otherwise
 *                 amp -ox --project <repoUrl> --visibility private
 *                     --no-archive-after-execute --title <title> [-m <mode>]
 *                 with the prompt on stdin and the thread id from the URL the
 *                 command prints, then amp threads label <id> <labels...>.
 *                 The first wait or stream poll that sees a message renames
 *                 the thread when its title is not the one asked for.
 *   getRun, wait  amp threads export <id>, polled; the run is terminal when
 *                 `meta.lastKnownAgentState.state` is idle and the last
 *                 message is an assistant message after the run's start.
 *                 When that message has no `## Status` or `## Verification`
 *                 section, wait and stream keep polling for a grace period
 *                 (`handoffGraceMs`) so a later turn can produce the handoff.
 *   stream        the same export, polled, diffed against what was yielded.
 *   cancel        amp threads archive <id>; the run reads as cancelled
 *   archive       amp threads archive <id>; a finished run still reads as finished
 *   label, rename amp threads label <id> <labels...>, amp threads rename <id> <title>
 *   sendFollowUp  amp threads continue <id> -ox, with the text on stdin
 *   list          amp threads list --json --limit <n>; with labels,
 *                 amp threads search "label:<a> label:<b> archived:false" --json --limit <n>
 *   agentUrl      https://ampcode.com/threads/<id>
 *
 * Run ids are `m<index>`: the index of the user message that started the
 * run in the thread's message list (`m0` for the spawn). Every number here
 * is overridable through environment variables so tests can run a fake
 * `amp` fast; see `readRuntimeOptionsFromEnv`.
 */

import { spawn as spawnProcess } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { setTimeout as sleep } from "node:timers/promises";
import {
  type AgentRuntime,
  AgentRuntimeError,
  type AgentSummary,
  type LatestRun,
  type NodeType,
  type RunHandle,
  type RunSnapshot,
  type RunStatus,
  type SpawnArgs,
  type SpawnResult,
  type StreamEvent,
  type WaitResult,
} from "../interface.ts";

export interface AmpRuntimeOptions {
  /** CLI binary; `ORCHESTRATE_AMP_BIN`, default `amp`. */
  bin?: string;
  /** Poll interval for wait and stream; `ORCHESTRATE_AMP_POLL_MS`, default 10 s. */
  pollMs?: number;
  /** Consecutive failed exports tolerated before wait or stream throws; `ORCHESTRATE_AMP_MAX_EXPORT_FAILURES`, default 30. */
  maxConsecutiveFailures?: number;
  /** How often wait checks whether another process archived the thread; `ORCHESTRATE_AMP_ARCHIVED_CHECK_MS`, default 60 s. */
  archivedCheckMs?: number;
  /** Thread visibility; `ORCHESTRATE_AMP_VISIBILITY`, default `private`. */
  visibility?: string;
  /** Label put on every spawned thread; `ORCHESTRATE_AMP_LABEL`, default `orchestrate`; empty disables. */
  label?: string;
  /** Web origin for `agentUrl`; `ORCHESTRATE_AMP_URL`, default `https://ampcode.com`. */
  url?: string;
  /** Wall-time cap for one CLI invocation; `ORCHESTRATE_AMP_COMMAND_TIMEOUT_MS`, default 180 s. */
  commandTimeoutMs?: number;
  /** Longest `wait` or `stream` keeps polling a run that has not ended; `ORCHESTRATE_WAIT_TIMEOUT_SEC`, default 7200 s. */
  waitTimeoutSec?: number;
  /**
   * How long `wait` and `stream` keep polling after a turn ends idle without a
   * `## Status` or `## Verification` section, so a later turn can produce the
   * handoff before the run reads as finished; `ORCHESTRATE_AMP_HANDOFF_GRACE_MS`,
   * default 120 s, `0` disables.
   */
  handoffGraceMs?: number;
  /** Where lines that deserve a person's attention go when no run can carry them (a rename or label that failed); default stderr. */
  onAttention?: (line: string) => void;
  /** Working directory for CLI invocations and the second place the bridge file is looked for. */
  cwd?: string;
  env?: NodeJS.ProcessEnv;
}

/** The grace window's default: long enough for a thread to start and finish one more turn. */
export const DEFAULT_HANDOFF_GRACE_MS = 120_000;

const DEFAULTS = {
  bin: "amp",
  pollMs: 10_000,
  maxConsecutiveFailures: 30,
  archivedCheckMs: 60_000,
  visibility: "private",
  label: "orchestrate",
  url: "https://ampcode.com",
  commandTimeoutMs: 180_000,
  waitTimeoutSec: 7_200,
  handoffGraceMs: DEFAULT_HANDOFF_GRACE_MS,
};

export function readRuntimeOptionsFromEnv(
  env: NodeJS.ProcessEnv = process.env
): AmpRuntimeOptions {
  const num = (key: string): number | undefined => {
    const raw = env[key];
    if (!raw) return undefined;
    const n = Number.parseInt(raw, 10);
    return Number.isFinite(n) && n > 0 ? n : undefined;
  };
  // Zero is a value here: it turns the grace window off.
  const nonNegative = (key: string): number | undefined => {
    const raw = env[key];
    if (raw === undefined || raw.trim() === "") return undefined;
    const n = Number.parseInt(raw, 10);
    return Number.isFinite(n) && n >= 0 ? n : undefined;
  };
  return {
    bin: env.ORCHESTRATE_AMP_BIN || undefined,
    pollMs: num("ORCHESTRATE_AMP_POLL_MS"),
    maxConsecutiveFailures: num("ORCHESTRATE_AMP_MAX_EXPORT_FAILURES"),
    archivedCheckMs: num("ORCHESTRATE_AMP_ARCHIVED_CHECK_MS"),
    visibility: env.ORCHESTRATE_AMP_VISIBILITY || undefined,
    label: env.ORCHESTRATE_AMP_LABEL === undefined ? undefined : env.ORCHESTRATE_AMP_LABEL,
    url: env.ORCHESTRATE_AMP_URL || undefined,
    commandTimeoutMs: num("ORCHESTRATE_AMP_COMMAND_TIMEOUT_MS"),
    waitTimeoutSec: num("ORCHESTRATE_WAIT_TIMEOUT_SEC"),
    handoffGraceMs: nonNegative("ORCHESTRATE_AMP_HANDOFF_GRACE_MS"),
  };
}

export const THREAD_ID_RE = /T-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
const THREAD_ID_EXACT_RE = new RegExp(`^${THREAD_ID_RE.source}$`, "i");
const RUN_ID_RE = /^m\d+$/;
const TITLE_MAX_CHARS = 100;
/** What `amp threads label` accepts, as probed: alphanumeric with hyphens, starting alphanumeric. */
export const LABEL_RE = /^[A-Za-z0-9][A-Za-z0-9-]*$/;
/** The mode the bridge runs when the caller says `inherit`. */
export const BRIDGE_DEFAULT_MODE = "high";

/**
 * The label a spawn's `nodeType` becomes, the same one the bridge plugin
 * derives from the field: `node-planner`, `node-worker`, and so on. The
 * runtime adds it on both spawn paths, so a run looks the same whichever
 * created its threads and whether or not the bridge knows the field.
 */
export function nodeTypeLabel(nodeType: NodeType): string {
  return `node-${nodeType}`;
}

/** True for a whole Amp thread id and nothing else. */
export function isThreadId(value: string): boolean {
  return THREAD_ID_EXACT_RE.test(value);
}

/**
 * Agent ids come from `state.json`, which is git-synced, and from `--agent-id`
 * flags, and they land in `amp` argv. Anything that is not a whole thread id
 * is refused before a process starts, so `--last` or `--help` cannot change
 * which thread a command touches or what it does.
 */
export function threadIdArg(agentId: string): string {
  if (typeof agentId !== "string" || !isThreadId(agentId)) {
    throw new AgentRuntimeError(
      `refusing to pass ${JSON.stringify(agentId)} to amp: not an Amp thread id`
    );
  }
  return agentId;
}

function runIdArg(runId: string): string {
  if (typeof runId !== "string" || !RUN_ID_RE.test(runId)) {
    throw new AgentRuntimeError(
      `refusing run id ${JSON.stringify(runId)}: the Amp runtime names runs m<message-index>`
    );
  }
  return runId;
}

/** True for a label the CLI accepts and nothing else. */
export function isLabel(value: string): boolean {
  return typeof value === "string" && LABEL_RE.test(value);
}

/**
 * Labels land in `amp threads label <id> <labels...>` argv and in the bridge
 * request, so anything outside the CLI's own pattern is refused before a
 * process starts: `--help` cannot become a flag. Duplicates are dropped.
 */
export function labelArgs(labels: readonly string[]): string[] {
  const out: string[] = [];
  for (const label of labels) {
    if (!isLabel(label)) {
      throw new AgentRuntimeError(
        `refusing label ${JSON.stringify(label)}: Amp labels match ${LABEL_RE.source}`
      );
    }
    if (!out.includes(label)) out.push(label);
  }
  return out;
}

// ---------------------------------------------------------------------------
// The bridge file. The orchestrate-bridge plugin writes it when a thread
// starts, so a spawn can nest under that thread. Exported for tests.
// ---------------------------------------------------------------------------

export interface BridgeFile {
  url: string;
  token: string;
  thread?: string;
  startedAt?: string;
}

/** Where the bridge file is looked for, in order; the first that exists wins. */
export function bridgeCandidates(env: NodeJS.ProcessEnv, cwd: string): string[] {
  if (env.ORCHESTRATE_AMP_BRIDGE) return [env.ORCHESTRATE_AMP_BRIDGE];
  const out = [join(cwd, ".orchestrate", "bridge.json")];
  if (env.AMP_WORKING_DIRECTORY) {
    out.push(join(env.AMP_WORKING_DIRECTORY, ".orchestrate", "bridge.json"));
  }
  return out;
}

const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "[::1]", "::1"]);

/**
 * The bridge serves on loopback. A file naming any other host is ignored,
 * because the request carries the task prompt and the file's token, and the
 * file sits in a working directory that git can write.
 */
export function isLoopbackUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return (
      (parsed.protocol === "http:" || parsed.protocol === "https:") &&
      LOOPBACK_HOSTS.has(parsed.hostname.toLowerCase())
    );
  } catch {
    return false;
  }
}

export type BridgeLookup =
  | { kind: "found"; path: string; bridge: BridgeFile }
  | { kind: "missing"; reason: string };

export function readBridgeFile(env: NodeJS.ProcessEnv, cwd: string): BridgeLookup {
  const candidates = bridgeCandidates(env, cwd);
  for (const path of candidates) {
    if (!existsSync(path)) continue;
    let parsed: unknown;
    try {
      parsed = JSON.parse(readFileSync(path, "utf8"));
    } catch (err) {
      return { kind: "missing", reason: `bridge file ${path} is not JSON: ${errorMessage(err)}` };
    }
    const rec = (typeof parsed === "object" && parsed !== null ? parsed : {}) as Record<string, unknown>;
    if (typeof rec.url !== "string" || !rec.url || typeof rec.token !== "string" || !rec.token) {
      return { kind: "missing", reason: `bridge file ${path} has no url and token` };
    }
    if (!isLoopbackUrl(rec.url)) {
      return { kind: "missing", reason: `bridge file ${path} names ${rec.url}, which is not a loopback address` };
    }
    return {
      kind: "found",
      path,
      bridge: {
        url: rec.url,
        token: rec.token,
        thread: typeof rec.thread === "string" ? rec.thread : undefined,
        startedAt: typeof rec.startedAt === "string" ? rec.startedAt : undefined,
      },
    };
  }
  return { kind: "missing", reason: `no bridge file at ${candidates.join(" or ")}` };
}

// ---------------------------------------------------------------------------
// Export parsing. Exported for tests and for the port's facade.
// ---------------------------------------------------------------------------

export interface ExportBlock {
  type?: string;
  text?: string;
  name?: string;
  id?: string;
}

export interface ExportMessage {
  role?: string;
  content?: ExportBlock[];
  createdAt?: string;
  state?: { type?: string; stopReason?: string } | null;
}

export interface ThreadExport {
  id?: string;
  title?: string;
  messages?: ExportMessage[];
  meta?: {
    lastKnownAgentState?: { state?: string } | null;
    deleted?: boolean;
    archived?: boolean | null;
  };
}

export interface RunDescription {
  status: RunStatus;
  finalText: string;
  branches: string[];
  durationMs: number | null;
  /** Index of the last message considered, for stream cursors. */
  messageCount: number;
  /** Whether `finalText` carries a handoff section; see `hasHandoffSection`. */
  hasHandoff: boolean;
}

export function parseRunId(runId: string): number {
  const match = /^m(\d+)$/.exec(runId);
  return match ? Number.parseInt(match[1], 10) : 0;
}

export function formatRunId(messageIndex: number): string {
  return `m${messageIndex}`;
}

export function messageText(message: ExportMessage | undefined): string {
  if (!message?.content) return "";
  return message.content
    .filter(b => b.type === "text" && typeof b.text === "string")
    .map(b => b.text as string)
    .join("\n");
}

/**
 * Amp inserts user-role messages of its own, such as the
 * `<integration_hint integration="slack">` block after a prompt. They are not
 * turns anyone sent, so they do not start a run.
 */
function isInjectedUserMessage(message: ExportMessage): boolean {
  return messageText(message).trimStart().startsWith("<integration_hint");
}

function isUserTextMessage(message: ExportMessage): boolean {
  return (
    message.role === "user" &&
    (message.content ?? []).some(b => b.type === "text") &&
    !isInjectedUserMessage(message)
  );
}

/** Index of the user message that started the thread's latest run. */
export function latestRunStart(exp: ThreadExport): number | null {
  const messages = exp.messages ?? [];
  for (let i = messages.length - 1; i >= 0; i--) {
    if (isUserTextMessage(messages[i])) return i;
  }
  return null;
}

/** The `## Branch` line of a handoff body, or nothing. */
export function parseBranchLine(body: string): string[] {
  const match = /^##\s+Branch\s*\r?\n([^\r\n]*)/m.exec(body);
  if (!match) return [];
  const raw = match[1].trim().replace(/^`([^`]+)`$/, "$1").trim();
  if (!raw || raw.startsWith("##") || /^\(no branch\)$/i.test(raw)) return [];
  return [raw];
}

/**
 * The same test as upstream's `hasStructuredHandoff` in `core/failure-handoff.ts`:
 * a handoff opens a `## Status` (or, for a verifier, `## Verification`)
 * section. A turn that ends without one is a progress message, not a handoff.
 */
export function hasHandoffSection(body: string): boolean {
  return /^##\s+(Status|Verification)\s*$/m.test(body);
}

function agentState(exp: ThreadExport): string {
  return (exp.meta?.lastKnownAgentState?.state ?? "").toLowerCase();
}

export function describeRun(exp: ThreadExport, runId: string): RunDescription {
  const messages = exp.messages ?? [];
  const start = Math.min(parseRunId(runId), Math.max(messages.length - 1, 0));
  const state = agentState(exp);
  const last = messages.length > 0 ? messages[messages.length - 1] : undefined;
  const lastIndex = messages.length - 1;

  let lastAssistant: ExportMessage | undefined;
  for (let i = lastIndex; i > start; i--) {
    if (messages[i].role === "assistant" && messageText(messages[i])) {
      lastAssistant = messages[i];
      break;
    }
  }
  const finalText = messageText(lastAssistant).trim();
  const branches = parseBranchLine(finalText);
  const startedAt = Date.parse(messages[start]?.createdAt ?? "");
  const endedAt = Date.parse(lastAssistant?.createdAt ?? "");
  const durationMs =
    Number.isFinite(startedAt) && Number.isFinite(endedAt) && endedAt >= startedAt
      ? endedAt - startedAt
      : null;
  const base = {
    finalText,
    branches,
    durationMs,
    messageCount: messages.length,
    hasHandoff: hasHandoffSection(finalText),
  };

  if (exp.meta?.deleted === true) {
    return { status: "cancelled", ...base };
  }
  const stopType = (last?.state?.type ?? "").toLowerCase();
  if (last?.role === "assistant" && lastIndex > start) {
    if (stopType === "cancelled" || stopType === "canceled") {
      return { status: "cancelled", ...base };
    }
    if (stopType === "error" || stopType === "failed") {
      return { status: "error", ...base };
    }
  }
  // Only `idle` ends a run. The agent state has been seen as working,
  // streaming, and running_tools while a turn is in flight, and an unknown
  // or missing state is treated the same way rather than as finished.
  const idleReply =
    state === "idle" && last?.role === "assistant" && lastIndex > start && finalText.length > 0;
  // An archived thread still exports. One archived after its reply (the loop
  // archives workers right after their handoff) is finished; one archived
  // mid-turn, by `cancel` or another process, is cancelled.
  if (exp.meta?.archived === true) {
    return { status: idleReply ? "finished" : "cancelled", ...base };
  }
  if (idleReply) {
    return { status: "finished", ...base };
  }
  if (state === "error" || state === "failed") {
    return { status: "error", ...base };
  }
  return { status: "running", ...base };
}

// ---------------------------------------------------------------------------
// The runtime
// ---------------------------------------------------------------------------

interface CommandResult {
  code: number | null;
  stdout: string;
  stderr: string;
}

export function createAmpRuntime(options: AmpRuntimeOptions = {}): AgentRuntime {
  const fromEnv = readRuntimeOptionsFromEnv(options.env ?? process.env);
  const cfg = {
    ...DEFAULTS,
    ...stripUndefined(fromEnv),
    ...stripUndefined(options),
  };
  const env = options.env ?? process.env;
  const cwd = options.cwd ?? process.cwd();
  const attention =
    options.onAttention ?? ((line: string) => console.error(`[amp-runtime] ${line}`));
  const cancelledHere = new Set<string>();
  // Threads spawned through the bridge get their title from the first poll
  // that sees a message; a CLI spawn sets it with --title. Either way the
  // rename runs once, only when the export's title is not the one wanted.
  const pendingTitles = new Map<string, string>();

  async function amp(
    args: string[],
    opts: { stdin?: string; timeoutMs?: number } = {}
  ): Promise<CommandResult> {
    return new Promise<CommandResult>((resolvePromise, rejectPromise) => {
      let child: ReturnType<typeof spawnProcess>;
      try {
        child = spawnProcess(cfg.bin, args, {
          cwd: options.cwd,
          env,
          stdio: [opts.stdin === undefined ? "ignore" : "pipe", "pipe", "pipe"],
        });
      } catch (err) {
        rejectPromise(
          new AgentRuntimeError(`could not start ${cfg.bin}: ${errorMessage(err)}`, {
            cause: err,
          })
        );
        return;
      }
      let stdout = "";
      let stderr = "";
      const timeoutMs = opts.timeoutMs ?? cfg.commandTimeoutMs;
      const timer = setTimeout(() => {
        child.kill("SIGKILL");
        rejectPromise(
          new AgentRuntimeError(
            `${cfg.bin} ${args.slice(0, 3).join(" ")} timed out after ${timeoutMs}ms`,
            { isRetryable: true }
          )
        );
      }, timeoutMs);
      child.stdout?.setEncoding("utf8");
      child.stderr?.setEncoding("utf8");
      child.stdout?.on("data", chunk => {
        stdout += chunk;
      });
      child.stderr?.on("data", chunk => {
        stderr += chunk;
      });
      child.on("error", err => {
        clearTimeout(timer);
        rejectPromise(
          new AgentRuntimeError(`could not run ${cfg.bin}: ${errorMessage(err)}`, {
            cause: err,
          })
        );
      });
      child.on("close", code => {
        clearTimeout(timer);
        resolvePromise({ code, stdout, stderr });
      });
      if (opts.stdin !== undefined) {
        child.stdin?.on("error", () => {});
        child.stdin?.end(opts.stdin);
      }
    });
  }

  function failure(what: string, result: CommandResult): AgentRuntimeError {
    const detail = (result.stderr || result.stdout).trim().split("\n").slice(-3).join(" | ");
    return new AgentRuntimeError(
      `${what} failed (exit ${result.code ?? "signal"})${detail ? `: ${detail}` : ""}`,
      { isRetryable: true }
    );
  }

  async function exportThread(agentId: string): Promise<ThreadExport> {
    const result = await amp(["threads", "export", threadIdArg(agentId)], { timeoutMs: 60_000 });
    if (result.code !== 0) throw failure(`amp threads export ${agentId}`, result);
    try {
      return JSON.parse(result.stdout) as ThreadExport;
    } catch (err) {
      throw new AgentRuntimeError(
        `amp threads export ${agentId} returned non-JSON output`,
        { isRetryable: true, cause: err }
      );
    }
  }

  async function isArchivedElsewhere(agentId: string): Promise<boolean> {
    try {
      const result = await amp(
        ["threads", "search", `id:${threadIdArg(agentId)} archived:true`, "--json"],
        { timeoutMs: 60_000 }
      );
      if (result.code !== 0) return false;
      const parsed = JSON.parse(result.stdout) as unknown;
      return (
        Array.isArray(parsed) &&
        parsed.some(
          item =>
            typeof item === "object" &&
            item !== null &&
            (item as { id?: string }).id === agentId
        )
      );
    } catch {
      return false;
    }
  }

  async function spawnViaBridge(
    bridge: BridgeFile,
    body: {
      name: string;
      prompt: string;
      project: string;
      mode: string;
      labels: string[];
      nodeType?: NodeType;
    }
  ): Promise<string> {
    let response: Response;
    try {
      response = await fetch(bridge.url, {
        method: "POST",
        headers: {
          authorization: `Bearer ${bridge.token}`,
          "content-type": "application/json",
        },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(cfg.commandTimeoutMs),
      });
    } catch (err) {
      throw new Error(`request to ${bridge.url} failed: ${errorMessage(err)}`);
    }
    const text = await response.text();
    let parsed: unknown = null;
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = null;
    }
    const rec = (typeof parsed === "object" && parsed !== null ? parsed : {}) as Record<string, unknown>;
    if (response.status !== 200) {
      const reason = typeof rec.error === "string" ? rec.error : truncate(text.trim(), 200);
      throw new Error(`${bridge.url} answered ${response.status}${reason ? `: ${reason}` : ""}`);
    }
    if (typeof rec.threadID !== "string" || !isThreadId(rec.threadID)) {
      throw new Error(`${bridge.url} answered 200 without a thread id`);
    }
    return rec.threadID;
  }

  /** The one rename a spawned thread gets; a failure is one attention line, never a run status. */
  async function applyPendingTitle(agentId: string, exp: ThreadExport): Promise<void> {
    const title = pendingTitles.get(agentId);
    if (title === undefined || (exp.messages ?? []).length === 0) return;
    pendingTitles.delete(agentId);
    if ((exp.title ?? "").trim() === title) return;
    try {
      await runtime.rename(agentId, title);
    } catch (err) {
      attention(
        `${agentId}: rename to ${JSON.stringify(title)} failed, keeping the thread's own title: ${errorMessage(err)}`
      );
    }
  }

  /**
   * Yield one export per poll, with the status the caller should act on,
   * until the caller stops consuming or the deadline passes. Shared by `wait`
   * and `stream`, so both tolerate up to `maxConsecutiveFailures` failed
   * exports in a row (the thread keeps running on the server while the local
   * view is dark), both notice a thread another process archived, both hold
   * a finished run without a handoff section for `handoffGraceMs` (the third
   * real run had a worker end a turn on a progress message and write the
   * handoff on its next turn, after the loop had already respawned it), and
   * both stop after `waitTimeoutSec` without a terminal state: the final item
   * carries `timedOut: true` and the generator ends.
   */
  async function* pollExports(
    run: RunHandle
  ): AsyncGenerator<{ exp: ThreadExport; status: RunStatus; timedOut: boolean }, void> {
    const startedAt = Date.now();
    const deadlineMs = cfg.waitTimeoutSec * 1000;
    let failures = 0;
    let lastArchivedCheck = startedAt;
    // When the turn that ended without a handoff section was first seen; null
    // while the thread is working, so each such turn gets its own window.
    let graceStartedAt: number | null = null;

    /**
     * A finished run whose final text has no handoff section stays `running`
     * for `handoffGraceMs` from the first poll that saw it, then reads as
     * finished with that text, as before. A thread that resumes a turn in
     * between clears the clock. An archived thread gets no grace: it cannot
     * take another turn.
     */
    function withHandoffGrace(run: RunHandle, exp: ThreadExport, status: RunStatus): RunStatus {
      if (status === "running") {
        graceStartedAt = null;
        return status;
      }
      if (status !== "finished" || cfg.handoffGraceMs <= 0 || exp.meta?.archived === true) {
        return status;
      }
      if (describeRun(exp, run.runId).hasHandoff) return status;
      const graceSec = Math.round(cfg.handoffGraceMs / 1000);
      if (graceStartedAt === null) {
        graceStartedAt = Date.now();
        attention(
          `${run.agentId} ${run.runId}: turn ended idle without a \`## Status\` or \`## Verification\` section; polling up to ${graceSec}s more for a later turn to produce the handoff`
        );
      }
      if (Date.now() - graceStartedAt < cfg.handoffGraceMs) return "running";
      attention(
        `${run.agentId} ${run.runId}: no handoff section after ${graceSec}s of grace; the run reads as finished with its last text`
      );
      graceStartedAt = null;
      return status;
    }

    while (true) {
      let exp: ThreadExport | null = null;
      if (cancelledHere.has(run.agentId)) {
        exp = { id: run.agentId, messages: [], meta: { archived: true } };
      } else {
        try {
          exp = await exportThread(run.agentId);
          failures = 0;
          await applyPendingTitle(run.agentId, exp);
        } catch (err) {
          failures++;
          if (failures >= cfg.maxConsecutiveFailures) {
            throw new AgentRuntimeError(
              `amp threads export ${run.agentId} failed ${failures} times in a row: ${errorMessage(err)}`,
              { isRetryable: true, cause: err }
            );
          }
        }
      }
      if (exp) {
        let status = describeRun(exp, run.runId).status;
        if (status === "running" && Date.now() - lastArchivedCheck >= cfg.archivedCheckMs) {
          lastArchivedCheck = Date.now();
          if (await isArchivedElsewhere(run.agentId)) {
            exp = { ...exp, meta: { ...(exp.meta ?? {}), archived: true } };
            status = describeRun(exp, run.runId).status;
          }
        }
        status = withHandoffGrace(run, exp, status);
        const timedOut = status === "running" && Date.now() - startedAt >= deadlineMs;
        yield { exp, status, timedOut };
        if (timedOut) return;
      }
      await sleep(cfg.pollMs);
    }
  }

  function timeoutMessage(run: RunHandle, exp: ThreadExport): string {
    return `gave up waiting for ${run.agentId} ${run.runId} after ORCHESTRATE_WAIT_TIMEOUT_SEC=${cfg.waitTimeoutSec}s without the thread reaching a terminal state (last agent state: ${agentState(exp) || "unknown"}); it may still be running at ${runtime.agentUrl(run.agentId)}`;
  }

  const runtime: AgentRuntime = {
    async spawn(args: SpawnArgs): Promise<SpawnResult> {
      const labels = labelArgs([
        ...(cfg.label ? [cfg.label] : []),
        ...(args.nodeType ? [nodeTypeLabel(args.nodeType)] : []),
        ...(args.labels ?? []),
      ]);
      const title = titleFor(
        args.title ?? (args.runTag ? `${args.runTag} ${args.name}` : args.name)
      );
      const mode = args.model && args.model !== "inherit" ? args.model : undefined;
      const prompt = withStartingRef(args.prompt, args.startingRef);

      // Bridge first: the thread nests under the thread that wrote the file.
      // Any failure falls back to the CLI, and the result's note says why.
      let note: string | undefined;
      const lookup = readBridgeFile(env, cwd);
      if (lookup.kind === "found") {
        try {
          const agentId = await spawnViaBridge(lookup.bridge, {
            name: args.name,
            prompt,
            project: args.repoUrl,
            mode: mode ?? BRIDGE_DEFAULT_MODE,
            labels,
            ...(args.nodeType === undefined ? {} : { nodeType: args.nodeType }),
          });
          pendingTitles.set(agentId, title);
          return { agentId, runId: formatRunId(0), via: "bridge" };
        } catch (err) {
          note = `bridge at ${lookup.path} refused the spawn, used the CLI: ${errorMessage(err)}`;
        }
      } else {
        note = `used the CLI: ${lookup.reason}`;
      }

      const argv = [
        "-ox",
        "--project",
        args.repoUrl,
        "--visibility",
        cfg.visibility,
        "--no-archive-after-execute",
        "--title",
        title,
      ];
      if (mode) argv.push("-m", mode);
      const result = await amp(argv, { stdin: prompt });
      if (result.code !== 0) throw failure("amp -ox", result);
      const match = THREAD_ID_RE.exec(result.stdout);
      if (!match) {
        throw new AgentRuntimeError(
          `amp -ox printed no thread URL: ${truncate(result.stdout.trim() || result.stderr.trim(), 200)}`,
          { isRetryable: true }
        );
      }
      const agentId = match[0];
      // `-l` on `amp -ox` does not apply; labelling afterwards does. A label
      // failure is hygiene lost, not a spawn lost.
      if (labels.length > 0) {
        try {
          await runtime.label(agentId, labels);
        } catch (err) {
          attention(`${agentId}: labelling ${labels.join(", ")} failed: ${errorMessage(err)}`);
        }
      }
      pendingTitles.set(agentId, title);
      return { agentId, runId: formatRunId(0), via: "cli", note };
    },

    async getRun(agentId: string, runId: string): Promise<RunSnapshot> {
      threadIdArg(agentId);
      runIdArg(runId);
      if (cancelledHere.has(agentId)) return { status: "cancelled" };
      const exp = await exportThread(agentId);
      return { status: describeRun(exp, runId).status };
    },

    async wait(run: RunHandle): Promise<WaitResult> {
      threadIdArg(run.agentId);
      runIdArg(run.runId);
      for await (const { exp, status, timedOut } of pollExports(run)) {
        const d = describeRun(exp, run.runId);
        const base = { finalText: d.finalText, branches: d.branches, durationMs: d.durationMs };
        if (status !== "running") return { status, ...base };
        if (timedOut) return { status: "error", ...base, error: timeoutMessage(run, exp) };
      }
      throw new AgentRuntimeError(`polling ${run.agentId} ended without a result`);
    },

    async *stream(run: RunHandle): AsyncIterable<StreamEvent> {
      threadIdArg(run.agentId);
      const start = parseRunId(runIdArg(run.runId));
      // Per message index: the first block not fully yielded and, when that
      // block is text still growing, how much of it went out already.
      const yielded = new Map<number, { next: number; partialLen: number }>();
      for await (const { exp, status, timedOut } of pollExports(run)) {
        const messages = exp.messages ?? [];
        for (let i = start + 1; i < messages.length; i++) {
          const m = messages[i];
          if (m.role !== "assistant") continue;
          const blocks = m.content ?? [];
          const seen = yielded.get(i) ?? { next: 0, partialLen: 0 };
          for (let j = seen.next; j < blocks.length; j++) {
            const b = blocks[j];
            const isLast = j === blocks.length - 1;
            if (b.type === "text" && typeof b.text === "string") {
              const delta = b.text.slice(j === seen.next ? seen.partialLen : 0);
              if (delta) yield { type: "assistant", text: delta };
              if (isLast) {
                seen.next = j;
                seen.partialLen = b.text.length;
                break;
              }
            } else if (b.type === "tool_use") {
              yield {
                type: "tool_call",
                name: b.name ?? "tool",
                callId: b.id ?? "",
                status: "started",
              };
            }
            seen.next = j + 1;
            seen.partialLen = 0;
          }
          yielded.set(i, seen);
        }
        if (status !== "running") {
          yield { type: "status", status };
          return;
        }
        if (timedOut) {
          yield { type: "status", status: "error", error: timeoutMessage(run, exp) };
          return;
        }
      }
    },

    async cancel(agentId: string, _runId: string): Promise<void> {
      await runtime.archive(agentId);
      cancelledHere.add(agentId);
    },

    async archive(agentId: string): Promise<void> {
      const result = await amp(["threads", "archive", threadIdArg(agentId)], {
        timeoutMs: 60_000,
      });
      if (result.code !== 0) throw failure(`amp threads archive ${agentId}`, result);
    },

    async label(agentId: string, labels: string[]): Promise<void> {
      const id = threadIdArg(agentId);
      const args = labelArgs(labels);
      if (args.length === 0) return;
      const result = await amp(["threads", "label", id, ...args], { timeoutMs: 60_000 });
      if (result.code !== 0) throw failure(`amp threads label ${agentId}`, result);
    },

    async rename(agentId: string, title: string): Promise<void> {
      const id = threadIdArg(agentId);
      const result = await amp(["threads", "rename", id, titleFor(title)], {
        timeoutMs: 60_000,
      });
      if (result.code !== 0) throw failure(`amp threads rename ${agentId}`, result);
    },

    async list(args: { limit: number; labels?: string[] }): Promise<AgentSummary[]> {
      const limit = String(Math.max(1, args.limit));
      const labels = labelArgs(args.labels ?? []);
      // `threads list` cannot filter by label; `threads search` can, and its
      // query is built only from labels that passed the label check.
      const argv =
        labels.length > 0
          ? ["threads", "search", `${labels.map(l => `label:${l}`).join(" ")} archived:false`, "--json", "--limit", limit]
          : ["threads", "list", "--json", "--limit", limit];
      const what = `amp threads ${argv[1]}`;
      const result = await amp(argv, { timeoutMs: 60_000 });
      if (result.code !== 0) throw failure(what, result);
      let parsed: unknown;
      try {
        parsed = JSON.parse(result.stdout);
      } catch (err) {
        throw new AgentRuntimeError(`${what} returned non-JSON output`, {
          isRetryable: true,
          cause: err,
        });
      }
      if (!Array.isArray(parsed)) return [];
      const out: AgentSummary[] = [];
      for (const item of parsed) {
        if (typeof item !== "object" || item === null) continue;
        const rec = item as Record<string, unknown>;
        if (typeof rec.id !== "string") continue;
        out.push({
          agentId: rec.id,
          name: typeof rec.title === "string" ? rec.title : "",
          updatedAt:
            typeof rec.updated === "string"
              ? rec.updated
              : typeof rec.updatedAt === "string"
                ? rec.updatedAt
                : null,
          messageCount: typeof rec.messageCount === "number" ? rec.messageCount : null,
        });
      }
      return out;
    },

    async latestRun(agentId: string): Promise<LatestRun | null> {
      const exp = await exportThread(agentId);
      const start = latestRunStart(exp);
      if (start === null) return null;
      const runId = formatRunId(start);
      const status = cancelledHere.has(agentId)
        ? "cancelled"
        : describeRun(exp, runId).status;
      return { agentId, runId, status };
    },

    async sendFollowUp(agentId: string, text: string): Promise<{ runId: string }> {
      // The new user message lands at the current message count, so read it
      // first; without it the follow-up's run could not be told from the last.
      const before = await exportThread(threadIdArg(agentId));
      const runId = formatRunId((before.messages ?? []).length);
      const result = await amp(["threads", "continue", agentId, "-ox"], { stdin: text });
      if (result.code !== 0) throw failure(`amp threads continue ${agentId}`, result);
      return { runId };
    },

    agentUrl(agentId: string): string {
      return `${cfg.url.replace(/\/$/, "")}/threads/${agentId}`;
    },
  };
  return runtime;
}

/**
 * Orbs open the project's default branch; the loop's `startingRef` is a
 * contract with the worker prompt, so the first instruction moves the
 * checkout there.
 */
export function withStartingRef(prompt: string, startingRef: string): string {
  const ref = startingRef.trim();
  if (!ref) return prompt;
  return `Start from git ref \`${ref}\`: before anything else, run \`git fetch origin ${ref} && git checkout ${ref}\` in the repository checkout, because the orb may have opened the project's default branch.\n\n${prompt}`;
}

/** One line, at most 100 characters, never starting with a dash: it lands in argv after `--title` and after `rename <id>`. */
export function titleFor(name: string): string {
  const trimmed = name.trim().replace(/\s+/g, " ").replace(/^-+/, "");
  const title = trimmed || "orchestrate";
  return title.length > TITLE_MAX_CHARS ? title.slice(0, TITLE_MAX_CHARS) : title;
}

function stripUndefined<T extends object>(obj: T): Partial<T> {
  const out: Partial<T> = {};
  for (const [key, value] of Object.entries(obj)) {
    if (value !== undefined) (out as Record<string, unknown>)[key] = value;
  }
  return out;
}

function truncate(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n)}…` : s;
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
