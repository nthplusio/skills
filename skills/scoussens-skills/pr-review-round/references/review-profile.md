# Repository review profile

Resolve the caller's explicit profile, otherwise `.nthplusio-skills/review.json` in the target repository. With no profile, use the bundled defaults and read applicable repository instructions and existing setup outputs. Do not run setup just to perform a review. If an explicitly requested profile is missing or invalid, report the configuration error; do not silently review with defaults.

Run `python3 <this skill>/scripts/review_config.py --root <repository> [--config <repository-relative-path>]`. Read the returned guidance, tracker policy, execution policy and applicable references before assessing the diff. The resolver validates file selection, not policy semantics or agent behavior. Save its `revision` in the review evidence inputs; it hashes the profile and all directly referenced files, including defaults. Changed rules invalidate affected reused assessments even when code and ticket evidence are unchanged. Follow links inside those files and refresh their evidence separately; the resolver does not crawl transitive links or live systems.

## Configuration contract

`schema_version` is required and is `1`. Other omitted fields retain defaults; unknown fields are errors, so a misspelled setting cannot silently change review coverage. Paths are repository-relative files within the target repository, not commands, URLs or paths into another repository. Referenced policy files can link to their authoritative external sources. The profile contains pointers, not credentials, ticket state, tool commands or permission grants.

- `guidance`: a list of existing setup/configuration or repository-wide guidance files.
- `tracker.policy`: a list of existing policy files. They own ticket identity/link formats, hosted or local access, allowed untracked work, transitions, automation and evidence writeback. Empty means discover from repository instructions; it does not mean tickets are forbidden or required. Explicit no-tracker policy is a valid choice. A failed lookup stays unknown.
- `execution.reviewers`: `auto`, `serial` or `parallel`. Default `auto` uses available, authorized helpers, otherwise separate Standards and Spec passes in the current agent. `serial` does not launch helpers. `parallel` requires verified helper support; if unavailable or prohibited, report the limitation and do not claim parallel/independent coverage. Continue safe serial assessment with that limitation. Read the active harness's saved discovery and current tool inventory only for capabilities needed by this run; a harness name is not a capability guarantee.
- `execution.policy`: a list of existing setup or harness configuration files for reviewer/model selection and execution limits. Prefer those outputs over hard-coded agent products, tool names or models. Verify stale capability facts before relying on them.
- `references`: an object keyed by category name. Bundled categories are `conventions`, `data-layer`, `integration`, `security` and `verification`. Each category accepts `mode` and `files`. `extend` adds repository references to the bundled file (the default); `replace` uses only the named files; `disable` excludes that category's optional checklist and accepts no files. A new category requires files and extends the set. `replace` requires at least one file. Modes affect review guidance, not higher-priority repository rules, acceptance criteria, source freshness or action-authority gates.

The resolver returns every enabled category. Read each reference's applicability and select checks from the actual changed behavior, not filenames alone. A documentation-only change does not require a database exercise; a renamed persisted field does even if its path looks like UI code. Record which references applied, which did not and why. A broken required reference is a configuration gap, not a completed review.

## Report-writing preferences

Reports default to `speak-clearly` first, then `writing-in-voice`, when each helper is available. Keep repository overrides in a file named by `guidance`, reusing existing setup output where possible; no extra JSON field or checklist category is needed. For example, a repository can state: "For review reports, apply speak-clearly and skip writing-in-voice." It can instead select a declared project voice under the voice skill's rules. Preserve the default order when both passes are enabled. An omitted preference retains defaults; a missing helper does not block a review. Keep personal profiles and samples out of shared guidance. The bundled report-writing reference owns the editing and privacy rules; the resolver validates the guidance pointer, not the prose preference's meaning.

## Example: reuse setup and add repository checks

These are illustrative paths, not requirements. Keep tracker details in the policy your existing setup owns; that policy may describe local files, a hosted tracker or no tracker.

```json
{
  "schema_version": 1,
  "guidance": ["docs/agents/domain.md"],
  "tracker": {"policy": ["docs/agents/issue-tracker.md"]},
  "execution": {"reviewers": "serial", "policy": []},
  "references": {
    "conventions": {"files": ["CONTRIBUTING.md"]},
    "data-layer": {"mode": "extend", "files": ["docs/review/storage.md"]},
    "integration": {"mode": "replace", "files": ["docs/review/contracts.md"]},
    "accessibility": {"files": ["docs/review/accessibility.md"]}
  }
}
```

## Applying the resolved policy

Repository requirements and acceptance criteria override conflicting bundled heuristics; keep source precedence intact. Defaults cannot invent a mandatory ORM, transaction model, integration transport or deployment process. Report a heuristic as nonblocking unless a documented rule or reproduced consequence supports a blocker. Disabling a checklist never waives an actual acceptance criterion or authorizes an unsafe write.

Read ticket bodies and relevant discussion/owner decisions through the configured mechanism. Confirm a link or local path rather than assuming a universal issue-ID regex. For a documented tracking exception, say "no linked ticket" and assess the agreed PR contract. If neither a ticket nor an agreed contract exists, Spec remains incomplete. Do not turn unavailable tracker access into a pass or require a particular setup skill.

Follow the configured lifecycle's definition of done and automation ownership. A forge merge is not automatically ticket completion. For example, one repository may complete work after development merge, another after production validation. Read back supported state at the configured milestones; flag mismatches without duplicating automation-owned transitions. Tracker writes, follow-up creation and publication still need their own authority. No configured tracker means no invented ticket updates.

Keep Standards and Spec separate under both serial and parallel execution. Give helpers the pinned revisions, complete applicable rules and criterion evidence; without helpers, retain equivalent coverage records for each pass and disclose the lack of independent reviewers. Configuration selects execution, not whether unexamined work can pass.

## Ownership and installation

`configuring-reviews` owns this contract, the resolver and bundled defaults. Review consumers carry identical local copies because installed skills cannot import sibling skill directories. A review should work when installed alone, even if the configuration skill or optional harness-discovery skill is unavailable. Owners edit the target repository's profile/references, not global skill copies. Setup/configuration skills can emit this profile directly; repeated setup preserves existing owner edits and links to current policy rather than duplicating it.
