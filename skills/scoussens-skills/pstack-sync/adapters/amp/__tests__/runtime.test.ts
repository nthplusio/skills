/**
 * Drives the port's facade (`agent-runtime/scripts/core/runtime.ts`), the
 * SDK-shaped `Agent` surface upstream calls, over the real runtime and the
 * fake `amp` on PATH. The facade's type-only imports name the installed
 * layout; bun erases them, so the pack layout runs here.
 */
import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { chmodSync, existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createAmpRuntime, type ThreadExport } from "../agent-runtime.ts";
import {
  buildAgentApi,
  isAgentRuntimeError,
  PENDING_AGENT_ID,
  requireThreadId,
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
