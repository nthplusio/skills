# Install skills and test candidate packages

Use one installation route per skill. A copied skill and a managed plugin can
both appear in a selector; neither Codex nor Claude merges their instructions.
Back up local edits before replacing a copy or switching routes. Remove the old
installation only after checking its source and confirming the replacement.

**Target-client behavior is unverified.** This repository checks source metadata,
archives, and isolated file installs. It does not claim that a ChatGPT, Codex,
Claude Chat, Cowork, or Amp account has accepted and executed these exports.
Documented host support is not a result from this collection.

## Preferred routes

| Product or mode | Preferred route | Updates and limits |
| --- | --- | --- |
| skills.sh and other coding agents | `npx skills add nthplusio/skills`; select skills and the actual agent. The hosted pack in the README is an alternative. | `npx skills check` checks tracked installs; `npx skills update` refreshes them. Review before updating editable copies. Pack listings and CLI discovery do not prove runtime support. |
| Codex CLI and IDE | For file installation, use `npx skills add nthplusio/skills --skill speak-clearly --agent codex --copy`. The generated sidecar preserves invocation policy. | Project copies live in `.agents/skills`; user copies use the CLI's global route. Codex can list duplicate names from different scopes. Refresh the chosen route, not both a copy and a plugin. |
| Codex managed plugins | The curated `.agents/plugins/marketplace.json` lists only `nthplusio-coding-agent`. Add a local checkout with `codex plugin marketplace add /absolute/checkout`. | `codex plugin marketplace upgrade nthplusio-skills` refreshes the source. Client installation, root-manifest fallback and exact selected membership still need a target-client check. Prefer the conventional generated folder for acceptance testing. This is not the universal public directory. |
| Claude Code | After the change reaches your source, add its marketplace and install `nthplusio-coding-agent@nthplusio`. For this unpushed work, add the local checkout, not GitHub main. | Use `/plugin marketplace update nthplusio` and `/plugin update nthplusio-coding-agent@nthplusio`. The package version controls managed updates; bump the single `package.json` version and regenerate metadata for a release. Do not edit plugin caches. |
| ChatGPT desktop standalone skills | Test only the four conversational candidates with the app's supported skill/local-marketplace workflow. | Standalone skills are documented for desktop, Codex CLI and IDE, not as a universal web upload route. Local plugin installs are cached copies; update the source and refresh/restart as the host documents. Actual account acceptance is unverified. |
| ChatGPT Chat and Work, including web/mobile | Use the conversational plugin candidate through a supported local/workspace testing route or a separately approved directory submission. | A GitHub repository, skills.sh pack, or generated ZIP is not a published OpenAI directory entry. Workspace publication and public submission are distinct actions. Test Chat and Work separately; tools available in one mode do not transfer to the other. |
| Claude Desktop Chat and claude.ai | For local testing, use a conversational standalone ZIP or **Customize → Plugins → Add → Upload plugin** with the conversational plugin ZIP. | Account/organization eligibility can restrict installation. Replace/update through that same account route; uploading a ZIP is not an automatic Git update subscription. Account plugins can sync to Claude Code; terminal installs do not upload to the account. |
| Claude Cowork | Test the conversational plugin separately in Cowork through account plugin installation. | Cowork has different tools and component support from Chat. Do not promote the coding-agent package merely because Cowork accepts a folder. Actual execution remains unverified. |
| Amp project | Install the complete canonical folder with `amp skill add /absolute/checkout/skills/scoussens-skills/speak-clearly`. | Refresh the chosen source with an explicit overwrite only after preserving edits; reload skills. A local/global install inside an orb is not cross-orb publication. |
| Amp hosted personal/workspace skills | Copy complete selected directories as immediate children of the chosen Skills repository, with required companions. Review, commit and push only with authorization. | Hosted publication is a separate approved write; it reaches other sessions after reload/new thread. Binary resources are not served. This builder does not publish or reuse pstack-sync. |

For a single-skill Git install, also select its required companions. For example:

```bash
npx skills add nthplusio/skills --skill pr-teacher explain-to --agent codex --copy
```

The catalog records nine required `explain-to` callers. Questionnaire manual and
static intake do not require it. `explain-to` can use `speak-clearly` and
destination discovery conditionally; they are not required closure. No sidecar
pretends to install companion skills automatically.

