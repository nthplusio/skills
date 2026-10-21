# skills

A [skills.sh](https://www.skills.sh) pack — a collection of reusable skills for
AI coding agents — and a Claude Code plugin marketplace.

## Install

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

| Skill | Description |
| --- | --- |
| [`scoussens-skills/agent-handoff`](skills/scoussens-skills/agent-handoff/SKILL.md) | Write a handoff another agent or person can act on without asking a question — a preflight that proves the state still holds, only the context and decisions that are load-bearing for what remains, and the rest of the work as a dependency-mapped action table. Invoked explicitly. |
| [`scoussens-skills/business-rules-catalogue`](skills/scoussens-skills/business-rules-catalogue/SKILL.md) | Find where a repository's business logic lives, derive the rules its code actually enforces, have a second reader check them, and deliver a tree explorer where business owners mark each rule correct or wrong and export corrections. Asks where the explorer goes and who can see it before publishing. Invoked explicitly. |
| [`scoussens-skills/dashboard`](skills/scoussens-skills/dashboard/SKILL.md) | Render one status file that follows its contract into a self-contained HTML status page for a non-technical reader, choose the destination through `explain-to`'s settings sheet, and keep the page current in place. Any producer feeds it: an orchestrate loop, a task with subagents, a thread with child threads. |
| [`scoussens-skills/explain-to`](skills/scoussens-skills/explain-to/SKILL.md) | Fit an explanation of a concept, problem, or change to one named reader — audience, altitude, anchor analogy with its twist, output type, and whether the reader must operate it — then hand sentences to `speak-clearly` and the medium to the harness's page or view skill. |
| [`scoussens-skills/harness-discovery`](skills/scoussens-skills/harness-discovery/SKILL.md) | Discover what the running harness can do — threads, subagents, monitoring, skills, instruction files, questions, models, and HTML destinations — and the repository's ticket conventions. Save sourced observations by harness name for any skill to read. |
| [`scoussens-skills/meeting-index`](skills/scoussens-skills/meeting-index/SKILL.md) | Index a period of recorded meetings — the threads that carried across them, a per-meeting ledger, and what got decided, owned and left at risk. Reads from Plaud or any source with a listing and per-meeting notes. Invoked explicitly. |
| [`scoussens-skills/optimize-ci`](skills/scoussens-skills/optimize-ci/SKILL.md) | Evaluate, design, or improve repository-specific CI for trustworthy feedback, runner cost, and maintainability. Preserves merge and release contracts, including when designing a pipeline without run history. |
| [`scoussens-skills/picking-skills`](skills/scoussens-skills/picking-skills/SKILL.md) | Open a reusable Amp portal with live skill search by name or description. Choose an exact source and copy its loading request, without injecting the skill's contents. |
| [`scoussens-skills/pr-detail`](skills/scoussens-skills/pr-detail/SKILL.md) | Retrospective on one pull request: a timeline of how it went, a ledger of what each reviewer said and whether it was acted on, and a scored evaluation, published as an HTML artifact. Invoked explicitly. |
| [`scoussens-skills/pr-digest`](skills/scoussens-skills/pr-digest/SKILL.md) | Recap every pull request merged to a branch over a period as one HTML artifact, grouped by theme and tied to its tickets, with what the period adds up to. Invoked explicitly. |
| [`scoussens-skills/pr-review-round`](skills/scoussens-skills/pr-review-round/SKILL.md) | Work a queue of open pull requests oldest first: review each at a depth scaled to its risk, verify every finding at the current head, then approve, unblock, or land it. Invoked explicitly. |
| [`scoussens-skills/pr-teacher`](skills/scoussens-skills/pr-teacher/SKILL.md) | Teach one pull request as an interactive artifact: the problem, how the mechanism works, a map of every changed file, something to operate, and a grounded self-check. Invoked explicitly. |
| [`scoussens-skills/pstack-sync`](skills/scoussens-skills/pstack-sync/SKILL.md) | Sync the pstack skills from `cursor/plugins`, with the skills and subagent definitions they hand off to, into the directory that holds this skill — adding, updating, and removing skills — and adapt Cursor-only features to the running harness, replaying recorded adaptations so a fresh install does not re-adapt. Ships an Amp harness profile and a template for others, and reads harness facts from `harness-discovery`. Invoked explicitly. |
| [`scoussens-skills/release-brief`](skills/scoussens-skills/release-brief/SKILL.md) | Turn a window of shipped work into a brief for a non-technical stakeholder, verified against what actually reached production. Invoked explicitly. |
| [`scoussens-skills/speak-clearly`](skills/scoussens-skills/speak-clearly/SKILL.md) | Write human-facing prose in Google developer style: named actors, condition-first sentences, timeless tense, no filler. |
| [`scoussens-skills/visualize-spec`](skills/scoussens-skills/visualize-spec/SKILL.md) | Turn a spec into a throwaway HTML page — problem, outcome, workflow, pieces and seams, data layer, file layout, tests, and validation plan — with every place the spec is silent marked as a gap, themed to the repository, and opened locally or published where the agent can. Invoked explicitly. |
| [`scoussens-skills/work-proposal`](skills/scoussens-skills/work-proposal/SKILL.md) | Turn a body of scoped work into a client-ready proposal — effort grounded in the codebase, priced against the agreement that already exists, delivered as a themed Artifact, PDF, or email. Invoked explicitly. |

## Claude Code plugins

This repository is also a Claude Code plugin marketplace, named `nthplusio`.
Plugins live in `plugins/`; `.claude-plugin/marketplace.json` lists them.
The pack builder also discovers marketplace plugins' bundled skills. Mark a
plugin-local skill with `metadata.internal: true` to exclude it from normal pack
discovery while keeping it available inside Claude Code.

```
/plugin marketplace add nthplusio/skills
/plugin install <plugin>@nthplusio
```

| Plugin | Description |
| --- | --- |
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
maintain. It walks the `skills/` container directory up to three levels deep
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

These skills keep their saved state in `.nthplusio-skills/` at the root of the
repository they work in. One script, `state.py` in `harness-discovery`, checks
it and resolves a harness from it.

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
  loading, so it runs only when invoked by name.
- A skill whose output can take more than one form, or serve more than one
  reader, does not ask its own question about it. It loads `explain-to` and
  runs its settings sheet (`explain-to/references/settings-sheet.md`), passing
  the settings it fixes and any extra outputs it can produce, and builds from
  what the user agreed. The sheet shows every inferred choice as a
  recommendation with its evidence; *go* accepts them all.
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
npm install
npm run validate
```

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
