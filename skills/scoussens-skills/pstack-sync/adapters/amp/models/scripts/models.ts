import type { ModelSelection } from "./core/runtime.ts";

import type { TaskType } from "./adapters/types.ts";

// Model catalog. Source of truth for `tasks[].model` choices; `defaultFor`
// entries supply the fallback when `tasks[].model` is omitted.
//
// Amp port: a "model" is an Amp agent mode. The CLI accepts the built-in
// effort modes and plugin modes by key; `inherit` means the CLI's default
// mode. There is no per-model parameter block, so every selection is a bare
// `{ id }` and the mode name is the slug.

export interface ModelProfile {
  /** User-facing slug for `tasks[].model` and `--model` flags. */
  slug: string;
  /** Canonical selection passed to `Agent.create({ model })`. */
  selection: ModelSelection;
  summary: string;
  strengths: string[];
  speed: "fast" | "medium" | "slow";
  use: string;
  /** Task types this profile is the default for. */
  defaultFor?: TaskType[];
}

// `slug` is the stable authoring name; `selection` is the canonical form.
// Run `bun cli.ts models --check` after an amp upgrade.
export const MODEL_CATALOG: ModelProfile[] = [
  {
    slug: "inherit",
    selection: { id: "inherit" },
    summary: "The amp CLI's default agent mode; no `-m` flag is passed.",
    strengths: ["operator's choice", "predictable cost"],
    speed: "medium",
    use: "Default for workers. Picks up whatever mode the operator configured as the CLI default, so a fleet of workers costs what the operator expects.",
    defaultFor: ["worker"],
  },
  {
    slug: "low",
    selection: { id: "low" },
    summary: "Fast, low-cost mode for small, well-defined tasks.",
    strengths: ["throughput", "mechanical edits", "bounded scope"],
    speed: "fast",
    use: "Workers doing well-scoped code edits with clear acceptance criteria when judgment is not the bottleneck.",
  },
  {
    slug: "medium",
    selection: { id: "medium" },
    summary: "Default for most tasks, balancing quality, speed, and cost.",
    strengths: ["balanced", "general implementation"],
    speed: "medium",
    use: "Default for verifiers; focused acceptance checks do not need the deepest reasoning. Also the right tier for workers whose slice mixes code and judgment.",
    defaultFor: ["verifier"],
  },
  {
    slug: "high",
    selection: { id: "high" },
    summary: "Deeper reasoning for difficult tasks that can tolerate more time and cost.",
    strengths: ["judgment", "architecture", "ambiguity resolution", "subtle correctness"],
    speed: "slow",
    use: "Default for subplanners: they decompose, route, and synthesize, where deep judgment pays off. Also the pick for workers owning systems or architecture slices.",
    defaultFor: ["subplanner"],
  },
  {
    slug: "ultra",
    selection: { id: "ultra" },
    summary: "Maximum capability for the hardest open-ended tasks; slowest and most expensive.",
    strengths: ["complex judgment", "deep reasoning"],
    speed: "slow",
    use: "Reserved for exceptionally difficult tasks. May overthink simple problems; only reach for this when `high` has produced unsatisfying results.",
  },
];

export function defaultModelForType(type: TaskType): string {
  const match = MODEL_CATALOG.find(m => m.defaultFor?.includes(type));
  if (!match)
    throw new Error(`MODEL_CATALOG missing default for TaskType "${type}"`);
  return match.slug;
}

export function isKnownModel(slug: string): boolean {
  return MODEL_CATALOG.some(m => m.slug === slug);
}

/** Unknown slugs pass through as a bare `{ id }` so planners can reach
 * plugin modes that aren't in our prescriptive catalog. */
export function resolveModelSelection(slug: string): ModelSelection {
  const profile = MODEL_CATALOG.find(m => m.slug === slug);
  return profile ? profile.selection : { id: slug };
}

export function renderModelCatalog(): string {
  const lines: string[] = [];
  for (const m of MODEL_CATALOG) {
    const defaults = m.defaultFor?.length
      ? ` (default for ${m.defaultFor.join(", ")})`
      : "";
    lines.push(`- \`${m.slug}\` — ${m.summary}${defaults}`);
    lines.push(`  speed: ${m.speed}; strengths: ${m.strengths.join(", ")}`);
    lines.push(`  use: ${m.use}`);
  }
  lines.push(
    "Plugin modes the amp CLI knows (`amp --help`, `-m`) also work as `tasks[].model`; run `bun cli.ts models --check` to confirm a name."
  );
  return lines.join("\n");
}
