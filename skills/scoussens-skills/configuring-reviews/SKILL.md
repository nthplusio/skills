---
name: configuring-reviews
description: >-
  Configures repository-specific PR review references, execution preferences and
  ticket-policy pointers over portable defaults. Use when setting up or tailoring
  code reviews for a repository, or changing what reviewers check. Not for running
  a review, installing a tracker or changing lifecycle automation.
---

# Configure reviews

Keep repository choices in `<repository>/.nthplusio-skills/review.json`, not in a global review skill. Each repository gets its own profile. A caller can supply another profile path explicitly. Read [the profile contract](references/review-profile.md) before editing one.

Read [report writing](references/report-writing.md) before authoring the discovery summary or draft. It defaults to `speak-clearly` first, then `writing-in-voice`, using enabled helpers when available.

## Discover before writing

Read the current profile and applicable repository instructions. Follow existing setup/configuration outputs for ticket policy, conventions, architecture, verification, automation and agent execution. For example, engineering setup may already point to `docs/agents/issue-tracker.md`; harness discovery may already hold `.nthplusio-skills/discovery.json`. These are pointers to reuse, not mandatory paths or dependencies. Do not create a second tracker policy or copy live harness capabilities into the review profile.

Inspect the repository's source layout, existing review guidance and CI/test entry points. Separate documented requirements from inferred practices and unknowns; cite the files behind the findings. Keep existing owner decisions, labels and automation intact. Finish discovery with a short summary of the current policies, likely review risks and missing information, not a profile written from guesses.

## Validate findings and ask

Before editing, show that summary and ask whether it is accurate and whether the owner wants to keep the current profile (or bundled defaults for a new profile), customize it now, or defer configuration. Offer a recommendation based on discovery. Keeping defaults preserves existing customizations; resetting them is a separate explicit choice. If the owner already answered a question in this conversation or current setup, reuse that answer and ask only about remaining choices.

When customization is wanted, ask a short round of repository-specific questions, with recommended answers and room for another answer. Ground each question in a finding or an identified gap:

- What matters most in this repository's reviews? Ask about the failure modes discovery suggests, such as schema compatibility, integration contracts or authorization; let the owner name other priorities and checks they find noisy.
- Which existing documents should govern those checks, and what rules are missing? Propose references to reuse and categories to extend. Confirm any replacement, disabled category, new blocking threshold or exception with the owner rather than inferring policy from common code patterns.
- Which discovered ticket lifecycle and execution settings need correction? Reuse setup/configuration outputs; ask about missing completion/automation ownership or reviewer constraints only when unresolved. Include review-bot eligibility (size/path limits and required human approvers) in existing guidance references, with its workflow/policy source, rather than inventing portable thresholds or new profile keys. A customization interview does not reinstall a tracker or select a mandatory harness.
- Should reports keep the default clarity-then-voice passes when the helpers are available, skip either pass, or use a declared project voice? Reuse an answered preference; do not collect private voice samples or start a voice interview during review setup.

Use the harness's question interface when available, otherwise ordinary conversation. Wait for answers before drafting unresolved choices; in unattended runs, retain a proposal with those choices marked unanswered instead of claiming configuration is complete. If customization is declined, skip the tailoring questions. If configuration is deferred, leave files untouched; reviews can still use the defaults and existing instructions.

## Tailor the profile

Start from [assets/review.template.json](assets/review.template.json). Set:

- `guidance`: existing setup/configuration outputs or repository-wide review guidance to read first, including any report-writing overrides. Keep overrides in those referenced files rather than adding unsupported JSON keys; omitted writing preferences retain the clarity-then-voice defaults.
- `tracker.policy`: existing ticket-policy files, whether the tracker is hosted, file-based or explicitly absent. Those files own identity, link resolution, tracking exceptions, statuses, automation and writeback. No provider or status mapping is bundled here.
- `execution.reviewers`: `auto` by default; `serial` for separate passes in one agent, or `parallel` when the configured harness supports helpers. `execution.policy` points to existing execution/model configuration. Configuration never grants launch or write authority.
- `references`: category overrides or additions. Extend bundled checks by default; replace or disable a category only deliberately. Keep applicability, check, evidence and severity in the referenced Markdown, so repository owners can change them without rewriting the skill.

The bundled starting points are [conventions](references/defaults/conventions.md), [data layer](references/defaults/data-layer.md), [integrations](references/defaults/integration.md), [security](references/defaults/security.md) and [verification](references/defaults/verification.md). They are review questions, not a prescribed architecture or a list of automatic blockers. Add categories such as accessibility, performance or domain rules when the repository needs them.

Reuse existing reference files; create repository-specific Markdown only for rules that do not already have a home. For a new file, record when it applies, the repository rule and its source, the evidence needed, and what makes a finding blocking. A profile can point at any repository-relative text file; no fixed docs layout is required.

Show the proposed profile/reference diff and how it reflects the owner's answers, including unchanged defaults and unresolved choices. Obtain confirmation before writing; when another setup skill calls this workflow, use its draft-confirmation step rather than asking twice. If the user only asked for a proposal or has not confirmed it, retain a draft instead of changing repository policy.

## Validate and hand off

Run `python3 <this skill>/scripts/review_config.py --root <repository>`; add `--config <repository-relative-path>` for an alternate profile. The command is read-only, rejects invalid profiles or missing references, and prints the resolved references and policy pointers. It does not execute commands from configuration, contact a tracker or launch reviewers. Inspect the referenced policies as well; path validation does not validate their meaning.

Check that a repository with no profile resolves the bundled defaults, and that a tailored repository resolves only its own policy files and chosen overrides. Give the review caller the profile path, resolved files and any unresolved policy choices. Add a pointer in the repository's existing instruction/configuration index when that edit is in scope. Do not change another harness's instruction file just to advertise this profile.

Review consumers bundle identical copies of `scripts/review_config.py`, `references/review-profile.md` and `references/defaults/`, so each skill can be installed alone. PR artifact skills also bundle `references/report-writing.md`. This skill owns those resources. Copy updates to consumers and run the shared-resource consistency test. Setup is optional: an unconfigured repository remains reviewable with defaults, with unknown ticket or harness policy reported rather than invented.