The five manual-only workflows are `pr-detail`, `pr-digest`, `pr-review-round`,
`pr-teacher`, and `visualize-spec`. Use explicit host invocation: `$name` in
Codex or the plugin's namespaced slash command in Claude Code. Their Codex policy
is `allow_implicit_invocation: false`, paired with Claude's source flag. A clear
natural-language task request is enough for `task-intent` skills, while
`context-helper` skills may assist another authorized task. Invocation never
grants merge, send, tracker-edit or publication authority by itself.

## What the builder exports

Run from a reviewed checkout with Node 22+, Python 3 and Git:

```bash
npm ci --ignore-scripts
npm run distribution:sync
# Review and stage the generated metadata and any new owned resources.
npm run validate
npm run test:distribution
npm run build:distribution
npm run check:installed
```

`package.json` supplies the version (`0.0.0` is a local candidate version, not a
release). `dist/` is ignored by Git and source discovery. The build replaces only
a directory marked as its own output. It produces:

- `dist/plugins/nthplusio-coding-agent/`: 18 skills with required companions,
  excluding the Amp picker and administrative pstack-sync.
- `dist/plugins/nthplusio-conversation/`: `speak-clearly`, session-only
  `writing-in-voice`, `explain-to` chat, and conversation-only `agent-handoff`.
  The complete canonical instructions remain intact; other modes retain their
  prerequisites and are not advertised as conversational support.
- Two versioned plugin ZIPs, each with one enclosing directory, root
  Agent Plugins `plugin.json`, `.claude-plugin/plugin.json`, conventional
  `skills/<name>/` layout, README, and licenses.
- Four versioned standalone ZIPs under `dist/`, each containing exactly one
  `<name>/` with strict standard frontmatter and complete owned resources.
  Their unpacked forms are under `dist/standalone/`.
- `dist/SHA256SUMS` for all six archives.

Strict targets cannot enforce the five manual-only policies using instruction
text alone, so the builder refuses those workflows. It also refuses a standalone
workflow with required companions. Native `context-statusline`, Doorbell and
Doorbell Grant remain separate Claude Code mods; they are not in the OpenAI
catalog or either archive. Doorbell's messaging skill remains plugin-only.
`good-css` remains a development dependency. Private voice profiles and
credentials are not part of these reusable packages.

These are **local candidate exports**, not uploaded release assets, approved
directory entries, or tested desktop releases. Publication needs explicit
authorization and target-mode evidence. Do not upload the coding-agent ZIP to a
strict chat target to bypass a policy gate.

## Three independent evidence layers

1. **Deterministic contracts:** `npm run validate`, `npm run test:skills`, and
   `npm run test:distribution`. Archive tests inspect actual ZIP contents,
   resources, licenses, closure, policy and reproducibility. The pinned
   `npm run check:installed` uses `skills@1.7.4` twice in temporary homes/projects,
   copies all 18 skills into Codex/Claude file locations, compares complete
   contents, and runs installed meeting rollup and handoff checks from a foreign
   working directory with spaces. This does not run either agent.
2. **Agent behavior:** `npm run eval:agents -- --list` only lists definitions.
   Without runner results, `--case ID` reports **NOT EXECUTED** and exits 2.
   Use the [evaluation adapter contract](../distribution/agent-evaluation.md)
   to record real execution, including the nine shared-settings cases and
   high-risk authority cases. Static instruction checks and source-copy equality
   tests are not evidence of model behavior.
3. **Target-product delivery:** Install the actual generated artifact and run
   the selected case in the named product/version/mode. Inspect interactive
   HTML in that product and fresh PDFs visually. No such results are bundled.

`DISABLE_TELEMETRY=1 npm run check:builder` separately runs **skills@latest**
discovery to catch upstream changes; it is not the pinned installation check.
Run `npm run test:browser` explicitly for the business-rules explorer's two
Chromium cases. That command fails if agent-browser is absent rather than
silently skipping. The ordinary Python suite keeps its opt-in behavior. Teaching
page interaction and target-product browser cases remain in the agent evaluation
route and must be reported unverified until executed.

After `npm ci --ignore-scripts`, the Claude npm command can still be a stub. Its
supported fallback runs the downloaded native dependency without postinstall:

```bash
node node_modules/@anthropic-ai/claude-code/cli-wrapper.cjs plugin validate .
node node_modules/@anthropic-ai/claude-code/cli-wrapper.cjs plugin validate dist/plugins/nthplusio-conversation
```

Manifest validation is not installation or workflow acceptance. Before publishing,
run the private-terms check with the maintainer's private patterns and review
tracked resource contents; path filters cannot prove text contains no secrets.
