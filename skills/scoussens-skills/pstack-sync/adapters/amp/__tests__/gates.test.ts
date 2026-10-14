import { describe, expect, test } from "bun:test";
import {
  checkRepoUrlAgainstOrigin,
  measurementGate,
  repoKey,
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
