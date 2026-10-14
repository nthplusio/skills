import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { chmodSync, existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { AgentRuntimeError, type StreamEvent } from "../../interface.ts";
import {
  createAmpRuntime,
  describeRun,
  isThreadId,
  parseBranchLine,
  type ThreadExport,
  withStartingRef,
} from "../agent-runtime.ts";
import { AMP_BUILTIN_MODES, createAmpModelCatalog, pluginModesFrom } from "../models.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const FAKE_DIR = join(HERE, "fake-amp");
const ID = "T-01a13830-78c4-723b-8624-f4b865ca42d8";
const REPO = "https://github.com/nthplusio/skills";

let dir: string;
let env: NodeJS.ProcessEnv;

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "os4-fake-amp-"));
  chmodSync(join(FAKE_DIR, "amp"), 0o755);
  writeFileSync(join(dir, "spawn-id"), ID);
  // The fake is found through PATH, as a real `amp` would be; the runtime's
  // default binary name is what gets resolved.
  env = {
    ...process.env,
    PATH: `${FAKE_DIR}:${process.env.PATH ?? ""}`,
    FAKE_AMP_DIR: dir,
    FAKE_AMP_LOG: join(dir, "calls.log"),
    ORCHESTRATE_AMP_BIN: "",
    ORCHESTRATE_AMP_POLL_MS: "5",
    ORCHESTRATE_AMP_ARCHIVED_CHECK_MS: "3600000",
    ORCHESTRATE_AMP_MAX_EXPORT_FAILURES: "5",
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
    const result = await rt.spawn({
      name: "demo/task-a",
      repoUrl: REPO,
      startingRef: "main",
      model: "inherit",
      prompt: "You are a worker.\n\nDo the thing.",
    });
    expect(result).toEqual({ agentId: ID, runId: "m0" });
    const [call] = calls();
    expect(call[0]).toBe("-ox");
    expect(call).toContain("--project");
    expect(call[call.indexOf("--project") + 1]).toBe(REPO);
    expect(call[call.indexOf("--title") + 1]).toBe("demo/task-a");
    expect(call[call.indexOf("--visibility") + 1]).toBe("private");
    expect(call).toContain("--no-archive-after-execute");
    expect(call).not.toContain("-m");
    const stdin = readFileSync(join(dir, "spawn-stdin.txt"), "utf8");
    expect(stdin.startsWith("Start from git ref `main`")).toBe(true);
    expect(stdin.endsWith("You are a worker.\n\nDo the thing.")).toBe(true);
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
});

describe("sendFollowUp", () => {
  test("continues the thread with the text on stdin and names the new run by message index", async () => {
    serve(ID, 1, FINISHED);
    const rt = createAmpRuntime({ env });
    const result = await rt.sendFollowUp(ID, "Reply with exactly FOLLOWUP-OK.");
    expect(result).toEqual({ runId: "m4" });
    const call = calls().find(c => c[0] === "threads" && c[1] === "continue");
    expect(call).toEqual(["threads", "continue", ID, "-ox"]);
    expect(readFileSync(join(dir, "continue-stdin.txt"), "utf8")).toBe(
      "Reply with exactly FOLLOWUP-OK."
    );
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
