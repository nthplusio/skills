import { describe, expect, test } from "bun:test";
import { createHash } from "node:crypto";
import {
  badThreadIdReason,
  checkRepoUrlAgainstOrigin,
  isPendingAgentId,
  measurementGate,
  repoKey,
  resolveSelfAgentId,
  ROOT_TASK_TITLE,
  runLabels,
  runTagFor,
  runTitle,
  shouldArchiveAfterHandoff,
} from "../agent-runtime/scripts/core/runtime.ts";

const REPO = "https://github.com/nthplusio/skills";

describe("measurementGate", () => {
  test("is off without ORCHESTRATE_MEASUREMENTS, whatever plan.json says", () => {
    expect(measurementGate({ planOptIn: true, env: {} })).toEqual({
      enabled: false,
      reason: "ORCHESTRATE_MEASUREMENTS is unset",
    });
    expect(measurementGate({ planOptIn: true, env: { ORCHESTRATE_MEASUREMENTS: "" } })).toEqual({
      enabled: false,
      reason: "ORCHESTRATE_MEASUREMENTS is unset",
    });
  });

  test("needs the operator's 1 and the plan's opt-in together", () => {
    expect(measurementGate({ planOptIn: false, env: { ORCHESTRATE_MEASUREMENTS: "1" } })).toEqual({
      enabled: false,
      reason: 'plan.json does not set "measurementsEnabled": true',
    });
    expect(measurementGate({ planOptIn: true, env: { ORCHESTRATE_MEASUREMENTS: "true" } })).toEqual({
      enabled: false,
      reason: 'ORCHESTRATE_MEASUREMENTS is "true", not 1',
    });
    expect(measurementGate({ planOptIn: true, env: { ORCHESTRATE_MEASUREMENTS: "1" } })).toEqual({
      enabled: true,
    });
  });
});

describe("checkRepoUrlAgainstOrigin", () => {
  test("is unknown without ORCHESTRATE_REPO_URL; the checkout's remote is not consulted", () => {
    expect(checkRepoUrlAgainstOrigin({ repoUrl: REPO, env: {} })).toEqual({
      kind: "unknown",
      reason: "ORCHESTRATE_REPO_URL is unset",
    });
  });

  test("matches the configured origin across URL spellings", () => {
    for (const origin of [
      REPO,
      `${REPO}.git`,
      "git@github.com:nthplusio/skills.git",
      "ssh://git@github.com/nthplusio/skills",
      "GitHub.com/NthPlusIO/Skills/",
    ]) {
      expect(
        checkRepoUrlAgainstOrigin({ repoUrl: REPO, env: { ORCHESTRATE_REPO_URL: origin } })
      ).toEqual({ kind: "match", origin });
    }
  });

  test("rejects a plan.repoUrl that names another repository or cannot be parsed", () => {
    const env = { ORCHESTRATE_REPO_URL: REPO };
    const other = checkRepoUrlAgainstOrigin({ repoUrl: "https://github.com/evil/skills", env });
    expect(other.kind).toBe("mismatch");
    expect(other.kind === "mismatch" && other.reason).toContain("is not the configured origin");
    const junk = checkRepoUrlAgainstOrigin({ repoUrl: "::", env });
    expect(junk.kind).toBe("mismatch");
    expect(junk.kind === "mismatch" && junk.reason).toContain("could not parse");
  });

  test("repoKey normalises host, path, .git, case, and trailing slashes", () => {
    expect(repoKey("https://GitHub.com/A/B.git/")).toBe("github.com/a/b");
    expect(repoKey("git@github.com:a/b.git")).toBe("github.com/a/b");
    expect(repoKey("")).toBeNull();
    expect(repoKey("https://github.com")).toBeNull();
  });
});

