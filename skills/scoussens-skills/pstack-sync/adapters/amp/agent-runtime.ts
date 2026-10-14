/**
 * `AgentRuntime` over the `amp` CLI. One agent is one Amp thread running in
 * an orb; one run is one user turn in that thread.
 *
 * Operation to command, as `.amp/in/artifacts/orchestrate-sync/prototype-roundtrip.log`
 * proved them:
 *
 *   spawn         amp -ox --project <repoUrl> --visibility private
 *                     --no-archive-after-execute --title <name> [-m <mode>]
 *                 with the prompt on stdin; the thread id comes from the URL
 *                 the command prints.
 *   getRun, wait  amp threads export <id>, polled; the run is terminal when
 *                 `meta.lastKnownAgentState.state` is idle and the last
 *                 message is an assistant message after the run's start.
 *   stream        the same export, polled, diffed against what was yielded.
 *   cancel        amp threads archive <id>
 *   sendFollowUp  amp threads continue <id> -ox, with the text on stdin
 *   list          amp threads list --json --limit <n>
 *   agentUrl      https://ampcode.com/threads/<id>
 *
 * Run ids are `m<index>`: the index of the user message that started the
 * run in the thread's message list (`m0` for the spawn). Every number here
 * is overridable through environment variables so tests can run a fake
 * `amp` fast; see `readRuntimeOptionsFromEnv`.
 */

import { spawn as spawnProcess } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";
import {
  type AgentRuntime,
  AgentRuntimeError,
  type AgentSummary,
  type LatestRun,
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
  cwd?: string;
  env?: NodeJS.ProcessEnv;
}

const DEFAULTS = {
  bin: "amp",
  pollMs: 10_000,
  maxConsecutiveFailures: 30,
  archivedCheckMs: 60_000,
  visibility: "private",
  label: "orchestrate",
  url: "https://ampcode.com",
  commandTimeoutMs: 180_000,
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
  return {
    bin: env.ORCHESTRATE_AMP_BIN || undefined,
    pollMs: num("ORCHESTRATE_AMP_POLL_MS"),
    maxConsecutiveFailures: num("ORCHESTRATE_AMP_MAX_EXPORT_FAILURES"),
    archivedCheckMs: num("ORCHESTRATE_AMP_ARCHIVED_CHECK_MS"),
    visibility: env.ORCHESTRATE_AMP_VISIBILITY || undefined,
    label: env.ORCHESTRATE_AMP_LABEL === undefined ? undefined : env.ORCHESTRATE_AMP_LABEL,
    url: env.ORCHESTRATE_AMP_URL || undefined,
    commandTimeoutMs: num("ORCHESTRATE_AMP_COMMAND_TIMEOUT_MS"),
  };
}

export const THREAD_ID_RE = /T-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
const TITLE_MAX_CHARS = 100;

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

