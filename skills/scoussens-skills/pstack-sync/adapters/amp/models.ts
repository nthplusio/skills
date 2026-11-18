/**
 * `ModelCatalog` for Amp. A plan's `tasks[].model` is `inherit` for the
 * CLI's default, an Amp model as `provider/name` (such as
 * `openai/gpt-6-astra`), or a model at a reasoning effort as
 * `provider/name@effort` (such as `openai/gpt-6-astra@xhigh`). Amp has no
 * agent modes for a plan to pick: `amp plugins show-agent-options --json`
 * lists the models, each with the efforts it accepts, and this catalog is
 * that list.
 */

import { spawn as spawnProcess } from "node:child_process";
import type { ModelCatalog } from "../interface.ts";

export interface AmpModelCatalogOptions {
  /** CLI binary; `ORCHESTRATE_AMP_BIN`, default `amp`. */
  bin?: string;
  env?: NodeJS.ProcessEnv;
  /** Wall-time cap for the listing command, default 30 s. */
  timeoutMs?: number;
}

/** A model value split into the model and the effort after `@`, if any. */
export function parseModelValue(value: string): { model: string; effort?: string } {
  const at = value.lastIndexOf("@");
  if (at <= 0) return { model: value };
  return { model: value.slice(0, at), effort: value.slice(at + 1) };
}

/**
 * The values a `show-agent-options --json` payload allows: each model's
 * `id`, then `id@effort` for every effort in `capabilities.efforts`.
 */
export function modelValuesFrom(payload: unknown): string[] {
  if (typeof payload !== "object" || payload === null) return [];
  const list = (payload as Record<string, unknown>).models;
  if (!Array.isArray(list)) return [];
  const out: string[] = [];
  for (const item of list) {
    if (typeof item !== "object" || item === null) continue;
    const r = item as Record<string, unknown>;
    if (typeof r.id !== "string" || !r.id.includes("/")) continue;
    out.push(r.id);
    const caps = r.capabilities as Record<string, unknown> | undefined;
    const efforts = Array.isArray(caps?.efforts) ? caps.efforts : [];
    for (const effort of efforts) if (typeof effort === "string") out.push(`${r.id}@${effort}`);
  }
  return out;
}

export function createAmpModelCatalog(options: AmpModelCatalogOptions = {}): ModelCatalog {
  const env = options.env ?? process.env;
  const bin = options.bin || env.ORCHESTRATE_AMP_BIN || "amp";
  const timeoutMs = options.timeoutMs ?? 30_000;
  let cached: Promise<string[]> | null = null;

  function listModels(): Promise<string[]> {
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
          resolvePromise(modelValuesFrom(JSON.parse(stdout)));
        } catch {
          resolvePromise([]);
        }
      });
    });
  }

  const catalog: ModelCatalog = {
    async models(): Promise<string[]> {
      if (!cached) cached = listModels().then(models => ["inherit", ...models]);
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
