# skills

A [skills.sh](https://www.skills.sh) pack — a collection of reusable skills for
AI coding agents — and a Claude Code plugin marketplace.

## Install

For product-specific routes, companion requirements, update behavior and limits,
read [installation and candidate packages](docs/installation.md). Use one route
per skill; copied skills and managed plugins can otherwise appear twice.

Install the [pack](https://www.skills.sh/docs/packs):

```bash
npx skills add https://skills.sh/p/LnXuSpHo8Jw01lUf
```

To install from this repository instead, bypassing the pack:

```bash
npx skills add nthplusio/skills
```

To install a single skill:

```bash
npx skills add nthplusio/skills --skill speak-clearly
```

## What's in here

<!-- Generated from SKILL.md by distribution:sync. -->

| Skill | Description |
| --- | --- |
| [`agent-handoff`](skills/scoussens-skills/agent-handoff/SKILL.md) | Writes actionable handoffs with a state-checking preflight, essential context, and dependency-ordered actions with completion criteria. Use only when explicitly asked to write a handoff, brief the next session, or package work for a subagent or person. Not for conversation summaries, status or standup updates, plans for unstarted work, commit messages, or PR descriptions. |
| [`business-rules-catalogue`](skills/scoussens-skills/business-rules-catalogue/SKILL.md) | Derives code-enforced business rules, has a second reader check them, and builds an explorer for business owners to review and export corrections. Use only when explicitly asked to catalogue business logic, find where it lives, or refresh the rules explorer. Not for explaining one function, reviewing a PR, or documenting an API. |
| [`dashboard`](skills/scoussens-skills/dashboard/SKILL.md) | Renders a producer-owned status file as a self-contained HTML page for non-technical readers and refreshes it at the user's chosen destination. Use for a run dashboard, thread status page, subagent progress view, or a coordinating skill's report. The producer determines status; this skill renders the record rather than judging it. |
| [`designing-questionnaires`](skills/scoussens-skills/designing-questionnaires/SKILL.md) | Researches requirements, coordinates category research when needed, and reviews feedback through a concise questionnaire with a JSONL planning handoff. Use when asked to collect team feedback on requirements, create a design questionnaire, or apply responses and republish the same questionnaire. |
| [`explain-to`](skills/scoussens-skills/explain-to/SKILL.md) | Fits explanations to a named reader and resolves audience/output settings for caller skills, reusing known choices. Use to explain to a PM or customer, teach a concept, write an overview for someone outside the code, or revise an explanation that is too technical or vague. Not for one-line facts, commit messages, or change summaries for the developer who made the change. |
| [`harness-discovery`](skills/scoussens-skills/harness-discovery/SKILL.md) | Discovers agent capabilities and repository ticket conventions, saving sourced facts by harness. Covers sessions, subagents, wake-ups, skills, instructions, questions, models, and HTML destinations. Use when pstack-sync, dashboard, or another caller needs discovery, or for /harness-discovery. For one saved fact, read that field instead of starting a full survey. |
| [`meeting-index`](skills/scoussens-skills/meeting-index/SKILL.md) | Indexes recorded meetings across a period into shared themes, a searchable ledger, decisions, owners, and risks. Reads Plaud or another recordings-and-notes source. Use only when explicitly asked to index meetings, recap recordings, or digest calls across a period or topic. Not for a single-meeting summary, one factual lookup, live note-taking, or minutes. |
| [`optimize-ci`](skills/scoussens-skills/optimize-ci/SKILL.md) | Evaluates, designs, and improves a repository's CI architecture for trustworthy feedback, runner cost, and maintainability while preserving merge and release contracts. Use when the user asks to audit or speed up CI, reduce CI cost, redesign a pipeline, or design CI for a repository without an existing pipeline. Supports GitHub Actions, GitLab CI, and other providers. Do not load for one failing build, one flaky test, or a narrow workflow syntax question. |
| [`picking-skills`](skills/scoussens-skills/picking-skills/SKILL.md) | Opens a reusable searchable skill picker and copies an exact-source loading instruction. Use for submitted /skills messages, a &lt;skill&gt; placeholder anywhere in a message, or requests to browse and choose skills. |
| [`pr-detail`](skills/scoussens-skills/pr-detail/SKILL.md) | Produces an HTML retrospective on one PR with its timeline, reviewer feedback and outcomes, and an evidence-based execution score. Use only for explicit requests about how a PR went, its review process, or why it took so long. Not for teaching the code, judging an open PR's merge readiness, or recapping a period of merged work. |
| [`pr-digest`](skills/scoussens-skills/pr-digest/SKILL.md) | Builds a themed HTML recap of PRs merged to a branch over a period, optionally including ready-for-review PRs, or an open-PR inventory including drafts with no time window. Use only for explicit requests for what shipped this week, a merged-PR digest, or what's open or in the backlog. Not for one-PR explanations or reviews, commit messages, or review-queue assessments or mutations. |
| [`pr-review-round`](skills/scoussens-skills/pr-review-round/SKILL.md) | Reviews every non-draft PR against a base branch, oldest first, with risk-scaled depth and findings verified at the current head. Reports readiness; approves, dismisses, or merges only within explicit authority. Use only when asked for a review round, queue triage, or to clear the review queue. Not for a single-PR review, a merged-work recap, or explaining a change. |
| [`pr-teacher`](skills/scoussens-skills/pr-teacher/SKILL.md) | Teaches one PR through an interactive HTML artifact with the problem, mechanism, changed-file map, operable example, and grounded self-check. Use only when asked to explain a specific PR, walk through its change, or quiz the reader on it. Not for a merged-period recap, a review verdict, or one narrow factual question about a diff. |
| [`pstack-sync`](skills/scoussens-skills/pstack-sync/SKILL.md) | Syncs pstack or another configured set from upstream, including skill and subagent dependencies, and replays harness adaptations. Use only when explicitly asked to sync, update, or install a managed set for this harness. Not for an unrelated single skill, a repository without a set file, or upstream content edits. Sync does not authorize publication or contribution. |
| [`release-brief`](skills/scoussens-skills/release-brief/SKILL.md) | Writes non-technical release briefs from verified production evidence, grouped by consequence and linked to tickets and PRs, as HTML or Markdown. Use only for explicit release-brief, board-update, or client/stakeholder shipped-work requests. Not for general recent-change recaps, changelogs, technical release notes, single-PR summaries, or commit messages. |
| [`speak-clearly`](skills/scoussens-skills/speak-clearly/SKILL.md) | Write human-facing prose in Google developer style — named actors, condition-first sentences, timeless tense, no filler. Use when drafting docs, READMEs, comments, commit messages, PR descriptions, error messages, or UI copy; when editing existing prose; or when asked to make writing clearer, tighten wording, or fix tone. |
| [`visualize-spec`](skills/scoussens-skills/visualize-spec/SKILL.md) | Turn a spec into a throwaway HTML page — problem, outcome, workflow, pieces and seams, data layer, file layout, tests, and validation plan — themed to the repository and opened locally or published wherever the agent can, so a developer can check it delivers what they want. |
| [`work-proposal`](skills/scoussens-skills/work-proposal/SKILL.md) | Drafts client proposals with code-grounded effort, agreed commercial terms, and explicit unknowns, as HTML, PDF, or email-ready Markdown. Use when asked to scope and price work, quote a phase or epic, or write a proposal or SOW. Not for estimating one ticket, internal sprint planning, or timing a single change. Drafting does not authorize tracker edits, sending, or publication. |
| [`working-tickets`](skills/scoussens-skills/working-tickets/SKILL.md) | Maintains hosted or file-based tickets under repository policy throughout execution, including comments, status, title, body, and tags. Use when assigned a ticket, resuming one, or creating or picking one up to work on. For a parent or epic, plans and works every in-scope child in dependency order. Not for read-only lookups or drafting tickets the agent is not taking on. |
| [`writing-in-voice`](skills/scoussens-skills/writing-in-voice/SKILL.md) | Drafts and revises writing using a personal or project voice profile, learns from corrections, and formats for the destination. Use when asked to write in my voice, learn my writing style, remember a writing preference, or adapt a voice-led draft for email, Teams, Slack, text messages, documents, or public posts. Not a source of facts or permission to send. |

## Claude Code plugins

This repository is also a Claude Code plugin marketplace, named `nthplusio`.
Native integrations live in `plugins/`; `.claude-plugin/marketplace.json` lists
them separately from the root `nthplusio-coding-agent` skill collection. The
OpenAI catalog excludes the native Claude mods. Source manifests reference
tracked canonical paths, never generated `dist/` files.
The pack builder also discovers marketplace plugins' bundled skills. Mark a
plugin-local skill with `metadata.internal: true` to exclude it from normal pack
discovery while keeping it available inside Claude Code.

```
/plugin marketplace add nthplusio/skills
/plugin install <plugin>@nthplusio
```

| Plugin | Description |
| --- | --- |
| [`nthplusio-coding-agent`](docs/installation.md) | Eighteen skill candidates with required companions and Codex/Claude invocation metadata. Target-client behavior remains unverified. |
| [`context-statusline`](plugins/context-statusline/README.md) | A card above the prompt: the model, the context window in tapered colour bands, prompt cache warmth, and the git repo and branch, collapsing to fit any terminal width. |
| [`doorbell`](plugins/doorbell/README.md) | Directory-bound messaging through Doorbell's public MCP connection, with local execution authority, explicit leases, and bounded optional Stop continuation. |
| [`doorbell-grant`](plugins/doorbell-grant/README.md) | Approves doorbell's own read-only inbox calls at the permission check, so its background refresh works in auto mode. Installed with doorbell. |

To add a plugin, put it in `plugins/<name>/` with its
`.claude-plugin/plugin.json`, add an entry to `.claude-plugin/marketplace.json`,
and check both with `claude plugin validate .` and
`claude plugin validate plugins/<name>`.

## Amp skill picker

With `picking-skills` installed, send `/skills` in Amp web chat to show the
live picker inside the conversation. Send `/skills code review` to prefill a
search, or ask **Show the skill picker**. Search filters as you type across
names, descriptions, and source paths. Choose a skill, click **Copy**,
then paste into Amp and add your task. **Details** reveals the full description,
exact source, and prepared request; search and Copy stay visible in small windows.

The optional [Amp plugin](plugins/amp-skill-picker/README.md) adds
**Skills: Open picker** to the command palette. It launches the same picker
without an agent turn and presents a native dialog with an **Open skill
picker** link. It also detects submitted `/skills` and `<skill>` requests in
code. Publish the plugin separately to your Amp User or Workspace Plugins
repository; installing the skill does not install the plugin.

To keep your task with the selection, put a literal `<skill>` anywhere in your
message, for example: `Use <skill> to tighten the wording in README.md.` Send
it to request the picker and defer the task. Choose a skill and
click **Copy**. The result keeps your message, replaces every `<skill>`
with the same selected name, and prepends the exact-source loading instruction.
Paste the completed message into Amp and send it. No skill body is included.

The picker is a bundled page served by one supervised service per orb/project.
Opening the page or clicking **Refresh** reads a fresh `amp skills list --json`
inventory. Filtering runs in the browser; typing does not invoke the agent.
The launcher reuses a healthy service and returns only a portal link, keeping
HTML and the skill list out of the conversation. Without the plugin, the agent
interprets `/skills` and `<skill>` after submission. With it, a hook prepares
the request and instructs the agent to embed the same portal and wait, without
showing a dialog first. Both chat routes take an agent turn; waiting still
relies on agent instructions. Clients without inline portals can open the
portal link. Neither route provides main-textbox autocomplete. Nothing edits
the textbox or sends automatically.
If clipboard access is blocked, the page selects the text for manual copying.
Each saved task has its own opaque link and expires after 24 hours. Portal
access follows the thread's permissions; keep the portal private.

This checkout links the skill into `.agents/skills/`. The launcher, server, and
page ship together; they need an Amp Linux orb, Node.js 22+, and `flock`, not a
custom plugin or npm install. Its tests run with `npm run test:skills`.

For cross-orb use, publish the whole package as top-level `picking-skills/` in
your Amp User or Workspace Skills repository (`amp skills repositories` lists
destinations). Publishing requires approval; a local `--global` install does
not distribute across orbs. New threads load published skills automatically;
reload skills in an existing thread. Every orb discovers its own inventory and
source directories rather than sharing another orb's paths or portal URL.

## Layout

The skills CLI discovers skills by convention — there is no manifest to
maintain for CLI discovery. The [distribution catalog](distribution/catalog.json)
records reviewed bundle membership, activation, companions and mode requirements;
`npm run distribution:sync` generates host metadata and the skill index above.
The CLI walks the `skills/` container directory up to three levels deep
looking for `SKILL.md`, and a shallower `SKILL.md` shadows any nested beneath
it.

```
skills/
  <skill-name>/
    SKILL.md        required — frontmatter + instructions
    references/     optional — detail loaded on demand
    scripts/        optional — executable helpers
```

Flat (`skills/<name>/`) and categorised (`skills/<category>/<name>/`) layouts
are both supported.

## Coordinating work

Fan-out of a large task across worker threads comes from Cursor's `orchestrate`
plugin, which `pstack-sync` installs and adapts as its `orchestrate` set: a root
planner decomposes a goal into tasks, isolated workers, subplanners and
verifiers take them, and they report upward through handoff files. Tickets are
optional inputs the root planner reads. The loop keeps its state in
`.orchestrate/<slug>/` (`plan.json`, `state.json`, `handoffs/`), outside the
`.nthplusio-skills/` folder described below.

The `dashboard` skill draws one page from a status file that follows its
contract (`dashboard/references/status-contract.md`), so the same page serves
an orchestrate loop, a task with subagents, or a thread with child threads.
`harness-discovery` records what the running harness can do, keyed by harness
name, for `pstack-sync`, `dashboard` and any skill that publishes HTML. Name
`/harness-discovery` to refresh facts; `pstack-sync` loads discovery itself.

Earlier versions of this pack shipped `orchestration-setup` and
`orchestration-run`, a coordinator of ticket-owned threads with its own
`orchestration.json` and run records. They are retired; delete the two skill
folders from your skills directory. `harness-discovery` was named
`orchestration-discovery` before that; there is no alias for either.

`npm run test:skills` runs every skill's `evals/test_*.py`, including
`harness-discovery`'s state tests and the `dashboard` renderer tests.

### Saved state

The discovery and sync skills keep their saved state in `.nthplusio-skills/`
at the root of the repository they work in. One script, `state.py` in
`harness-discovery`, checks it and resolves a harness from it.

`writing-in-voice` defaults to personal profiles at
`~/.config/agents/voices/default.md`, outside project and shared skill repositories.
An explicitly declared project voice can live at `.agents/voice/profile.md`
in the consuming project, never in this reusable skill repository. Local-only
users manage backup and Git tracking; fresh machines and orbs need restoration.
For cross-session durability, users can opt into a separate, unshared personal
`remembering-my-voice` package in their User Skills repository. Its published
profile takes precedence over the local default; confirmed updates require
explicit or recorded standing authorization to push. See
[hosted personal profiles](skills/scoussens-skills/writing-in-voice/references/hosted-profile.md).
The reusable skill ships only generic instructions, a versioned questionnaire,
formatting references, and synthetic evaluation cases.

| File | Written by | Read by | In Git |
| --- | --- | --- | --- |
| `discovery.json` | `harness-discovery` | Every skill that needs harness facts | Yes, sanitized |
| `harness-discovery/registry/<slug>.json` (in the pack, not in `.nthplusio-skills/`) | `harness-discovery` `export` | `harness-discovery` `seed`, which copies it into `discovery.json` and checks its fingerprint | Yes; one shared entry per harness |
| `pstack-sync/manifest.json`, `transform.json`, `LICENSE-*`, `harness/<slug>.md` | `pstack-sync` | `pstack-sync` | Yes |

```bash
python3 <skill>/scripts/state.py check
python3 <skill>/scripts/state.py resolve --harness amp
```

A harness is named by its discovered key, such as `Claude Code`, or by that
key's slug, `claude-code`.

Earlier versions kept this state in `.orchestration/`. `harness-discovery`
runs `state.py migrate` before it reads anything. It moves `discovery.json`,
upgrades it when its schema is older, refuses to overwrite a conflicting file,
and leaves the retired skills' `config.json` and run folders where they are,
listed in its summary under `left`, for you to delete.

To change a saved file's shape, bump its `schema_version`, add one upgrade step
to `UPGRADES` in `state.py`, and add a fixture of the old shape under
`harness-discovery/evals/fixtures/<legacy folder without its dot>/`. To move
the files, add the old folder to `LEGACY_DIRS`. The migration test migrates
every fixture and checks the result.

## Adding a skill

```bash
mkdir -p skills/my-new-skill
$EDITOR skills/my-new-skill/SKILL.md
npm run validate
npm run check:builder
```

`SKILL.md` requires two frontmatter fields:

```yaml
---
name: my-new-skill
description: What it does. Use when <trigger>, <trigger>, or <trigger>.
---
```

- `name` — lowercase-with-hyphens, and **must match the directory name**.
- `description` — the only text an agent sees before deciding to load the
  skill, at most 1024 characters. See
  [writing good descriptions](docs/writing-good-descriptions.md).

Other fields follow the [Agent Skills specification](https://agentskills.io/specification):
`license`, `compatibility`, `metadata` with string values, and `allowed-tools`.
The pack uses two extensions that strict validators reject:

- `disable-model-invocation: true` keeps a skill out of Claude Code's automatic
  loading, so it runs only when invoked by name. Generated Codex sidecars carry
  the matching `allow_implicit_invocation: false` policy. Strict standalone
  exports exclude these manual-only workflows rather than dropping the policy.
- A skill whose output can take more than one form, or serve more than one
  reader, can delegate settings to `explain-to`. Reuse settled choices and ask
  only consequential unresolved questions; delivery audience and publishing
  permission remain separate. The questionnaire also has self-contained intake.
  The catalog distinguishes required companions from optional helpers.
- `metadata.needs` lists, comma-separated, the harness capabilities a skill
  reads from `discovery.json`, as dotted paths into one harness entry of
  `harness-discovery/assets/discovery.template.json` (for example
  `artifacts, skills.load`). The validator rejects a path the template does
  not have, so the capability vocabulary has one home.
- `metadata.internal: true` hides a plugin-bundled skill from pack discovery. The
  skills CLI checks for the boolean, so do not quote it.

A skill installs as one directory. Link only to files inside it; copy a file
another skill owns rather than linking across, and add a test that the copies
match.

## Validation

```bash
npm ci --ignore-scripts
npm run validate
npm run test:distribution
npm run build:distribution
npm run check:host-manifests
npm run check:installed
```

These are deterministic metadata, archive and installed-file checks, not
target-product acceptance. `npm run eval:agents -- --list` enumerates scenarios;
the [agent evaluation adapter](distribution/agent-evaluation.md) requires actual
runner evidence and reports missing execution honestly. `npm run test:browser`
explicitly runs the opt-in explorer browser cases and fails without its browser.

The pack builder fails *quietly*: it skips invalid `SKILL.md` files and omits
binary or over-2 MB files without reporting an error, so a broken pack still
installs — just with skills missing. The validator turns those silent omissions
into a non-zero exit, and runs in CI on every push and pull request.

It checks:

- frontmatter parses as YAML, using the same parser the builder uses
- `name` and `description` exist, are strings, and `name` matches its directory
- the Agent Skills limits: `name` up to 64 characters, `description` up to 1024,
  `compatibility` up to 500, and no fields beyond the specification and the
  two extensions above
- relative Markdown links resolve and stay inside the skill directory
- `evals/evals.json` matches its skill and gives every eval a prompt, an
  expected output, assertions, and input files that exist
- no file exceeds 2 MB
- no binary files are committed inside a skill

It warns when `SKILL.md` passes 500 lines or a reference file passes 300 lines
without a `Contents` heading. Skills bundled in `plugins/*/skills/` get the same
checks.

### The private-terms check

```bash
npm run check:private
```

Skills here are installed into other repositories, so no tracked file may name
an employer, client, person, private repository, or private tracker prefix. The
patterns themselves are private, so they never live in this repository. The
check reads one case-insensitive regular expression per line from the
untracked `.private-terms` file, or from the `PRIVATE_TERMS` repository secret
in CI. It reports matches by file, line, and pattern number, never the pattern.
With no patterns configured, it warns and passes.

### The builder-agreement check

```bash
npm run check:builder
```

The validator *encodes* the builder's rules, and encoded rules drift. This
check encodes nothing: it runs the real skills.sh CLI against the checkout and
asserts it finds every skill the repository contains, so it cannot fall out of
step by construction. When the two disagree, it prints the file, the builder's
own reason, and what the gap costs:

```
✗ the builder skipped .../meeting-index/SKILL.md
    YAML parse error: Nested mappings are not allowed in compact mappings at line 2, column 14:
✗ "meeting-index" exists in this repo but the builder did not find it
✗ the builder reported 2 skill(s); this repository contains 3
```

It reaches the network and runs `skills@latest`, so an upstream change can fail
the build without anything here changing. That is the point — upstream changing
the rules is worth being told about — but it is why CI runs it as its own job,
separate from the hermetic validator, so the two failures are never confused.

The validator has one dependency, `yaml`, and that is deliberate. Frontmatter
must be parsed with the parser the builder uses, because a reimplementation
drifts and the drift is silent. A hand-rolled reader here once accepted a
description containing `": "` — which YAML reads as a nested mapping — and
reported three valid skills while the pack shipped two.

### Descriptions cannot contain `": "`

A colon followed by a space makes an unquoted YAML value ambiguous with a
nested mapping, and the whole skill is dropped. Introduce a list of trigger
phrases with an em dash instead:

```yaml
# Breaks the skill, silently
description: Load this when the user asks for an index: "index my meetings".

# Correct
description: Load this when the user asks for an index — "index my meetings".
```

## Licence

[MIT](LICENSE)