function isUserTextMessage(message: ExportMessage): boolean {
  return (
    message.role === "user" &&
    (message.content ?? []).some(b => b.type === "text")
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
  const base = { finalText, branches, durationMs, messageCount: messages.length };

  if (exp.meta?.deleted === true || exp.meta?.archived === true) {
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
  if (state === "idle" && last?.role === "assistant" && lastIndex > start && finalText) {
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
  const cancelledHere = new Set<string>();

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
    const result = await amp(["threads", "export", agentId], { timeoutMs: 60_000 });
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
        ["threads", "search", `id:${agentId} archived:true`, "--json"],
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

  /**
   * Poll exports until `onExport` returns a value. Transient export failures
   * are tolerated up to `maxConsecutiveFailures` in a row; the thread keeps
   * running on the server while the local view is dark, so giving up early
   * would lose a live run.
   */
  async function pollExports<T>(
    run: RunHandle,
    onExport: (exp: ThreadExport, failedBefore: boolean) => T | undefined
  ): Promise<T> {
    let failures = 0;
    let lastArchivedCheck = Date.now();
    let failedBefore = false;
    while (true) {
      if (cancelledHere.has(run.agentId)) {
        const value = onExport(
          { id: run.agentId, messages: [], meta: { archived: true } },
          failedBefore
        );
        if (value !== undefined) return value;
      }
      let exp: ThreadExport | null = null;
      try {
        exp = await exportThread(run.agentId);
        failures = 0;
      } catch (err) {
        failures++;
        if (failures >= cfg.maxConsecutiveFailures) {
          throw new AgentRuntimeError(
            `amp threads export ${run.agentId} failed ${failures} times in a row: ${errorMessage(err)}`,
            { isRetryable: true, cause: err }
          );
        }
        failedBefore = true;
      }
      if (exp) {
        if (
          Date.now() - lastArchivedCheck >= cfg.archivedCheckMs &&
          describeRun(exp, run.runId).status === "running"
        ) {
          lastArchivedCheck = Date.now();
          if (await isArchivedElsewhere(run.agentId)) {
            exp = { ...exp, meta: { ...(exp.meta ?? {}), archived: true } };
          }
        }
        const value = onExport(exp, failedBefore);
        if (value !== undefined) return value;
        failedBefore = false;
      }
      await sleep(cfg.pollMs);
    }
  }

  const runtime: AgentRuntime = {
    async spawn(args: SpawnArgs): Promise<SpawnResult> {
      const argv = [
        "-ox",
        "--project",
        args.repoUrl,
        "--visibility",
        cfg.visibility,
        "--no-archive-after-execute",
        "--title",
        titleFor(args.name),
      ];
      if (cfg.label) argv.push("-l", cfg.label);
      if (args.model && args.model !== "inherit") argv.push("-m", args.model);
      const prompt = withStartingRef(args.prompt, args.startingRef);
      const result = await amp(argv, { stdin: prompt });
      if (result.code !== 0) throw failure("amp -ox", result);
      const match = THREAD_ID_RE.exec(result.stdout);
      if (!match) {
        throw new AgentRuntimeError(
          `amp -ox printed no thread URL: ${truncate(result.stdout.trim() || result.stderr.trim(), 200)}`,
          { isRetryable: true }
        );
      }
      return { agentId: match[0], runId: formatRunId(0) };
    },

    async getRun(agentId: string, runId: string): Promise<RunSnapshot> {
      if (cancelledHere.has(agentId)) return { status: "cancelled" };
      const exp = await exportThread(agentId);
      return { status: describeRun(exp, runId).status };
    },

    async wait(run: RunHandle): Promise<WaitResult> {
      return pollExports(run, exp => {
        const d = describeRun(exp, run.runId);
        if (d.status === "running") return undefined;
        return {
          status: d.status,
          finalText: d.finalText,
          branches: d.branches,
          durationMs: d.durationMs,
        };
      });
    },

    async *stream(run: RunHandle): AsyncIterable<StreamEvent> {
      const start = parseRunId(run.runId);
      // Per message index: the first block not fully yielded and, when that
      // block is text still growing, how much of it went out already.
      const yielded = new Map<number, { next: number; partialLen: number }>();
      let failures = 0;
      while (true) {
        let exp: ThreadExport | null = null;
        if (cancelledHere.has(run.agentId)) {
          exp = { id: run.agentId, messages: [], meta: { archived: true } };
        } else {
          try {
            exp = await exportThread(run.agentId);
            failures = 0;
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
          const d = describeRun(exp, run.runId);
          if (d.status !== "running") {
            yield { type: "status", status: d.status };
            return;
          }
        }
        await sleep(cfg.pollMs);
      }
    },

    async cancel(agentId: string, _runId: string): Promise<void> {
      const result = await amp(["threads", "archive", agentId], { timeoutMs: 60_000 });
      if (result.code !== 0) throw failure(`amp threads archive ${agentId}`, result);
      cancelledHere.add(agentId);
    },

    async list(args: { limit: number }): Promise<AgentSummary[]> {
      const result = await amp(
        ["threads", "list", "--json", "--limit", String(Math.max(1, args.limit))],
        { timeoutMs: 60_000 }
      );
      if (result.code !== 0) throw failure("amp threads list", result);
      let parsed: unknown;
      try {
        parsed = JSON.parse(result.stdout);
      } catch (err) {
        throw new AgentRuntimeError("amp threads list returned non-JSON output", {
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
      const before = await exportThread(agentId);
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

function titleFor(name: string): string {
  const trimmed = name.trim().replace(/\s+/g, " ");
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
