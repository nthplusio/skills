/**
 * `models --check` through the port's `tools/probe-models.ts`. Upstream's
 * `scripts/__tests__/probe-models.test.ts` calls
 * `probeModelCatalog("test-key", { agentApi })`, the SDK signature the port
 * replaced; the set ignores `scripts/__tests__/**`, so this is its Amp
 * counterpart. The port files are spread over two port directories in the
 * pack, so the test assembles them into one `scripts/` tree first.
 */
import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { chmodSync, cpSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import type { ModelCatalog } from "../../interface.ts";
import { createAmpModelCatalog } from "../models.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const ADAPTER = join(HERE, "..");
const FAKE_DIR = join(HERE, "fake-amp");

type Profile = {
  slug: string;
  selection: { id: string };
  summary: string;
  strengths: string[];
  speed: "fast" | "medium" | "slow";
  use: string;
};
type ProbeModule = {
  probeModelCatalog(opts?: { catalog?: Profile[]; modelCatalog?: ModelCatalog }): Promise<
    ({ profile: Profile; ok: true } | { profile: Profile; ok: false; error: string })[]
  >;
  printProbeResults(results: Awaited<ReturnType<ProbeModule["probeModelCatalog"]>>): number;
};

let root: string;
let probe: ProbeModule;
let models: { MODEL_CATALOG: Profile[]; isKnownModel(slug: string): boolean };

beforeAll(async () => {
  root = mkdtempSync(join(tmpdir(), "os4-scripts-"));
  cpSync(join(ADAPTER, "agent-runtime", "scripts"), join(root, "scripts"), { recursive: true });
  cpSync(join(ADAPTER, "models", "scripts"), join(root, "scripts"), { recursive: true });
  probe = (await import(pathToFileURL(join(root, "scripts", "tools", "probe-models.ts")).href)) as ProbeModule;
  models = await import(pathToFileURL(join(root, "scripts", "models.ts")).href);
});

afterAll(() => {
  rmSync(root, { recursive: true, force: true });
});

function profile(slug: string, id = slug): Profile {
  return { slug, selection: { id }, summary: slug, strengths: [], speed: "fast", use: slug };
}

describe("models --check", () => {
  test("marks modes the catalog does not list as failures, naming the known modes", async () => {
    const catalog = [profile("high"), profile("opus", "claude-opus-4-8")];
    const modelCatalog: ModelCatalog = {
      models: async () => ["inherit", "high"],
      probe: async model => model === "high",
    };
    const results = await probe.probeModelCatalog({ catalog, modelCatalog });
    expect(results).toEqual([
      { profile: catalog[0], ok: true },
      {
        profile: catalog[1],
        ok: false,
        error: "not an agent mode the amp CLI lists (known: inherit, high)",
      },
    ]);
  });

  test("a catalog that throws is reported, not thrown", async () => {
    const results = await probe.probeModelCatalog({
      catalog: [profile("high")],
      modelCatalog: {
        models: async () => [],
        probe: async () => {
          throw new Error("amp not signed in");
        },
      },
    });
    expect(results).toEqual([{ profile: profile("high"), ok: false, error: "amp not signed in" }]);
  });

  test("the shipped catalog validates against the Amp model catalog without spawning", async () => {
    const dir = mkdtempSync(join(tmpdir(), "os4-fake-amp-"));
    chmodSync(join(FAKE_DIR, "amp"), 0o755);
    writeFileSync(join(dir, "calls.log"), "");
    try {
      const env = { ...process.env, FAKE_AMP_DIR: dir, FAKE_AMP_LOG: join(dir, "calls.log") };
      const modelCatalog = createAmpModelCatalog({ env, bin: join(FAKE_DIR, "amp") });
      const results = await probe.probeModelCatalog({ catalog: models.MODEL_CATALOG, modelCatalog });
      expect(results.every(r => r.ok)).toBe(true);
      expect(models.MODEL_CATALOG.map(m => m.slug)).toEqual(["inherit", "low", "medium", "high", "ultra"]);
      expect(models.isKnownModel("ultra")).toBe(true);
      expect(models.isKnownModel("claude-opus-4-8")).toBe(false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("printProbeResults returns the failure count", () => {
    const lines: string[] = [];
    const priorLog = console.log;
    const priorError = console.error;
    console.log = (line?: unknown) => {
      lines.push(String(line ?? ""));
    };
    console.error = (line?: unknown) => {
      lines.push(String(line ?? ""));
    };
    try {
      expect(probe.printProbeResults([{ profile: profile("bad"), ok: false, error: "not an agent mode" }])).toBe(1);
      expect(probe.printProbeResults([{ profile: profile("high"), ok: true }])).toBe(0);
      expect(lines.join("\n")).toContain("[FAIL] bad -> {\"id\":\"bad\"}  not an agent mode");
      expect(lines.join("\n")).toContain("amp --help");
    } finally {
      console.log = priorLog;
      console.error = priorError;
    }
  });
});
