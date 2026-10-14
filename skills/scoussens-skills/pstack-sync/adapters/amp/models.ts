/**
 * `ModelCatalog` for Amp. A plan's `tasks[].model` is an Amp agent mode: one
 * of the built-in effort modes, `inherit` for the CLI's default, or a plugin
 * mode by key. No `amp` command lists plugin modes today;
 * `amp plugins show-agent-options --json` lists provider models and tools
 * for plugin agents, so this reads any `agentModes`, `modes`, or
 * `pluginModes` array it may grow and otherwise returns the built-ins.
 */

import { spawn as spawnProcess } from "node:child_process";
import type { ModelCatalog } from "../interface.ts";

export const AMP_BUILTIN_MODES: readonly string[] = [
  "inherit",
  "low",
  "medium",
  "high",
  "ultra",
];

export interface AmpModelCatalogOptions {
  /** CLI binary; `ORCHESTRATE_AMP_BIN`, default `amp`. */
  bin?: string;
  env?: NodeJS.ProcessEnv;
  /** Wall-time cap for the listing command, default 30 s. */
  timeoutMs?: number;
}

/** Mode names found in a `show-agent-options --json` payload, if it carries any. */
export function pluginModesFrom(payload: unknown): string[] {
  if (typeof payload !== "object" || payload === null) return [];
  const rec = payload as Record<string, unknown>;
  const out: string[] = [];
  for (const key of ["agentModes", "modes", "pluginModes"]) {
    const list = rec[key];
    if (!Array.isArray(list)) continue;
    for (const item of list) {
      if (typeof item === "string") out.push(item);
      else if (typeof item === "object" && item !== null) {
        const r = item as Record<string, unknown>;
        const name = r.key ?? r.id ?? r.name;
        if (typeof name === "string") out.push(name);
      }
    }
  }
  return out;
}

export function createAmpModelCatalog(options: AmpModelCatalogOptions = {}): ModelCatalog {
  const env = options.env ?? process.env;
  const bin = options.bin || env.ORCHESTRATE_AMP_BIN || "amp";
  const timeoutMs = options.timeoutMs ?? 30_000;
  let cached: Promise<string[]> | null = null;

  function listPluginModes(): Promise<string[]> {
    return new Promise(resolvePromise => {
      let stdout = "";
      let child: ReturnType<typeof spawnProcess>;
      try {
        child = spawnProcess(bin, ["plugins", "show-agent-options", "--json"], {
          env,
          stdio: ["ignore", "pipe", "ignore"],
        });
      } catch {
        resolvePromise([]);
        return;
      }
      const timer = setTimeout(() => {
        child.kill("SIGKILL");
        resolvePromise([]);
      }, timeoutMs);
      child.stdout?.setEncoding("utf8");
      child.stdout?.on("data", chunk => {
        stdout += chunk;
      });
      child.on("error", () => {
        clearTimeout(timer);
        resolvePromise([]);
      });
      child.on("close", code => {
        clearTimeout(timer);
        if (code !== 0) {
          resolvePromise([]);
          return;
        }
        try {
          resolvePromise(pluginModesFrom(JSON.parse(stdout)));
        } catch {
          resolvePromise([]);
        }
      });
    });
  }

  const catalog: ModelCatalog = {
    async models(): Promise<string[]> {
      if (!cached) {
        cached = listPluginModes().then(plugin => {
          const out = [...AMP_BUILTIN_MODES];
          for (const mode of plugin) {
            if (!out.some(m => m.toLowerCase() === mode.toLowerCase())) out.push(mode);
          }
          return out;
        });
      }
      return cached;
    },
    async probe(model: string): Promise<boolean> {
      const wanted = model.trim().toLowerCase();
      if (!wanted) return false;
      const known = await catalog.models();
      return known.some(m => m.toLowerCase() === wanted);
    },
  };
  return catalog;
}
