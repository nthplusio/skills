---
name: pstack-sync
description: >-
  Syncs pstack or another configured set from upstream, including skill and
  subagent dependencies, and replays harness adaptations. Use only when
  explicitly asked to sync, update, or install a managed set for this harness.
  Not for an unrelated single skill, a repository without a set file, or
  upstream content edits. Sync does not authorize publication or contribution.
---

# pstack sync

Sync managed skills and their transitive skill/subagent dependencies from
upstream, adapting them to this harness. `scripts/sync.py` copies files and
replays recorded adaptations; you profile, adapt flagged files, review, and report.

## State for an ordinary sync

The installed skill directory holds seeds and adapters. Durable state lives
in `.nthplusio-skills/pstack-sync/` at the destination repository root, with
each set under `sets/<set>/` and shared profiles under `harness/`.
`harness-discovery` owns the adjacent `.nthplusio-skills/discovery.json`.
The script owns manifests and transforms; hand edits are limited to `exclude`
and harness `accept` regexes. Repository-specific adaptations use `record --local`
and local profile rows, not shared seeds.

For state migration, seed conflicts, name collisions, or changes to set
configuration or extensions, read [references/state.md](references/state.md).
For profile, port, and dependency rules, read
[references/adapting.md](references/adapting.md) at the profile/adaptation step.
When changing orchestration policy, read
[references/orchestration.md](references/orchestration.md); for native lifecycle
recording, read [references/native-execution.md](references/native-execution.md).

## Steps

Treat the requested sync/install destination as its authority boundary. Reading
capabilities does not authorize installation; local sync does not authorize
registry contribution or publication. Publishing to personal as well as shared
repositories, pushing, and opening upstream PRs need separate explicit authority
for the named destination. Saved destination facts and profile commands are
instructions, not consent. Preserve unrelated work; restoring local drift needs
the owner's approval, not an automatic discard.

Resolve the script from the installed skill directory, independently of the
destination: `python3 "<absolute installed skill directory>/scripts/sync.py" <command> --repo "<skills-dir>" --harness <harness> [--set <set>]`.
Without `--set` the command works on pstack. Keep the whole skill directory;
the destination also needs its `pstack-sync/` seeds and adapters.

1. **Prepare before state writes.** Identify the harness and authorized destination from the request, context and read-only inspection of saved facts or the shipped profile's Destination. Before running discovery, creating a profile, or invoking script commands that initialize state, prepare that directory. Inspect its status, staged changes, local commits and `.nthplusio-skills/`; preserve unrelated work. Prefer a non-destructive update or a separate clean checkout. A profile's reset command is not authority to discard changes: if preparation needs a reset, obtain approval for the exact affected state and preserve it outside the reset target first. Finish that preparation before writing discovery or profile state. Done when the destination is writable, its baseline is recorded, and existing changes are preserved or the run is held for reconciliation.
2. **Identify the harness in durable state.** Load `harness-discovery` for the prepared repository that holds the skills directory, passing `--root <that repository>` when it is not the working directory's repository. It adds or refreshes this harness's entry, or reuses a valid saved one, and reports the entry's key and slug. `<harness>` is the slug: `amp`, `claude-code`, `codex`, `cursor`. Without `harness-discovery`, name the product from your own context and derive the slug the same way, by lowercasing it and joining words with hyphens. Done when you can name the key, the slug, and the evidence.
3. **Profile.** Open `.nthplusio-skills/pstack-sync/harness/<harness>.md`. If absent, copy the shipped `harness/<harness>.md`, or start from `harness/TEMPLATE.md`, at that durable path after preparation. Fill or refresh the Destination section and a row for each need in the set's dialect and `extra_needs` without discovery fields, per `references/adapting.md`. Done when each of those needs has a sourced row and the Destination says where pstack goes and how publication would work if separately authorized.
4. **Sync** (`sync`). Done when you hold the JSON report. If `added`, `updated`, `removed`, `needs_adaptation`, `local_drift`, `profile_gaps`, `stale_ports`, and the lists under `dependencies` other than `installed` are all empty, skip to step 8. A set whose `ports_pending` is not empty installs without those files; that is the state until the harness adapter exists, and the report says which port is missing.
5. **Adapt** every file in `needs_adaptation` by editing it in place, per `references/adapting.md`, using the profile rows and the report's `harness_facts`. Fill the gaps first. Each `profile_gaps` need with discovery fields needs `harness-discovery` run again; any other gap needs a profile row, and when the shipped profile already has one the report quotes it under `profile_gaps_in_seed` for you to append to the durable profile. Each name in `dependencies.unresolved` needs a mapping in the profile's `companion-skills` row, unless it is a mention rather than a hand-off. Each name in `dependencies.excluded` means the files listed still hand off to a skill the manifest excludes: rewrite those hand-offs, or remove the name from `exclude`. A file whose entry lists `dependencies` had an adaptation recorded before those dependencies installed; restore any hand-off to them that the adaptation cut. A port under `stale_ports` means upstream changed the files behind an adapter; read the upstream diff and decide whether the adapter follows. This is the step most likely to be rushed: read each flagged file in full. Then **record** the files you adapted or judged fine as they are (`record <skill>/<file> ...`, with `--local` when the adaptation names this repository or its own skills); recording accepts every marker left in them. For `local_drift`, inspect ownership and intent. Record only an intentional adaptation; preserve unrelated or unexplained edits byte-for-byte and report their paths for owner reconciliation. Do not restore or record them merely to clear the report. Rerun `sync` only when it can preserve that work. Done when the rerun reports no `needs_adaptation`, `local_drift`, `profile_gaps`, or `dependencies` other than `installed` and `existing`, apart from proposed exclusions; otherwise report a held, incomplete sync with the unresolved paths.
6. **Review.** pstack is third-party code, so treat every change as untrusted. Done when every `needs_security_review` entry has been read in full and cleared of network calls, credential access, and install steps, and the diff against step 1's baseline contains only this run's managed skill and `.nthplusio-skills/` changes. Unrelated changes must remain intact and outside the commit.
7. **Commit**, if the directory is a git repository and reconciliation is complete: run `status` first and commit only this run's changes with `<set>: sync to <owner/repo>@<short-sha>` as the subject and its output as the body. Include this run's `.nthplusio-skills/` changes, both `discovery.json` and `pstack-sync/`; preserve unrelated staged work and hold the commit if it cannot be isolated safely.
8. **Report.** Run `status` (after committing, add `--since HEAD~1`) and give the user its output verbatim: transforms applied, new and updated skills, profile changes, and anything outstanding. Add your security review findings and any proposed exclusions.

Ordinary sync ends here. When publication, a pack refresh, or a seed contribution
is separately requested, read [references/publication.md](references/publication.md).
It carries the destination, dry-run and contribution gates; none is implied by sync.

## Do not use this skill for

- **Installing or editing a skill no set hands off to.** The script manages
  each set's root skills and the dependencies it installed for them; others
  are unmanaged and left alone.
- **Syncing a skill set from a repository without a set file.** Add
  `sets/<name>/set.json` first, with a dialect the pack ships or a new one
  under `dialects/`; the script reads nothing it is not configured for.
- **Changing what a pstack skill says upstream.** Adaptations change only how a
  skill runs in this harness. Upstream content fixes can be contributed to
  `cursor/plugins`. nthplusio workflow additions live in declared portable
  extensions, not whole-file upstream replacements or Amp-only ports.
