# Cross-platform skill distribution

Researched on 2026-10-30. This is a recommendation, not an implemented migration.

## Keep one skill source and distribute tested subsets

Keep the existing `skills/scoussens-skills/<name>/` source directories. Add thin plugin manifests, Codex metadata, and generated upload packages. Do not maintain separate copies of the instructions for Claude, Codex, and Amp.

The unit of reuse is a complete skill directory. The unit of distribution can be an individual skill or a plugin containing several skills. The unit of compatibility is a product mode with particular tools, not a model name. ChatGPT Chat, ChatGPT Work, Codex CLI, Claude chat, Claude Cowork, and Claude Code need separate runtime checks even when they accept the same files.

This recommendation applies the Laziness Protocol. Keep the working source layout, reuse the existing validator and discovery code, and generate only the files a distribution target requires.

Evidence labels used below:

- **Observed** means inspected in this checkout or exercised with a local command.
- **Documented** means stated by the platform's official documentation or upstream source.
- **Recommended** means a design choice proposed for this repository.
- **Unverified** means not exercised in the target product.

## The repository already supports coding-agent installation

Observed at repository revision [a00fc46](https://github.com/nthplusio/skills/commit/a00fc468f67134352ccb6d2a1cadc297430cfe3d):

| Existing structure | What it provides | Gap relevant to this research |
| --- | --- | --- |
| `skills/scoussens-skills/<name>/` | Twenty reusable skills with owned resources | No per-skill `agents/openai.yaml` files |
| `.claude-plugin/marketplace.json` | Three Claude Code plugins, `context-statusline`, `doorbell`, and `doorbell-grant` | The reusable skill collection is not itself a listed plugin |
| `plugins/amp-skill-picker/` | A separate Amp integration | Not a portable Claude or OpenAI plugin |
| `scripts/validate-skills.mjs` | Frontmatter, resources, links, evaluation fixtures, and pack limits | One validation policy combines standard rules and host-specific exceptions |
| `scripts/check-builder-agrees.mjs` | A real skills CLI discovery check | Discovery is not a target-runtime behavior test |
| `metadata.needs` and `harness-discovery` | Existing capability vocabulary and discovery mechanism | No distribution-level support matrix or skill dependency resolver |
| `.github/workflows/validate.yml` | Validation, skill tests, plugin checks, and live CLI discovery | No upload-package build or release-archive checks |

Sources are the [README](../../README.md), [marketplace](../../.claude-plugin/marketplace.json), [validator](../../scripts/validate-skills.mjs), [discovery code](../../scripts/lib/discover-skills.mjs), and [workflow](../../.github/workflows/validate.yml).

Observed checks:

- `npm run validate` passed for twenty public skills and one plugin-local skill.
- `DISABLE_TELEMETRY=1 npm run check:builder` passed and found all twenty public skills.
- In an empty temporary directory, `skills@1.7.4 add /home/user/workspace/repo --skill speak-clearly --agent codex claude-code --copy --yes` installed the skill under `.agents/skills/` and `.claude/skills/`. Byte comparisons confirmed that both installed instruction files and the bundled reference were preserved. No global skills were installed.

These checks establish discovery and file installation. They do not establish successful execution in Codex or Claude Code.

## Each target has a distinct installation contract

| Target | Documented structure or delivery route | Recommendation for this repository |
| --- | --- | --- |
| skills.sh CLI | Discovers `SKILL.md` directories under `skills/`, including category levels. Installs into the selected agent's directories. Also reads Claude plugin manifests. | Keep direct GitHub installation as the universal coding-agent route. No new manifest is necessary for the current source layout. |
| skills.sh packs | Hosted collections installed through a pack URL. The pack builder drops binary files and files over 2 MB. | Keep the existing pack as an optional convenience. Do not treat its file limits as requirements of every skill host. |
| Codex CLI and IDE | Project skills in `.agents/skills/`; user skills in `~/.agents/skills/`. Optional `agents/openai.yaml` controls presentation, invocation, and tool dependencies. | Add the sidecar metadata and document agent-targeted installation. |
| Codex managed plugins | Local or Git marketplaces. `.agents/plugins/marketplace.json` is the current native catalog. Claude-compatible manifests remain supported. | Add a curated OpenAI catalog so Claude-only mods are not advertised as compatible plugins. Reuse supported Claude manifests for the first local integration. |
| ChatGPT desktop | Standalone skills and plugins. Current docs describe a Skills sidebar and local marketplace testing. | Test the same portable workflows here, with explicit tool requirements. Do not equate desktop availability with web availability. |
| ChatGPT web and mobile | Skills bundled in plugins work in Chat and Work. Public distribution uses the shared ChatGPT/Codex plugin directory. | Produce a portable plugin archive for submission. A GitHub repo or skills.sh listing alone does not publish to this directory. |
| Claude Code | `.claude/skills/<name>/SKILL.md`, `~/.claude/skills/<name>/SKILL.md`, or plugin skills. Plugins use `.claude-plugin/plugin.json`. | Add a skill-collection plugin to the existing marketplace. Keep native mods separate. |
| Claude chat, including the Desktop Chat tab | Account-installed skill ZIPs and plugins. A standalone skill ZIP contains `<name>/SKILL.md`. Plugins can come from a Git marketplace or upload. | Offer a tested skills-only plugin and individual strict-format ZIPs where the skill is independent. |
| Claude Cowork | Account plugins and skills, with more runtime capabilities than chat. | Test separately. Do not claim a chat workflow can execute local hooks or subagents. |
| Amp local projects | `.agents/skills/`; `amp skill add` also accepts repository and local sources. | Continue using complete skill directories. |
| Amp hosted personal/workspace skills | Each skill is an immediate child of the hosted repository root. Files must be text. Publishing is a separate push to that repository. | Provide a top-level-directory export if automated publishing is needed. Installing into an orb's local global directory does not publish across orbs. |
| Other coding agents | The skills CLI maps supported agents to their installation directories. | Document the installer route, then claim runtime support only for tested workflows. |

Primary sources: [skills CLI discovery](https://raw.githubusercontent.com/vercel-labs/skills/main/docs/creating-skills.md), [CLI commands](https://raw.githubusercontent.com/vercel-labs/skills/main/docs/commands.md), [agent paths](https://raw.githubusercontent.com/vercel-labs/skills/main/docs/agents.md), [packs](https://www.skills.sh/docs/packs), [OpenAI skills](https://developers.openai.com/codex/skills), [OpenAI plugins](https://developers.openai.com/plugins/build/plugins), [Claude skills](https://code.claude.com/docs/en/skills), [Claude platform support](https://claude.com/docs/plugins/platform-support.md), and [Amp skills](https://ampcode.com/docs/markdown/customize/skills).

### Desktop support is broader than older guidance suggests

Documented by OpenAI, standalone skills are available in the ChatGPT desktop app, Codex CLI, and the IDE extension. Plugin-bundled skills also reach Chat and Work across web, desktop, and mobile. OpenAI recommends a root `plugin.json` with the Agent Plugins schema for new portable packages. `.codex-plugin/plugin.json` remains a compatibility format, not a requirement to duplicate every plugin. [OpenAI skills](https://developers.openai.com/codex/skills), [packaging](https://developers.openai.com/plugins/build/plugins).

Documented by Anthropic, Claude plugins work in web chat, Desktop Chat, Cowork, and Claude Code. Skills and commands load across these modes. Agents and hooks do not run in chat. Local MCP servers do not run in chat. Claude Code mods are listed for Claude Code, not assumed portable to Cowork. A top-level `bin/` directory prevents installation in chat and Cowork. [Platform support](https://claude.com/docs/plugins/platform-support.md).

Account-installed Claude plugins can sync to Claude Code. Installing a plugin through the terminal does not upload it to the Claude account. Skill sync also requires an eligible account login, not an API-key or cloud-provider session. Avoid documentation that promises bidirectional synchronization. [Plugin installation and sync](https://claude.com/docs/plugins/platform-support.md), [skill sync](https://support.claude.com/en/articles/12512180-use-skills-in-claude).

## Matt Pocock's repository is a useful coding-agent reference

The upstream investigation inspected revision [a496f55](https://github.com/mattpocock/skills/commit/a496f5513d4a4cf889bc48e189e579f4b0bdf6aa), dated 2026-10-29, and version 1.3.2. It read source, manifests, release automation, and packaging history without executing fetched scripts.

| Pattern | Evidence | Decision for this repository |
| --- | --- | --- |
| One canonical skill directory | Skills are grouped under `engineering`, `productivity`, `in-progress`, and `misc`. | Copy the single-source approach. Changing our category name is not required for compatibility. |
| Explicit promoted set | Twenty-seven promoted skills are listed in the plugin manifest. Other public skill folders remain outside that plugin. | Curate supported bundles explicitly. A directory named `in-progress` does not hide a skill from skills.sh. |
| Thin Claude plugin manifest | One root plugin uses explicit paths to canonical skill folders. Its marketplace points to `./`. | Add a root skill-collection manifest rather than copying twenty skill bodies into a new source directory. |
| Codex policy sidecars | All thirty-eight skill folders have `agents/openai.yaml`. Explicit-only skills pair the Codex policy with Claude's frontmatter field. | Add corresponding sidecars and a consistency check. |
| One release version | Changesets updates the package version, then a script synchronizes the plugin version. | Use one release version for generated metadata and archives. Changesets is optional at this repository's size. |
| Managed versus editable installation | README explains plugin installs separately from copied skills and warns about duplicates. | Give users one preferred route per product and explain update behavior. |
| Separate human documentation | Human-facing skill pages explain prerequisites and use cases separately from agent instructions. | Start with a concise install/support page. Add individual pages when they answer real user questions. |

Sources: upstream [repository guidance](https://github.com/mattpocock/skills/blob/a496f5513d4a4cf889bc48e189e579f4b0bdf6aa/AGENTS.md), [plugin manifest](https://github.com/mattpocock/skills/blob/a496f5513d4a4cf889bc48e189e579f4b0bdf6aa/.claude-plugin/plugin.json), [marketplace](https://github.com/mattpocock/skills/blob/a496f5513d4a4cf889bc48e189e579f4b0bdf6aa/.claude-plugin/marketplace.json), [README](https://github.com/mattpocock/skills/blob/a496f5513d4a4cf889bc48e189e579f4b0bdf6aa/README.md), [invocation rules](https://github.com/mattpocock/skills/blob/a496f5513d4a4cf889bc48e189e579f4b0bdf6aa/.agents/invocation.md), and [release workflow](https://github.com/mattpocock/skills/blob/a496f5513d4a4cf889bc48e189e579f4b0bdf6aa/.github/workflows/release.yml).

### Do not copy its limitations

- Its inspected release had no uploaded release assets. There was no desktop ZIP exporter or ChatGPT installation guide. It is not evidence of tested desktop support.
- Its skill-to-skill dependencies are instructions in prose. For example, `grill-with-docs` calls `grilling` and `domain-modeling`. Selecting the wrapper alone does not prove its dependencies are installed. [Wrapper source](https://github.com/mattpocock/skills/blob/a496f5513d4a4cf889bc48e189e579f4b0bdf6aa/skills/engineering/grill-with-docs/SKILL.md).
- Its maintainer symlink script removes existing non-symlink destinations. Do not adopt it as a public installer. [Script](https://github.com/mattpocock/skills/blob/a496f5513d4a4cf889bc48e189e579f4b0bdf6aa/scripts/link-skills.sh).
- Its packaging ADR initially deferred Codex, then recorded working array paths and Claude-manifest fallback with Codex 0.161.0 in October. The initial rejection is superseded by the later entries. That version is an upstream test record, not an independently established minimum. [ADR](https://github.com/mattpocock/skills/blob/a496f5513d4a4cf889bc48e189e579f4b0bdf6aa/.agents/adr/0002-ship-as-a-claude-code-plugin.md).

## The main gaps are behavioral, not directory depth

### Preserve invocation rules across products

Observed, five skills set `disable-model-invocation: true`: `pr-detail`, `pr-digest`, `pr-review-round`, `pr-teacher`, and `visualize-spec`. None has `agents/openai.yaml`.

Codex documents `policy.allow_implicit_invocation: false` in that sidecar. The absence of the sidecar is a missing Codex policy declaration, not proof of an observed unintended invocation. [OpenAI metadata](https://developers.openai.com/codex/skills).

Claude's standalone skill uploader and the reference packager accept the six standard frontmatter fields and reject additional fields. Therefore, a raw ZIP of these five skills is not the documented standalone-upload format. Claude Code accepts its extension. An exporter must remove the extension for strict targets and preserve the explicit-only intent in instructions. That instruction is not equivalent to a host-enforced policy. Exclude a skill from a target if the missing policy is necessary for safe use. [Claude frontmatter portability](https://code.claude.com/docs/en/skills#using-skill-frontmatter-outside-claude-code).

Recommended, use one invocation policy as the source for generated host metadata. Also audit prose-only "invoked explicitly" claims before deciding which other skills need a policy. Do not mark every workflow implicit merely because its source lacks the Boolean.

### Package required skills together

Observed, `pr-teacher` requires `explain-to`. `explain-to` loads `speak-clearly` only when available. Its destination reference uses the `harness-discovery` resolver and also describes fallbacks when no discovery entry or publishing tool exists. These are different dependency contracts. The current link validator prevents broken relative Markdown links, but it does not resolve named skill dependencies. [PR teacher](../../skills/scoussens-skills/pr-teacher/SKILL.md), [explain-to](../../skills/scoussens-skills/explain-to/SKILL.md), [destination reference](../../skills/scoussens-skills/explain-to/references/formats.md).

Recommended, record required versus optional skill dependencies in a small packaging catalog. Include transitive required skills in each plugin bundle, and fail packaging when a requirement is unavailable. Keep tool dependencies separate from skill dependencies. `agents/openai.yaml` documents tool dependencies; do not invent a supported skill-install dependency mechanism there.

For individually installed skills, document the required companion install or provide an actual fallback. Do not assume a host exposes a tool named `Skill`. For standalone uploads, a workflow that cannot load companions must be self-contained or explicitly unsupported. The shared Agent Skills specification does not define a cross-skill invocation API. [Specification](https://agentskills.io/specification).

### Declare capabilities and test the intended modes

Recommended support classes:

| Class | Contract | Initial examples to evaluate |
| --- | --- | --- |
| Conversational | Needs only instructions, bundled references, and user-provided input | `speak-clearly`; inspect `agent-handoff` for a chat-only path |
| Tool-dependent | Needs repository access, scripts, trackers, connectors, or artifact output | `working-tickets`, `pr-teacher`, `meeting-index`, `designing-questionnaires` |
| Host-specific | Needs a named product's APIs or runtime | `picking-skills`, which explicitly requires an Amp Linux orb |

These are evaluation candidates, not completed compatibility certifications. `picking-skills` already states its host requirement in [frontmatter](../../skills/scoussens-skills/picking-skills/SKILL.md). The existing `metadata.needs` vocabulary is useful, but a vocabulary entry does not prove that a host supplies the capability. The checked-in discovery registry currently has only an Amp entry.

Do not translate `context-statusline`, `doorbell`, or `doorbell-grant` into OpenAI plugins by changing their manifests. Their runtime implementations are Claude Code-specific. Likewise, Amp tool names, portals, background threads, and wake-up behavior need explicit alternatives or an unsupported status.

### Separate standard rules from delivery restrictions

The Agent Skills specification allows a skill folder with scripts, references, assets, and other resources. Its metadata values are strings. The skills.sh `metadata.internal: true` Boolean is a CLI extension. The 2 MB and text-only constraints documented for hosted packs are not universal Git-install or plugin constraints. [Specification](https://agentskills.io/specification), [skills CLI extensions](https://raw.githubusercontent.com/vercel-labs/skills/main/docs/creating-skills.md), [pack limits](https://www.skills.sh/docs/packs).

Recommended, retain current checks for the current pack, but distinguish standard validation, pack validation, Claude Code extensions, and strict upload validation. Put plugin icons outside the canonical skill folders when only plugin presentation needs them. This avoids imposing the pack's binary restriction on every output.

One documentation discrepancy needs care. The Claude Help Center custom-skill article says descriptions have a 200-character maximum and shows inconsistent metadata examples. The Claude developer guide explicitly says 1,024 characters and matches the open specification. Use the developer guide and validate actual uploads before claiming support. Shortening descriptions remains useful for selection accuracy, not because a universal 200-character limit was established. [Help article](https://support.claude.com/en/articles/12512198-creating-custom-skills), [developer guide](https://claude.com/docs/skills/how-to.md).

## Recommended repository organization

Keep authoring files separate from generated distribution artifacts:

| Path | Ownership and purpose |
| --- | --- |
| `skills/scoussens-skills/<name>/SKILL.md` | Canonical workflow instructions. Preserve the current paths in the first implementation. |
| `skills/scoussens-skills/<name>/references/`, `scripts/`, `assets/`, `evals/` | Resources and existing tests owned by that skill. |
| `skills/scoussens-skills/<name>/agents/openai.yaml` | Codex presentation and invocation policy. This directory does not imply a portable subagent definition. |
| `plugins/<name>/` | Existing native integrations. Keep their host requirements explicit. |
| `.claude-plugin/plugin.json` | New root skill-collection plugin with explicit canonical skill paths. |
| `.claude-plugin/marketplace.json` | Existing Claude catalog, extended with the collection plugin. |
| `.agents/plugins/marketplace.json` | OpenAI catalog listing only approved plugins, not every Claude Code mod. |
| `distribution/catalog.json` | Proposed small catalog for bundle membership, required skill dependencies, and target support evidence. Reference canonical metadata rather than duplicating descriptions. |
| `scripts/` | Extend existing checks and add one package builder. Avoid a new framework or a script per host. |
| `docs/installation.md` | Human installation routes, update behavior, tested modes, prerequisites, and known limitations. |
| `dist/` | Generated, untracked plugin folders, archives, and checksums. Publish selected outputs as release assets after approval. |

The root source plugin can use explicit paths, as Matt's does. The generated portable plugin must use the conventional flat `skills/<name>/SKILL.md` package layout. Flattening the export does not require moving the authoring directories.

Recommended generated outputs:

| Output | Contents |
| --- | --- |
| Portable plugin folder | Root `plugin.json` using the Agent Plugins schema, `.claude-plugin/plugin.json` for Claude, `skills/<name>/`, README, and license. Both manifests derive shared identity and version from one source. |
| OpenAI plugin ZIP | A tested skills-only portable package for local testing or directory submission. Add MCP only when the workflow actually requires a bundled integration. |
| Claude plugin ZIP | One plugin with `.claude-plugin/plugin.json` at its root or under one enclosing folder. Include the tested skill dependency closure. |
| Individual Claude skill ZIP | Exactly one enclosing `<skill-name>/` directory containing `SKILL.md` and its owned resources, with strict frontmatter. Only export a standalone-supported skill. |
| Amp hosted export, if needed | Immediate `<skill-name>/` child directories containing text resources. Publishing remains a separate action. |

A dual-manifest package is a recommended structure based on each host's documented entry point. It has not been installed in both products in this investigation. Test it before declaring that one ZIP serves both. Native MCP formats also differ: OpenAI's portable format uses root `mcp.json`; Claude uses `.mcp.json`. Do not rename one into the other without translating and validating its schema. [OpenAI packaging](https://developers.openai.com/plugins/build/plugins), [Claude packaging](https://claude.com/docs/plugins/build.md).

Keep generated archives outside skills.sh discovery. The source catalogs must reference files present in Git, not an ignored `dist/` directory that consumers do not have. A release archive is a separate download route, not an excuse for a broken repository marketplace.

### Alternatives and tradeoffs

| Approach | Benefit | Cost | Recommendation |
| --- | --- | --- | --- |
| Keep source layout, add thin manifests and generated exports | Preserves links and current installation; one instruction source | A small packaging step and target checks | Adopt |
| Move all sources to flat `skills/<name>/` immediately | Conventional plugin shape | Changes paths, docs, fixtures, and tooling without fixing runtime dependencies | Optional later cleanup, not a compatibility prerequisite |
| Maintain a separate skill tree per product | Direct platform-specific editing | Duplicate prose, policy drift, repeated fixes | Reject |
| Put everything in one universal plugin | One install command | Includes unsupported host integrations and unnecessary dependencies | Reject; start with a small tested subset |
| Copy only `SKILL.md` into chat or a custom assistant | Low packaging effort | Loses resources, discovery behavior, updates, and executable workflow guarantees | Describe only as a limited manual fallback |

Do not use `.agents/skills/` or `.claude/skills/` as additional maintained copies of the published collection. Those directories configure agents working on this repository. Retain intentional development links, but keep authoring and consumption roles distinct.

## Implement in independently checkable stages

1. **Codex metadata and installation documentation.** Add `agents/openai.yaml`, preserve explicit invocation policies, describe managed versus editable installation, and retain all existing skill paths. Check metadata consistency and repeat isolated CLI installs.
2. **A curated skill-collection plugin.** Add the root Claude manifest, update the Claude marketplace, and add an OpenAI catalog that excludes native mods. Validate paths, names, dependency closure, and version agreement. Test actual selection and invocation in both coding agents.
3. **Desktop-ready exports.** Build strict standalone ZIPs and conventional plugin packages from the same source. Inspect archive paths, resource inclusion, frontmatter, dependency closure, and absence of secrets. Test a small conversational subset in Claude chat, Cowork, ChatGPT desktop, and ChatGPT web through supported plugin routes.
4. **Versioned releases and broader support.** Publish archives and checksums only after the installation and workflow tests pass. Expand support one capability-dependent workflow at a time. Public-directory submission is a separate approval and review process.

Keep the existing live skills CLI check. Add a pinned installer smoke test for repeatability and retain the latest-version check to detect upstream changes. Neither substitutes for workflow evaluation.

Useful acceptance scenarios include an explicit-only skill that must not trigger from a merely related request, a skill with bundled references, a workflow with a required companion skill, and a missing-tool case that must stop honestly rather than invent an API.

## Delivery and remaining uncertainty

This investigation changes only this research note. It does not modify skills, manifests, installation settings, or release automation. Nothing has been committed, pushed, uploaded, or published.

Local discovery and a selected file installation were exercised. Codex runtime behavior, Claude account uploads, Cowork execution, ChatGPT plugin installation, and dual-manifest package acceptance remain unverified. Account policy, plan, client version, and mode can restrict documented features.

The subsequent [whole-library audit and adjustment plan](../plans/skill-maintenance-adjustments.md) identifies correctness and authorization defects to fix before expanding distribution. After those fixes, begin with metadata and one curated plugin, not a repository-wide move or a promise that every skill works everywhere.
