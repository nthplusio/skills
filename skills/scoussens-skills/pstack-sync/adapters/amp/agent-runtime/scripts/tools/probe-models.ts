#!/usr/bin/env bun
// Amp port: upstream probed each catalog entry by creating a cloud agent and
// cancelling it. The Amp model catalog answers `probe(mode)` from the modes
// the amp CLI accepts, so no thread is spawned.
import type { ModelCatalog } from "../core/runtime.ts";
import { loadModelCatalog } from "../core/runtime.ts";
import { MODEL_CATALOG, type ModelProfile } from "../models.ts";

export type ProbeResult =
  | {
      profile: ModelProfile;
      ok: true;
    }
  | {
      profile: ModelProfile;
      ok: false;
      error: string;
    };

export async function probeModelCatalog(
  opts: {
    catalog?: ModelProfile[];
    modelCatalog?: ModelCatalog;
  } = {}
): Promise<ProbeResult[]> {
  const catalog = opts.catalog ?? MODEL_CATALOG;
  const modelCatalog = opts.modelCatalog ?? (await loadModelCatalog());
  const results: ProbeResult[] = [];
  for (const profile of catalog) {
    try {
      const ok = await modelCatalog.probe(profile.selection.id);
      if (ok) {
        results.push({ profile, ok: true });
      } else {
        const known = await modelCatalog.models();
        results.push({
          profile,
          ok: false,
          error: `not an agent mode the amp CLI lists (known: ${known.join(", ")})`,
        });
      }
    } catch (err) {
      results.push({
        profile,
        ok: false,
        error: (err instanceof Error ? err.message : String(err)).slice(0, 200),
      });
    }
  }
  return results;
}

export function printProbeResults(results: ProbeResult[]): number {
  let failures = 0;
  for (const r of results) {
    const label = `${r.profile.slug} -> ${JSON.stringify(r.profile.selection)}`;
    if (r.ok) {
      console.log(`[OK]   ${label}`);
    } else {
      failures += 1;
      console.log(`[FAIL] ${label}  ${r.error}`);
    }
  }
  if (failures > 0) {
    console.error(`\n${failures} catalog entries failed validation.`);
    console.error(
      "Compare against `amp --help` (-m, --mode) and update MODEL_CATALOG.selection."
    );
  } else {
    console.log("\nAll catalog entries validate.");
  }
  return failures;
}

if (import.meta.main) {
  const results = await probeModelCatalog();
  process.exit(printProbeResults(results) > 0 ? 1 : 0);
}
