# Skill maintenance audit and adjustment plan

Audited on 2026-10-30 at repository revision [a00fc46](https://github.com/nthplusio/skills/commit/a00fc468f67134352ccb6d2a1cadc297430cfe3d). This is a proposal, not authorization to implement, commit, publish, or install changes.

## Fix incorrect outcomes before expanding distribution

Keep the canonical skill directories. Fix the workflows that can make unauthorized changes or report unsupported conclusions. Then simplify shared setup, declare dependencies and supported modes, and generate platform packages from that source.

The audit covered all 20 public skills, the internal `doorbell-messaging` skill, and the imported development skill `good-css`. The `.agents/skills/picking-skills` symlink is not a second skill. All 22 instruction files were read. Load-bearing references, scripts, and evaluation definitions were inspected selectively. This was not a line-by-line security audit of every bundled application.

The existing organization is adequate for skills.sh discovery. The main maintainability problem is that dependencies, invocation, delivery consent, and capability requirements are encoded differently across workflows. Several executable helpers also contradict their instructions.

Evidence labels in this plan:

- **Reproduced** means executed locally against synthetic input, disposable files, or mocked forge calls.
- **Source-traced** means supported by the inspected instructions or implementation, without a live workflow reproduction.
- **Proposed** means an adjustment to consider during implementation, not existing behavior.
- **Unverified** means no claim of target-product execution or acceptance.

Throughput checkpoint is not applicable to this read-only investigation.

## Seven local probes exposed failures the existing suite misses

These checks used no production data, real merge calls, tracker writes, or publishing services. The HTML probe parsed a harmless injected attribute. It did not execute JavaScript or establish exploitability under a particular host's security policy.

| Reproduced failure | Input and decisive observation | Source |
| --- | --- | --- |
| Review-round retries a write after approval disappears | Mocked `APPROVED+CLEAN`, then `CHANGES_REQUESTED+CLEAN`. `land.py` called enqueue twice. | [Merge loop](../../skills/scoussens-skills/pr-review-round/scripts/land.py#L88-L128) |
| Review-round reports a conflicted PR as landed | Mocked an approved PR becoming `DIRTY`. Output included `all watched PRs landed`. | [Completion reporting](../../skills/scoussens-skills/pr-review-round/scripts/land.py#L115-L139) |
| Review-body links can introduce HTML attributes | A quoted URL produced an anchor with an extra `data-audit="injected"` attribute. | [Markdown renderer](../../skills/scoussens-skills/pr-review-round/scripts/md_to_html.py#L27-L48) |
| Failed release comparison becomes equality | A disposable Git repository with missing production/integration refs produced `IDENTICAL` and `Nothing is queued`, with exit code 0. | [Ship-state comparison](../../skills/scoussens-skills/release-brief/scripts/shipped-in-window.sh#L62-L75) |
| Proposal checker certifies skipped arithmetic | One row with 2 hours and $999 at $100/hour, even with `--strict`, exited 0 and said `money matches hours × rate`. | [Column selection](../../skills/scoussens-skills/work-proposal/scripts/check-totals.py#L150-L156), [success message](../../skills/scoussens-skills/work-proposal/scripts/check-totals.py#L255-L256) |
| Failed PDF rerender reports the old file as new | A stub browser exited 37. An existing nonempty output stayed byte-identical, but the script exited 0 and printed `wrote:`. | [PDF rendering](../../skills/scoussens-skills/work-proposal/scripts/html-to-pdf.sh#L56-L79) |
| Equivalent meeting timestamps become different instants | `15:00Z` and `10:00-05:00` became naive `15:00` and `10:00`. | [Timestamp parsing](../../skills/scoussens-skills/meeting-index/scripts/rollup.py#L85-L92) |

A control run confirmed that `land.py --watch` made zero enqueue calls. Its timeout wording still claimed queue membership without evidence. Missing reviewed-head protection is source-traced, not a reproduced live race.

## Prioritize bounded corrections, then shared contracts

P1 fixes protect authority, evidence, and correctness. P2 removes cross-product installation and maintenance obstacles. P3 improves selection after behavior is trustworthy. The IDs below name proposed work units, not created tickets.

| Order | Priority and unit | Scope | Depends on | Completion criterion |
| --- | --- | --- | --- | --- |
| 1 | **P1 A1. Make review-round writes and reports truthful** | `pr-review-round` instructions, `land.py`, `round_report.py`, and Markdown rendering. Separate assessment-only from authorized approval/dismissal/merge. Bind writes to the reviewed head. Recheck approval on every enqueue. Track actual queue/merge/conflict states. Escape link attributes. | None | A read-only request makes no mutation calls. A changed head or revoked approval blocks writes. Conflicts never count as landed. Watch mode stays read-only. Malformed links add no attributes. |
| 2 | **P1 A2. Preserve unknown release state** | `release-brief` helper and output rules. Fail or mark unknown on comparison errors. Resolve explicit previous/current release boundaries. Replace universal privacy promises with verified audience information. | None | Missing refs never produce equality. A tag spanning three commits includes all three. Failed deployment remains unverified. A public destination is never described as private. |
| 3 | **P1 A3. Make proposal validation and delivery honest** | `work-proposal` arithmetic, PDF renderer, and estimating/output references. Do not edit tracker estimates as a side effect of drafting. Distinguish checked, failed, and unverified arithmetic. Accept only a successful fresh PDF output. | None | The reproduced single-row error fails validation. Failed rerender cannot certify an existing PDF. A draft causes no tracker/email writes. Publishing reports actual access. |
| 4 | **P1 A4. Make PR collections complete and repository-bound** | `pr-detail` gathering/metrics and `pr-digest` helpers. Preserve pagination and fetch failures. Resolve the intended repository explicitly. Detect capped result sets. Do not interpret comment-only reviews as clearance. | None | Multi-page fixtures retain every record and retrieval gap. An installed skill in repository B queries requested repository A. Saturation is detected. "Do not merge" in a comment-only review does not become "no blocking issues." |
| 5 | **P1 A5. Normalize meeting time correctly** | `meeting-index` timestamp parser, offset instructions, and installed script invocation. Convert aware timestamps before removing timezone information. Correct the offset formula. Define fixed-offset limits or accept a named timezone. | None | Equivalent timestamps group into the same local instant. Midnight and daylight-saving boundaries follow the documented contract. Invocation works outside the skill directory. |
| 6 | **P2 B1. Simplify shared settings and capability lookup** | `explain-to`, its callers, `harness-discovery`, and questionnaire setup. Resolve the conflicting single-destination rule. Separate ordinary settings from disclosure permission. Avoid persistent discovery or companion installation for a simple supported reply. | None, but keep overlapping changes after A1–A4 | Known settings are reused. Public-only delivery without approval stays held. Chat output needs no Python or discovery state. Manual questionnaire review works without a wake adapter. |
| 7 | **P2 B2. Encode packaging contracts once** | A small catalog, existing validator, and generated Codex metadata/manifests. Distinguish required companions, optional helpers, and mode-specific tools. Classify manual invocation separately from an explicit natural-language request. | B1 | Every public skill has a reviewed activation/support contract. A missing required companion fails packaging. Optional helpers do not become mandatory. The five existing manual-only flags have corresponding supported host metadata. |
| 8 | **P2 B3. Exercise installed workflows and product modes** | Extend existing tests. Add temporary installed-directory fixtures and a separate agent evaluation command. Retain prompt cases and source-copy checks, but identify what each proves. | Each relevant A unit and B2 | Run from a foreign working directory with paths containing spaces. Record the actual client/version/mode and selected case. Unsupported operations stop honestly. Browser cases run explicitly rather than disappearing behind skips. |
| 9 | **P2 B4. Publish only tested subsets** | Generated plugin/ZIP exports and installation documentation from the [distribution research](../research/cross-platform-skill-distribution.md). No platform-specific source copies. | B2, B3, and all P1 fixes affecting the selected subset | Archives preserve resources and required companions. Strict targets accept their metadata. Each advertised workflow has a target-mode result or an explicit unsupported status. Publishing still requires authorization. |
| 10 | **P3 C1. Reduce selection and reading cost** | Long descriptions, `pstack-sync` entry workflow, and `pr-digest` selection metadata. Keep scope exclusions, move rare administrative detail into owned references, and add positive/negative trigger cases. | Relevant behavior contracts settled | Shortened instructions preserve the same authority and evidence gates. Open-PR inventory requests select `pr-digest`. No skill is renamed or split without a demonstrated discovery or ownership benefit. |

A1–A5 can proceed independently with different file owners. Add each regression test with its fix, not in a later cleanup. B3 broadens those checks to installed packages and real agent behavior.

## All 20 public skills have a disposition

The classes describe current requirements, not a certification that a particular product supplies them. A workflow can have both a conversational mode and a tool-dependent mode.

| Skill | Observed contract and gap | Proposed disposition and acceptance focus |
| --- | --- | --- |
| [agent-handoff](../../skills/scoussens-skills/agent-handoff/SKILL.md) | Repository-oriented handoff. The preflight assumes Git/`gh` at lines 58–75. The checker command at 198–200 is relative to the current directory. Manual table checking already exists. | **P2.** Add an explicit conversation-only path that labels unverifiable repository facts. Resolve the checker from the installed skill directory. Preserve action dependencies, completion criteria, and offline evidence replay. Test a non-repository conversation and an installed checker invocation. |
| [business-rules-catalogue](../../skills/scoussens-skills/business-rules-catalogue/SKILL.md) | Tool-dependent analysis application. No required companion skill. Independent checking, source pinning, held publication, and unavailable-helper behavior are already explicit. The [upload recipe](../../skills/scoussens-skills/business-rules-catalogue/references/upload-brief.md#L7-L14) assumes Amp `code_exec`. | **P2, narrow adjustment.** Label that recipe as an Amp adapter and keep the generic destination contract. Preserve the independent-checker requirement. An isolated install must hold final build without a checker and hold public publication without approval. Do not rewrite its pipeline. |
| [dashboard](../../skills/scoussens-skills/dashboard/SKILL.md#L53-L92) | Python/HTML application with a clear producer-owned status contract. Requires `explain-to` for settings. Explicitly requires confirmation even when only one destination exists. | **P2 B1.** Align settings and audience rules with other callers. Preserve atomic rendering, same-URL updates, and served-byte checks. A fixed approved destination needs no repeat interview; an unapproved audience still blocks publication. |
| [designing-questionnaires](../../skills/scoussens-skills/designing-questionnaires/SKILL.md) | Stateful application with meaningful persistence, outbox, and retry checks. Manual/static fallbacks already exist. `metadata.needs` lists wake/message capabilities unconditionally. [Setup](../../skills/scoussens-skills/designing-questionnaires/references/setup.md#L3-L9) requires installing `explain-to` if absent. | **P2 B1/B2.** Separate manual, static, and automatic requirements. Allow its defined intake to run without installing a companion solely for settings. Preserve immutable submissions, durable receipts, actual wake verification, and authenticated team access. Test manual mode with no wake capability. |
| [explain-to](../../skills/scoussens-skills/explain-to/SKILL.md) | Audience/output policy used by many other skills. Its description is 899 characters. `metadata.needs` requires artifacts and helpers even though chat is a supported output. `speak-clearly` is optional at lines 153–158. | **P2 B1.** Keep audience/altitude guidance. Make the normal chat path independent of Python, filesystem state, and page helpers. Make the caller contract small and explicit. Do not replace the optional prose helper with a mandatory dependency. |
| [harness-discovery](../../skills/scoussens-skills/harness-discovery/SKILL.md#L20-L53) | Durable repository capability registry with migration, validation, and fingerprints. Stale discovery triggers a full inspection and tells the agent to open an upstream PR. It already says not to load it for one saved fact. | **P2.** Preserve durable discovery for orchestration/sync. Permit callers to use a narrow session-local observation when no persistent registry is needed. Separate registry contribution from capability lookup. A missing page destination must not trigger an upstream PR workflow. |
| [meeting-index](../../skills/scoussens-skills/meeting-index/SKILL.md) | Required `explain-to`; source adapters support both connectors and local exports. Timestamp normalization is wrong. Offset prose at lines 173–175 has the opposite sign from the implementation. The rollup command at 164–166 assumes a working directory. | **P1 A5.** Fix time and installed paths. Add pagination/boundary fixtures. Keep whole-window enumeration, source IDs, short-record exclusions, and unavailable-summary disclosure. Plaud remains optional. |
| [optimize-ci](../../skills/scoussens-skills/optimize-ci/SKILL.md) | Repository/CI workflow with separate evaluate, design, and implement modes. Missing evidence is explicit. Provider references are conditional. Bundled script paths are already resolved correctly. | **Keep structure.** Add capability/support metadata and installed-fixture coverage. Reuse this mode separation elsewhere instead of adding companion skills. An evaluation request must remain read-only and must not infer provider access. |
| [picking-skills](../../skills/scoussens-skills/picking-skills/SKILL.md#L1-L5) | Intentionally Amp Linux orb-specific. Declares portals, Amp CLI, Node 22, and `flock`. Exact-source selection and paste-to-submit boundaries are explicit. | **Keep host-specific.** Exclude from portable desktop bundles. Maintain the Amp adapter and its existing tests. Do not add generic branches that imply a browser can submit into another product's conversation. |
| [pr-detail](../../skills/scoussens-skills/pr-detail/SKILL.md) | Required `explain-to`; manual-only flag. [Gatherer](../../skills/scoussens-skills/pr-detail/scripts/gather_pr.sh#L82-L126) truncates review threads/comments and discards later slurped pages. Fetch failures do not survive reliably into metrics. Shared `/tmp/pr.json` and `/tmp/metrics.json` can collide. | **P1 A4.** Aggregate pages or disclose incomplete evidence and withhold unsupported assessment. Use run-specific files. Keep author-scoped counts, bot distinctions, source-checked finding outcomes, and behavior rather than personality judgments. Test two concurrent assessments. |
| [pr-digest](../../skills/scoussens-skills/pr-digest/SKILL.md) | Required `explain-to`; teacher prompt has a fallback. Instructions at 122–123 use the skill directory as cwd, while the helper relies on the current repository. Lists cap at 300 merged/200 open. [Review status](../../skills/scoussens-skills/pr-digest/references/review-status.md#L48-L55) overstates comment-only verdicts. | **P1 A4, then P3.** Bind the target repo, expose truncation, and use "reviewed; no formal verdict" unless evidence supports clearance. Advertise the existing no-window, drafts-inclusive inventory mode. Keep forge-first enumeration and optional tracker enrichment. |
| [pr-review-round](../../skills/scoussens-skills/pr-review-round/SKILL.md) | Mutation-capable GitHub workflow. Invocation wording assumes authority for the full loop, while prompts also ask only which PRs are ready. Destination silence is treated as acceptance. Merge/HTML failures are reproduced above. | **P1 A1.** Split assessment authority from approval/dismissal/merge authority. Hold external publication independently. Preserve fresh-head verification, independent review, no self-approval, and permission-denial handling. Optional teacher prompts must stay optional. |
| [pr-teacher](../../skills/scoussens-skills/pr-teacher/SKILL.md) | Required `explain-to`; interactive HTML is part of the product. Source reads at 49–65 do not explicitly pin head/base revisions. Lines 142–145 assume native Mermaid rendering in artifacts. Mechanical checks use interaction heuristics, not actual operation. | **P2.** Pin the PR snapshot before reading surrounding code. Pre-render diagrams or verify destination rendering. Exercise the teaching interaction in a browser. Preserve prediction/check behavior and label simulations. A later checkout must not silently replace the PR's implementation. |
| [pstack-sync](../../skills/scoussens-skills/pstack-sync/SKILL.md) | Administrative sync engine with dependency closure, ownership, drift tracking, durable adaptations, and dry-run publication. Dense numbered steps mix install, adapt, commit, publish, and upstream seed contribution. A drift instruction says to restore with `git checkout`. | **P2, then P3.** Separate ordinary sync from optional contribution/publishing procedures in owned references. Make restoration and external-write authority explicit, including personal repositories. Reorder preparation before state writes when preparation can reset state. Preserve ownership and local drift rather than making sync overwrite them. Do not reuse this whole engine as a general package builder. |
| [release-brief](../../skills/scoussens-skills/release-brief/SKILL.md) | Required `explain-to`; production evidence is essential. Failed comparisons report equality. `--release` selects `release^..release` despite supporting tag-to-tag releases in prose. Lines 229–233 promise privacy regardless of destination. | **P1 A2.** Fix uncertainty, release boundaries, and audience claims. Keep merged-versus-deployed distinctions, promotion deduplication, tracker-authoritative fields, and explicit omissions. Never make plain-chat compatibility mean unverified production claims. |
| [speak-clearly](../../skills/scoussens-skills/speak-clearly/SKILL.md) | Instruction-only prose guidance with one owned reference. Optional audience guidance does not require `explain-to`. No external write or runtime dependency. | **Keep structure.** First candidate for a small portable package. Test meaning/identifier preservation and selection on prose requests. Do not turn it into an output router or require companion installation. |
| [visualize-spec](../../skills/scoussens-skills/visualize-spec/SKILL.md#L27-L40) | Requires `explain-to`; Python checker and HTML template are integral. Skips the settings sheet when only one destination exists, contradicting `dashboard`. Missing repository data already becomes a visible gap. | **P2 B1/B3.** Align delivery consent, retain source-versus-suggestion labels, and run the page checker/browser cases from installed resources. No available private destination must not imply permission to publish repository details publicly. |
| [work-proposal](../../skills/scoussens-skills/work-proposal/SKILL.md) | Required `explain-to`; `speak-clearly` is optional. [Estimating reference](../../skills/scoussens-skills/work-proposal/references/estimating.md#L107-L109) instructs tracker correction during drafting. [Output rules](../../skills/scoussens-skills/work-proposal/references/output-formats.md#L56-L57) promise privacy. Arithmetic/PDF failures are reproduced above. | **P1 A3.** Report ticket discrepancies without changing them absent authority. Fix checker and renderer success semantics. Declare PDF/browser capability separately from Markdown drafting. Preserve known-rate requirements, code-grounded estimates, unpriced decisions, and final visual inspection. |
| [working-tickets](../../skills/scoussens-skills/working-tickets/SKILL.md) | Tracker-dependent workflow with no mandatory companion. Already discovers local policy, preserves concurrent edits, reconciles uncertain writes, and refuses false closure. Its tests explicitly distinguish test-harness checks from model effectiveness. | **Keep structure.** Use it as the model for uncertain-write handling. Declare read/write capabilities by operation and run existing agent scenarios on supported hosts. Do not replace its policy discovery with a universal tracker abstraction. |
| [writing-in-voice](../../skills/scoussens-skills/writing-in-voice/SKILL.md) | Conversational drafting plus optional private persistence. Already supports missing-storage/session-only mode and optional `explain-to`. Profiles are deliberately separate from the reusable package. | **Keep structure.** Exercise selected-profile failure, no-storage drafting, and formatting-only revisions in desktop candidates. Preserve identity, scoped consent, and no-send-by-default rules. Do not bundle a person's profile or add another mandatory interview. |

### The two other skills have different ownership

| Skill | Disposition |
| --- | --- |
| [doorbell-messaging](../../plugins/doorbell/skills/doorbell-messaging/SKILL.md) | **Keep plugin-only.** Its Claude Code client binding, known leases, standing authority, and idempotency rules are intentional. Preserve `metadata.internal` in the CLI-specific source, but do not export it as a general desktop skill. Validate through Doorbell's plugin tests, not the public skill test count. Those plugin tests were not rerun in this audit. |
| [good-css](../../.agents/skills/good-css/SKILL.md) | **Keep a development dependency.** [skills-lock.json](../../skills-lock.json) records the upstream source. Its optional motion guidance and browser-support caveats do not require a public-package rewrite. Update through its upstream installation mechanism rather than adopting local maintenance of a second public copy. |

## Simplify shared policy without weakening safeguards

### Settings and publishing permission are separate decisions

Proposed caller input to `explain-to` is the artifact, fixed reader/output settings, and unresolved choices. The result is the selected settings, delivery audience, and whether publication is authorized. A settings result cannot grant authority that the task did not supply.

Use these rules consistently across callers:

1. Reuse choices the user or an authorized caller already fixed.
2. Ask about unresolved choices that change the deliverable. Do not repeat a full intake for every refresh.
3. Treat one available destination as a capability fact, not consent to disclose data there.
4. Permit ordinary in-thread drafting without persistent capability discovery.
5. If the workflow promises HTML interaction, report an unavailable HTML destination explicitly. Do not silently replace that contract with Markdown.

This changes the policy currently duplicated in `dashboard`, `visualize-spec`, review-round, and questionnaire setup. Decide and test it once. Keep the existing `explain-to` owner rather than creating a new settings skill or framework.

### Dependencies need three distinct meanings

Ten public skills directly require `explain-to` today: dashboard, designing-questionnaires, meeting-index, pr-detail, pr-digest, pr-review-round, pr-teacher, release-brief, visualize-spec, and work-proposal. Most use its settings step, not its full teaching workflow.

- **Required companion.** The current workflow unconditionally loads another skill. Bundle it or declare the installation requirement until the dependency is removed.
- **Optional helper.** The workflow continues without it. Examples include `speak-clearly` in explain-to/work-proposal and `explain-to` in writing-in-voice. Do not pull these into mandatory dependency closure.
- **Mode-specific capability.** Automatic questionnaire review needs a verified wake route. Manual review does not. PDF generation needs a renderer. Markdown drafting does not.

`harness-discovery` is a conditional dependency for destination handling, not proof that every conversational skill requires Python or Amp. Its registry remains useful for durable orchestration. A simple caller should not initialize that registry merely to discover that it can answer in chat.

Proposed catalog fields should stay limited to canonical path, bundle membership, invocation intent, required/optional companions, mode requirements, and support evidence. Read names/descriptions from the skill source. Reuse the existing capability vocabulary. Do not create separate handwritten catalogs with the same facts for every platform.

### Manual invocation is not the same as explicit task intent

Five skills currently set `disable-model-invocation: true`: pr-detail, pr-digest, pr-review-round, pr-teacher, and visualize-spec. None has an OpenAI sidecar. This is a missing cross-host declaration, not a demonstrated unintended invocation.

Classify intent before generating metadata:

- Manual-only workflows require the host's explicit skill invocation mechanism.
- Intent-triggered workflows may load when the user clearly requests the task in natural language.
- Context helpers may load during another authorized task.

Claude documents that `disable-model-invocation` removes the skill from model invocation and is intended for manual `/name` use. Do not add it to every description containing "only when asked." That can prevent the natural-language behavior the description promises. [Claude invocation documentation](https://code.claude.com/docs/en/skills#control-who-invokes-a-skill).

Regardless of activation policy, invoking a skill does not authorize unrelated tracker edits, publishing to an inferred audience, or a merge when the user asked only for assessment. Strict upload formats that cannot preserve a necessary host-enforced policy need an explicit support limit.

## Keep the test layers distinct

Observed during this audit:

- `npm run validate` passed for 20 public skills and one plugin-local skill.
- `npm run test:skills` completed successfully with `12 suite(s) passed`.
- Two business-rules explorer tests were skipped because the opt-in browser flag was absent. They require `BR_BROWSER_TEST=1` and `agent-browser`.
- The run emitted resource warnings for an unclosed dashboard test socket and pstack-sync file reads. They did not fail the suites. Clean these up with their owning tests rather than suppressing warnings.
- Eleven public skills have `evals/evals.json`. Those files define prompt scenarios. The root test command does not run model evaluations.

[scripts/test-skills.mjs](../../scripts/test-skills.mjs#L13-L27) selects directories with top-level `evals/test_*.py` modules. Some suites exercise real contracts with disposable state. Others have narrower purposes. Review-round and work-proposal currently test copied-reference equality. Agent-handoff tests executable-evidence packaging, not its dependency-table checker. Working-tickets tests its evaluation machinery, not model effectiveness.

Eight public skills have no top-level suite discovered by that command: meeting-index, pr-detail, pr-digest, speak-clearly, explain-to, pr-teacher, visualize-spec, and writing-in-voice. This does not imply that an instruction-only skill needs unit tests or that nested fixtures are worthless. Add checks matched to the failure being prevented.

Use three test layers:

1. **Deterministic contracts.** Keep current validation and script tests. Add regression cases for the seven reproduced failures, collection pagination, installed paths, and required-companion packaging. Check totals and metadata agreement without treating them as model results.
2. **Agent behavior.** Execute positive and negative trigger cases, assessment-only versus write-authorized requests, missing-tool cases, and private/public destination cases. Record model, client version, tool inventory, source revision, and actual observed actions. Start with the high-risk workflows rather than evaluating every prose variation.
3. **Target-product delivery.** Install the actual generated package, run a representative workflow, and inspect output in that product mode. Exercise browser interactions for teaching/explorers and fresh PDF rendering for proposals. File discovery alone does not certify any of these behaviors.

## Start with a small portable subset

After the relevant fixes, use `speak-clearly` and the existing session-only drafting mode of `writing-in-voice` as initial conversational candidates. Add `explain-to` after its basic chat path no longer requires persistent discovery. Add `agent-handoff` only after its no-repository contract is explicit.

Test tool-dependent workflows separately. Preserve independent checking for business rules, real source reads for PR teaching, production verification for release briefs, and durable storage/wake verification for questionnaires. A product without those capabilities should receive an unsupported or held result, not a weaker workflow under the same promise.

Keep picking-skills and doorbell-messaging in their native integrations. Keep pstack-sync as an administrative workflow. Do not move every skill, rename everything into a new taxonomy, create one platform fork per product, or build a universal runtime adapter before a concrete caller requires one.

Matt Pocock's repository is a useful model for canonical folders, thin host metadata, and curated plugin membership. Its packaging does not solve our evidence, consent, or runtime defects. The [distribution research](../research/cross-platform-skill-distribution.md) records that distinction and the platform sources.

The Laziness Protocol shaped the recommendation to keep source paths and reuse existing validators. Minimize Reader Load shaped the recommendation to simplify the settings/discovery call chain and move rare sync administration out of the default instructions, without adding another orchestration layer.

## Delivery state and limits

Only documentation was created or corrected. No skill, helper script, manifest, installed package, or release automation was changed. Nothing was committed, pushed, uploaded, or published.

The findings combine full instruction-file coverage, selective supporting-source inspection, the existing test run, and seven local failure reproductions. Codex runtime behavior, ChatGPT installation, Claude Desktop/Cowork execution, account uploads, and publication privacy were not tested in their target products. The plan therefore recommends support gates rather than claiming universal compatibility.
