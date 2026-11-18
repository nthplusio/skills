import type { ModelSelection } from "./core/runtime.ts";

import type { TaskType } from "./adapters/types.ts";

// Model catalog. Source of truth for `tasks[].model` choices; `defaultFor`
// entries supply the fallback when `tasks[].model` is omitted.
//
// Amp port: a "model" is `inherit` (the CLI's default), an Amp model as
// `provider/name`, or a model at a reasoning effort as `provider/name@effort`.
// Amp has no agent modes to pick. There is no per-model parameter block, so
// every selection is a bare `{ id }` and the value is the slug.

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
    summary: "The amp CLI's default model and effort; no `--model` flag is passed.",
    strengths: ["operator's choice", "predictable cost"],
    speed: "medium",
    use: "Default for workers. Picks up whatever model the operator configured as the CLI default, so a fleet of workers costs what the operator expects.",
    defaultFor: ["worker"],
  },
  {
    slug: "anthropic/claude-haiku-5-5@low",
    selection: { id: "anthropic/claude-haiku-5-5@low" },
    summary: "Small, fast, low-cost model for small, well-defined tasks.",
    strengths: ["throughput", "mechanical edits", "bounded scope"],
    speed: "fast",
    use: "Workers doing well-scoped code edits with clear acceptance criteria when judgment is not the bottleneck.",
  },
  {
    slug: "anthropic/claude-opus-5-5@medium",
    selection: { id: "anthropic/claude-opus-5-5@medium" },
    summary: "Strong general model at its default effort, balancing quality, speed, and cost.",
    strengths: ["balanced", "general implementation"],
    speed: "medium",
    use: "Default for verifiers; focused acceptance checks do not need the deepest reasoning. Also the right tier for workers whose slice mixes code and judgment.",
    defaultFor: ["verifier"],
  },
  {
    slug: "anthropic/claude-opus-5-5@xhigh",
    selection: { id: "anthropic/claude-opus-5-5@xhigh" },
    summary: "The same model with deeper reasoning, for difficult tasks that can tolerate more time and cost.",
    strengths: ["judgment", "architecture", "ambiguity resolution", "subtle correctness"],
    speed: "slow",
    use: "Default for subplanners: they decompose, route, and synthesize, where deep judgment pays off. Also the pick for workers owning systems or architecture slices.",
    defaultFor: ["subplanner"],
  },
  {
    slug: "openai/gpt-6-astra@xhigh",
    selection: { id: "openai/gpt-6-astra@xhigh" },
    summary: "Another vendor's deep-reasoning model for the hardest open-ended tasks; slow and expensive.",
    strengths: ["complex judgment", "deep reasoning", "vendor diversity"],
    speed: "slow",
    use: "Reserved for exceptionally difficult tasks, or a second opinion from another vendor. Only reach for this when a Claude model at `xhigh` has produced unsatisfying results.",
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
 * models and efforts that aren't in our prescriptive catalog. */
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
    "Any model `amp plugins show-agent-options` lists also works as `tasks[].model`, as `provider/name` or `provider/name@effort` with one of its efforts; run `bun cli.ts models --check` to confirm a value."
  );
  return lines.join("\n");
}
