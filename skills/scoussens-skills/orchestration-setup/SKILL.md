---
name: orchestration-setup
description: >-
  Interviews the user to configure repository orchestration using saved discovery,
  with shared project policy and separate profiles keyed by harness name. Use for
  /orchestration-setup, first-time configuration, adding another harness, or
  repairing setup. Calls harness-discovery when needed. Use orchestration-run
  to coordinate work after setup.
---

# Orchestration setup

Turn discovered capabilities into confirmed configuration. Save project policy
once and keep each harness's choices under its discovered name.

## 1. Read setup and ensure discovery exists

Saved state lives in `<repository root>/.nthplusio-skills/`: `orchestration.json`
holds setup and `discovery.json` holds discovery. These skills change between
versions, so first run:

```bash
python3 <this skill's folder>/scripts/state.py migrate
```

It moves and upgrades state saved by earlier versions, refuses to overwrite a
conflicting file, and prints what it changed. Tell the user what it moved. When
the user names an older configuration elsewhere, pass it with `--from <path>`;
migrate copies it and leaves the original unchanged. Then read both files when
they exist. Identify the current harness by its canonical product name, as
`harness-discovery` records it.

If discovery is absent, malformed, missing this harness, or contradicted by
the current context, load `harness-discovery` first for the same repository.
Read its saved output before interviewing the user.
Reuse suitable saved discovery. A new run alone does not require rediscovery.

Use the discovered harness name exactly as the profile key. Adding another
harness merges a new entry into the same files. Preserve other profiles and
confirmed project choices. To configure a harness not running here, reuse its
saved discovery or obtain a discovery report from that environment first.

An old single-harness version 1 configuration, supplied by the user or reported
by migrate, is migration input, not the runner's contract. Preserve it, carry confirmed choices into the
new profile, and confirm only missing project/default choices. Discovery verifies
imported capability facts. Save the new repository files rather than overwriting
personal defaults or inventing compatibility behavior in the runner.

**Done when** valid discovery for the named harness is available and the existing
configuration, confirmed choices, and unresolved choices are known.

## 2. Interview for durable choices

Ask one focused question at a time. Offer only options the discovery report supports,
name relevant limitations, and recommend a choice. Inspect facts yourself. Questions
resolve user preferences, not capabilities. Reuse actual prior confirmation or
explicit user instructions. A template value or unanswered proposal is not confirmation.
Use suitable saved observations throughout the interview. Inspect capabilities
again only for a named contradiction or missing fact, through discovery.

Resolve project choices first, then the current harness profile:

1. Ticket policy. Read [ticket policy and the default layout](references/ticket-template.md).
   Confirm the source, location, definition, stable IDs, layout, and criterion limit
   against discovered repository conventions. This policy belongs to `project.ticket_policy`.
2. Worker instructions. Confirm project-wide `shared_skills` and any harness-specific
   additions. Use required baseline guidance as evidence rather than asking again.
   `harness-discovery` and both orchestration skills belong to the coordinator, not worker briefs.
   Optionally map business stages to the repository skills that perform them in
   `project.stage_skills`, such as a start-work skill for `code_publication` or
   a review skill for `review`. Offer only skills the repository already has.
3. Storage. Confirm this profile's `run_root`. Explain that run files hold status,
   dashboards, retained proof, and handoffs. Propose `runs/<harness slug>`, relative
   to `.nthplusio-skills/`. An absolute local path or `~/...` is also supported.
4. Run defaults. Confirm the default finish line, preferred available destination
   or `null` for no preference, and the coordinator's scan interval. Propose
   review-ready PRs and 60 seconds if guidance supplies none. Explain active-turn
   or manual-resume limits from discovery. For destinations with verified embedded refresh,
   explain that the dashboard reloads at the run interval, including during dialogs.
   A preference is not run approval or permission to wake the coordinator after yielding.

Group closely related choices when one answer can settle them, such as the run
defaults. If an answer is pending, end this turn with that one question
and resume the interview after the user answers. Keep later choices unresolved.
When the harness supplies an answer receipt or message link, retain that reference
with the confirmed choices. Wait before saving a new setup profile. Discovery can
already be saved while an interview awaits input.
Changes to project policy affect every harness, so confirm their shared scope.

**Done when** project policy and the current profile's storage, shared instructions,
and defaults have actual confirmation sources, or setup is explicitly awaiting input.

## 3. Save and check setup

Fill [`assets/orchestration.template.json`](assets/orchestration.template.json)
with confirmed choices and save it as `.nthplusio-skills/orchestration.json`.
`run_root` resolves relative to `.nthplusio-skills/`, not the invocation directory.
Record the actual confirmation source in project ticket policy and each harness
profile.

Keep sanitized discovery and setup in the repository. Keep run files outside Git
and installed skill directories. For a run root inside the repository, write
`.nthplusio-skills/.gitignore` with a rule that covers it, such as `runs/`, and
verify the run files are neither tracked nor staged before the runner writes there.
Local machine-specific overrides remain untracked. No step commits or pushes files.

Run:

```bash
python3 <this skill's folder>/scripts/state.py check orchestration
python3 <this skill's folder>/scripts/state.py resolve --harness '<discovered name>' --orchestration
```

The second command emits the resolved profile the runner consumes. It joins saved
capabilities with project policy and this harness's preferences without invoking tools.
Unsupported operations remain explicit. If the requested coordination cannot use
independent owners, report the limitation before offering a different workflow.

**Done when** saved setup validates, the selected name resolves to the intended
profile, and runtime storage is excluded from Git. Reply with the paths, configured
harness names, and material limitations. Invite `/orchestration-run` for actual work.
