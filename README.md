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
| [`agent-handoff`](skills/scoussens-skills/agent-handoff/SKILL.md) | Write a handoff another agent or person can act on without coming back to ask a question — opening with a preflight that proves the state still holds, carrying only the context and decisions that are load-bearing for what remains, and putting the remaining work in a dependency-mapped action table with a completion criterion on every row. Load this only when the user explicitly asks for a handoff — "write a handoff", "hand this off", "brief the next session", "I'm running out of context, write this up", "package this for a subagent", "document where we got to so someone else can pick it up". Do not load it to summarise a conversation, to write a status update or a standup note, to plan work nobody has started, or to write a commit message or pull request description; answer those directly instead. |
| [`business-rules-catalogue`](skills/scoussens-skills/business-rules-catalogue/SKILL.md) | Finds where a repository's business logic lives, derives the rules its code actually enforces, has a second reader check them, and delivers a tree explorer in which business owners mark each rule correct or wrong and export corrections for engineering. Load this only when the user explicitly asks for such a catalogue or its discovery — "derive the business rules", "catalogue the business logic", "where does our business logic live", "business rules review for the product team", "refresh the rules explorer". Do not load it to explain one function, review a pull request, or document an API; answer those directly instead. |
| [`dashboard`](skills/scoussens-skills/dashboard/SKILL.md) | Renders one status file into a self-contained HTML status page for a non-technical reader and keeps it current in place at a destination the user chooses. Any producer feeds it through the same contract — an orchestrate loop, a single task that spawned subagents, a thread that spawned child threads. Use when asked for a "dashboard for this run", a "status page for these threads", or to "show me where the subagents are", and when a coordinating skill needs to present progress as one page. Do not load it to decide what the status is; the producer owns the record, and this skill draws it. |
| [`designing-questionnaires`](skills/scoussens-skills/designing-questionnaires/SKILL.md) | Researches requirements, coordinates category research when needed, and reviews feedback through a concise questionnaire with a JSONL planning handoff. Use when asked to collect team feedback on requirements, create a design questionnaire, or apply responses and republish the same questionnaire. |
| [`explain-to`](skills/scoussens-skills/explain-to/SKILL.md) | Fit an explanation of a concept, problem, or change to one named reader — choose the audience, the altitude, an anchor analogy with its twist, the output type, and whether the reader must operate it, reuse known settings and ask only consequential open choices, then hand sentences to speak-clearly and the medium to the harness's page or view skill. Other skills with a reader or output choice call this step instead of asking their own way. Use when asked to explain something to a named audience ("explain this to the PM", "write it up for the data engineers", "make this understandable to a customer"), to teach a concept, to write an overview or walkthrough for someone outside the code, or when the user says the last explanation was too technical or too vague. Do not load it for a one-line factual answer, a commit message, or a change summary for the developer who made it; answer those directly instead. |
| [`harness-discovery`](skills/scoussens-skills/harness-discovery/SKILL.md) | Discovers what the current agent harness can do — independent threads or sessions, subagents, monitoring and wake-ups, skill loading, instruction files, structured questions, model choice, and HTML publishing destinations — plus the repository's ticket conventions, and saves sourced observations keyed by harness name. Load this when pstack-sync, dashboard, or another skill needs discovery, or when the user names /harness-discovery to refresh facts. Do not run it as the first step of a task that only needs one saved fact. |
| [`meeting-index`](skills/scoussens-skills/meeting-index/SKILL.md) | Index a period of recorded meetings — the threads that carried across them, a searchable per-meeting ledger, and what got decided, who owns it, and what is at risk — reading from Plaud, or any source that can list recordings and return per-meeting notes. Load this only when the user explicitly asks for such an index — "index my meetings from last week", "what did we discuss about the migration", "recap my recordings this sprint", "digest my calls with that client", "what came out of this month's meetings". Do not load it to summarise a single meeting, to answer one factual question about something that was said, to take notes on a call in progress, or to write minutes — answer those directly instead, because this sweeps every recording in a window and costs a lookup per meeting. |
| [`optimize-ci`](skills/scoussens-skills/optimize-ci/SKILL.md) | Evaluates, designs, and improves a repository's CI architecture for trustworthy feedback, runner cost, and maintainability while preserving merge and release contracts. Use when the user asks to audit or speed up CI, reduce CI cost, redesign a pipeline, or design CI for a repository without an existing pipeline. Supports GitHub Actions, GitLab CI, and other providers. Do not load for one failing build, one flaky test, or a narrow workflow syntax question. |
| [`picking-skills`](skills/scoussens-skills/picking-skills/SKILL.md) | Opens a reusable searchable skill picker and copies an exact-source loading instruction. Use for submitted /skills messages, a &lt;skill&gt; placeholder anywhere in a message, or requests to browse and choose skills. |
| [`pr-detail`](skills/scoussens-skills/pr-detail/SKILL.md) | Retrospective on one pull request — a timeline of how it actually went, a ledger of what every reviewer said and whether it was acted on, and a scored evaluation of the execution, published as an HTML artifact. Load this only when the user explicitly asks how a PR went — "how did this PR go", "review the process on #101", "retrospective on this pull request", "how did this developer handle that change", "why did this PR take three weeks". Do not load it to teach the code a PR changed, to produce a review verdict on something still open, or to recap a period of merged work; answer those directly instead. |
| [`pr-digest`](skills/scoussens-skills/pr-digest/SKILL.md) | Recap every pull request merged to a branch over a period as one HTML artifact — grouped by theme, each tied to its issue-tracker ticket, explained both for the user and for the codebase, and closed with what the period adds up to; optionally covering what is still open and in review. Load this only when the user explicitly asks for such a recap — "what shipped this week", "digest the PRs merged this sprint", "release notes for last month", "what landed on staging since the cut", "catch me up on recent development". Do not load it to explain one pull request, to write a commit message, or to review anything still open; answer those directly instead. |
| [`pr-review-round`](skills/scoussens-skills/pr-review-round/SKILL.md) | Work a queue of open pull requests end to end — every non-draft PR against a base branch, oldest first, each reviewed at a depth scaled to its risk, every finding verified at the PR's current head rather than relayed. Report readiness; approve, dismiss, or land only within the user's authorized scope. Load this only when the user explicitly asks to work the queue — "review round", "work through the open PRs", "review everything targeting main", "clear the review queue", "triage the PR backlog and merge what's ready". Do not load it to review a single pull request, to recap what merged recently, or to explain a change to someone; answer those directly or reach for a single-PR skill instead. |
| [`pr-teacher`](skills/scoussens-skills/pr-teacher/SKILL.md) | Teach one pull request as an interactive artifact — the problem it solved, how its mechanism actually works, a map of where every changed file sits and why, something the reader can operate rather than only read, and a grounded self-check. Load this only when the user wants to understand or be taught a specific PR — "teach me PR 412", "explain this pull request", "help me understand what #1234 does", "walk me through this change", "I have to review this and I don't know the codebase", "quiz me on this PR", or when they paste a PR URL and ask what it does. Do not load it to recap a period of merged work, to produce a review verdict, or to answer one narrow factual question about a diff; answer those directly instead. |
| [`pstack-sync`](skills/scoussens-skills/pstack-sync/SKILL.md) | Sync a managed skill set, pstack by default or any set under `sets/`, from its upstream repository, with the skills and subagent definitions they hand off to, into this harness's shared skills — adding new, updating changed, and removing retired skills — and adapt Cursor-specific features to what the harness supports, replaying recorded adaptations so a fresh install does not re-adapt. Load this only when the user explicitly asks to sync or update pstack — "sync pstack", "update pstack", "pull the latest pstack skills", "install pstack for this harness". Do not load it to install or edit one skill no set hands off to, to sync a repository that has no set file, or to change what a synced skill says upstream; answer those directly instead. |
| [`release-brief`](skills/scoussens-skills/release-brief/SKILL.md) | Turn a window of shipped work into a brief for a non-technical stakeholder — verified against what actually reached production, grouped by consequence, referenced back to issue-tracker IDs and pull request numbers, and delivered as a themed Artifact page or Markdown. Load this only when the user explicitly asks for such a brief — "write a release brief", "board update", "brief the client on this sprint", "stakeholder summary of what we shipped". Do not load it to answer what changed recently, to generate a changelog or technical release notes, to summarise a single pull request, or to write a commit message; answer those directly instead. |
| [`speak-clearly`](skills/scoussens-skills/speak-clearly/SKILL.md) | Write human-facing prose in Google developer style — named actors, condition-first sentences, timeless tense, no filler. Use when drafting docs, READMEs, comments, commit messages, PR descriptions, error messages, or UI copy; when editing existing prose; or when asked to make writing clearer, tighten wording, or fix tone. |
| [`visualize-spec`](skills/scoussens-skills/visualize-spec/SKILL.md) | Turn a spec into a throwaway HTML page — problem, outcome, workflow, pieces and seams, data layer, file layout, tests, and validation plan — themed to the repository and opened locally or published wherever the agent can, so a developer can check it delivers what they want. |
| [`work-proposal`](skills/scoussens-skills/work-proposal/SKILL.md) | Turn a body of scoped work into a client-ready proposal — effort and cost grounded in the actual codebase rather than ticket titles, priced against whatever commercial agreement already exists, with anything not yet knowable named rather than averaged into a range, and delivered as a themed Artifact page, a PDF, or email-ready Markdown. Use when the user asks to scope and price work — "write a proposal", "what would it take to build X", "quote this work", "put together an SOW", "estimate this epic for the client", "how much for phase 2". Do not load it to estimate one ticket, to plan a sprint for an internal team, or to answer how long a single change takes; answer those directly instead. |
| [`working-tickets`](skills/scoussens-skills/working-tickets/SKILL.md) | Keeps tickets accurate throughout execution using the repository's own ticket standards, concise comments, status changes, title and body cleanup, and tags. Use whenever the agent is told to work a ticket or issue, is assigned one, resumes one, or creates or picks up one to work on its own. For a parent ticket or epic, plans and works every in-scope child in dependency order with the same hygiene. Applies to hosted and file-based trackers. Not for read-only ticket lookups or drafting tickets that the agent is not taking on. |
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