describe("resolveSelfAgentId", () => {
  const ID = "T-01a13830-78c4-723b-8624-f4b865ca42d8";

  test("a missing key is upstream's unset and raises nothing", () => {
    expect(resolveSelfAgentId(undefined)).toEqual({ id: null, attention: null });
  });

  test("a thread id passes through", () => {
    expect(resolveSelfAgentId(ID)).toEqual({ id: ID, attention: null });
  });

  test("the unexpanded placeholder, an empty string, and a non-id are unknown with one attention line", () => {
    for (const value of ["$AMP_THREAD_ID", "${AMP_THREAD_ID}", " $AMP_THREAD_ID ", "", "bc-123", "--last"]) {
      const resolved = resolveSelfAgentId(value);
      expect(resolved.id).toBeNull();
      expect(resolved.attention).toContain("echo $AMP_THREAD_ID");
      expect(resolved.attention).toContain("kill-tree --agent-id");
    }
    expect(resolveSelfAgentId("$AMP_THREAD_ID").attention).toContain("unexpanded placeholder");
    expect(resolveSelfAgentId("bc-123").attention).toContain('"bc-123" is not an Amp thread id');
  });

  test("badThreadIdReason tells nudge-root and kill-tree why they refuse", () => {
    expect(badThreadIdReason(ID)).toBeNull();
    expect(isPendingAgentId("$AMP_THREAD_ID")).toBe(true);
    expect(badThreadIdReason("$AMP_THREAD_ID", "<agent-id>")).toContain(
      "<agent-id> is the unexpanded placeholder $AMP_THREAD_ID"
    );
    expect(badThreadIdReason("--last", "--agent-id")).toBe('--agent-id "--last" is not an Amp thread id');
  });
});

describe("run hygiene", () => {
  const ID = "T-01a13830-78c4-723b-8624-f4b865ca42d8";
  const OTHER = "T-01a13b70-1111-7222-8333-444455556666";

  test("runTagFor is the first six hex characters of a sha1 over the slug and the root's thread id", () => {
    const sha = (input: string) => createHash("sha1").update(input).digest("hex").slice(0, 6);
    expect(runTagFor("demo")).toBe(sha("demo"));
    expect(runTagFor("demo", null)).toBe(sha("demo"));
    expect(runTagFor("demo", ID)).toBe(sha(`demo\n${ID}`));
    expect(runTagFor("demo", ID)).toMatch(/^[0-9a-f]{6}$/);
    expect(runTagFor("demo", ID)).not.toBe(runTagFor("demo"));
    expect(runTagFor("demo", ID)).not.toBe(runTagFor("demo", OTHER));
    expect(runTagFor("demo", ID)).toBe(runTagFor("demo", ID));
  });

  test("every thread of a run carries the orchestrate label, the run label, and a tagged title", () => {
    const tag = runTagFor("demo", ID);
    expect(runLabels(tag)).toEqual(["orchestrate", `run-${tag}`]);
    expect(runLabels(tag).every(label => /^[A-Za-z0-9][A-Za-z0-9-]*$/.test(label))).toBe(true);
    expect(runTitle(tag, "task-a")).toBe(`${tag} task-a`);
    expect(runTitle(runTagFor("demo"), ROOT_TASK_TITLE)).toBe(`${runTagFor("demo")} root`);
  });

  test("the loop archives a finished worker, verifier, or subplanner thread after its handoff", () => {
    for (const type of ["worker", "verifier", "subplanner"]) {
      expect(
        shouldArchiveAfterHandoff({ type, resultStatus: "finished", agentId: OTHER, selfAgentId: ID })
      ).toBe(true);
    }
  });

  test("and never the root planner, an errored run, a missing thread, or a thread archived already", () => {
    const finished = { type: "worker", resultStatus: "finished", agentId: OTHER, selfAgentId: ID };
    expect(shouldArchiveAfterHandoff({ ...finished, agentId: ID })).toBe(false);
    expect(shouldArchiveAfterHandoff({ ...finished, type: "planner" })).toBe(false);
    expect(shouldArchiveAfterHandoff({ ...finished, resultStatus: "error" })).toBe(false);
    expect(shouldArchiveAfterHandoff({ ...finished, resultStatus: "cancelled" })).toBe(false);
    expect(shouldArchiveAfterHandoff({ ...finished, resultStatus: null })).toBe(false);
    expect(shouldArchiveAfterHandoff({ ...finished, agentId: null })).toBe(false);
    expect(shouldArchiveAfterHandoff({ ...finished, agentId: "$AMP_THREAD_ID" })).toBe(false);
    expect(
      shouldArchiveAfterHandoff({ ...finished, archivedAt: "2026-10-14T02:14:24.000Z" })
    ).toBe(false);
    // Without a known root id, a task thread is still archived.
    expect(shouldArchiveAfterHandoff({ ...finished, selfAgentId: null })).toBe(true);
  });
});
