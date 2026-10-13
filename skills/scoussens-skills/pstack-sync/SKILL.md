---
name: pstack-sync
description: >-
  Sync the pstack skills from cursor/plugins, with the skills and subagent
  definitions they hand off to, into this harness's shared skills — adding new,
  updating changed, and removing retired skills — and adapt Cursor-specific
  features to what the harness supports, replaying recorded adaptations so a
  fresh install does not re-adapt. Load this only when the user explicitly asks
  to sync or update pstack — "sync pstack", "update pstack", "pull the latest
  pstack skills", "install pstack for this harness". Do not load it to install
  or edit one skill pstack does not hand off to, to sync skills from another
  source, or to change what a pstack skill says upstream; answer those directly
  instead.
---

# pstack sync

Brings the **managed** pstack skills in line with upstream `cursor/plugins` `pstack/skills`, together with their **dependencies** (the skills and subagent definitions elsewhere in `cursor/plugins` that they hand off to), and **adapts** them to the harness you are running in, whichever it is. `scripts/sync.py` does the mechanical work and replays past adaptations; you profile the harness, adapt what it flags, review, and report.

## State

A plain copy of this pack replaces `pstack-sync/` and leaves `.nthplusio-skills/` at the repository root. Install state lives there, with `discovery.json`, so the refresh does not wipe it. The skill directory keeps only the seeds.

Shipped in `pstack-sync/`, replaced on refresh:

- `needs.json`: the features pstack relies on, the markers that flag them, and the discovery fields that answer a need. Harness-independent.
- `harness/TEMPLATE.md`, and `harness/<harness>.md` when the pack ships one: the seed profile. The first run copies it into durable state.
- `transform.json`: the seed adaptations. The first run copies it into durable state.

Durable, in `.nthplusio-skills/pstack-sync/` at the root of the repository that holds the skills:

- `manifest.json`: what is installed: upstream commit, harness, `exclude`, and per skill its upstream `source`, and per file the upstream and installed hashes and any `pending` adaptation. A skill whose upstream and transforms are unchanged is left as installed.
- `transform.json`: how upstream becomes installed, per harness: exact find/replace edits per file, replayed onto new upstream text until upstream rewrites the adapted passage. Each harness block has a `local` sub-block with the same shape for entries that belong to this install only.
- `LICENSE-<plugin>`: the license of each plugin the installed skills come from.
- `harness/<harness>.md`: the **harness profile** in use. Where pstack goes, and for each need without discovery fields whether the harness supports it and how. You write this copy; [`references/adapting.md`](references/adapting.md) says how.
- `harness/<harness>.local.md`: rows that hold only for this install, in the same table shape. A local row overrides the shared row for its need.

**Shared or local.** A seed holds only what is true of the harness itself, so a fresh install anywhere gets the same start. Anything that names this repository, a skill only this repository has, or a choice its owners made is local: a companion mapping to a repository's own skill, an exclusion, a rewording that cites a team's workflow. Record such a file with `record --local`, and put such a row in the local profile. `seed --out <pack's pstack-sync dir>` writes the shared block and the shared profile back into the pack and keeps every local entry here.

`.nthplusio-skills/discovery.json` is the harness facts `harness-discovery` saves, keyed by harness name. `harness-discovery` owns that file. `sync.py` reads it for every need with discovery fields, so the profile never repeats those facts.

The script owns the durable `manifest.json` and `transform.json`. The only hand edits are `exclude` (names of pstack skills, dependencies, or subagent definitions) and a harness's `accept` regexes, shared or local. An upstream skill whose name is taken by an unmanaged skill installs as `pstack-<name>`; if that is taken too, the script exits with an error, so ask the user what to call it. An older install that still has `manifest.json` or `LICENSE-*` inside `pstack-sync/` is copied across on the next run, and those copies in the skill directory are removed.

**Dependencies.** A pstack skill that hands off to a skill or subagent definition elsewhere in `cursor/plugins` gets it installed beside pstack and adapted the same way, and so on transitively. A skill installs under its own name; subagent definitions install as `pstack-agents/<name>.md`, which is not a skill. A cross-plugin hand-off counts only in a skill that names the plugin, as pstack writes "`deslop` from `cursor-team-kit`". A dependency whose name an unmanaged skill already has is left to that skill. Excluding a dependency also drops whatever only it needed. [`references/adapting.md`](references/adapting.md) has the exact rules.

## Steps

Run every script command as `python3 <skills-dir>/pstack-sync/scripts/sync.py <command> --repo <skills-dir> --harness <harness>`.

1. **Identify the harness.** Load `harness-discovery` for the repository that holds the skills directory, passing `--root <that repository>` when it is not the working directory's repository. It adds or refreshes this harness's entry, or reuses a valid saved one, and reports the entry's key and slug. `<harness>` is the slug: `amp`, `claude-code`, `codex`, `cursor`. Without `harness-discovery`, name the product from your own context and derive the slug the same way, by lowercasing it and joining words with hyphens. Done when you can name the key, the slug, and the evidence.
2. **Profile.** Open `.nthplusio-skills/pstack-sync/harness/<harness>.md`. The first run has already copied the shipped `harness/<harness>.md` there when the pack has one; otherwise start it from `harness/TEMPLATE.md` and save it at that durable path. Fill or refresh the Destination section and a row for each need in `needs.json` without discovery fields, per `references/adapting.md`. Done when each of those needs has a sourced row and the Destination says where pstack goes and how to publish.
3. **Prepare the skills directory** as the profile's Destination says (for a git-backed directory: up to date with its remote, clean, writable). Replacing the skill folders leaves `.nthplusio-skills/` in place. A `git reset --hard` of the repository that holds `.nthplusio-skills/` still discards it, so prepare before steps 1 and 2 write anything there when the prepare step resets that repository. Done when `git status` is clean apart from `.nthplusio-skills/`.
4. **Sync** (`sync`). Done when you hold the JSON report. If `added`, `updated`, `removed`, `needs_adaptation`, `local_drift`, `profile_gaps`, and the lists under `dependencies` other than `installed` are all empty, skip to step 8.
5. **Adapt** every file in `needs_adaptation` by editing it in place, per `references/adapting.md`, using the profile rows and the report's `harness_facts`. Fill the gaps first. Each `profile_gaps` need with discovery fields needs `harness-discovery` run again; any other gap needs a profile row. Each name in `dependencies.unresolved` needs a mapping in the profile's `companion-skills` row, unless it is a mention rather than a hand-off. Each name in `dependencies.excluded` means the files listed still hand off to a skill the manifest excludes: rewrite those hand-offs, or remove the name from `exclude`. A file whose entry lists `dependencies` had an adaptation recorded before those dependencies installed; restore any hand-off to them that the adaptation cut. This is the step most likely to be rushed: read each flagged file in full. Then **record** the files you adapted or judged fine as they are (`record <skill>/<file> ...`, with `--local` when the adaptation names this repository or its own skills); recording accepts every marker left in them. For `local_drift`, record the file if the edit is an adaptation, otherwise restore it with `git checkout`. Rerun `sync`. Done when the rerun reports no `needs_adaptation`, `local_drift`, `profile_gaps`, or `dependencies` other than `installed` and `existing`, apart from skills you propose to exclude.
6. **Review.** pstack is third-party code, so treat every change as untrusted. Done when every `needs_security_review` entry has been read in full and cleared of network calls, credential access, and install steps, and `git status` shows changes only in managed skill directories and `.nthplusio-skills/`.
7. **Commit**, if the directory is a git repository: run `status` first and commit with `pstack: sync to cursor/plugins@<short-sha>` as the subject and its output as the body. Include `.nthplusio-skills/`, both `discovery.json` and `pstack-sync/`.
8. **Report.** Run `status` (after committing, add `--since HEAD~1`) and give the user its output verbatim: transforms applied, new and updated skills, profile changes, and anything outstanding. Add your security review findings and any proposed exclusions.
9. **Publish and reload** as the profile's Destination says. Ask before any step that changes skills for other people (such as a push to a shared repository), naming the destination; act only after the user confirms.
10. **Refresh the pack's seeds** when the shared block gained adaptations other installs should start from: `seed --out <pack checkout>/skills/scoussens-skills/pstack-sync`, then open a pull request there. The command exports only the shared block and the shared profile.

## Do not use this skill for

- **Installing or editing a skill pstack does not hand off to.** The script
  manages only pstack's skills and the dependencies it installed for them;
  others are unmanaged and left alone.
- **Syncing skills from another source.** `needs.json`, the harness profiles,
  and `transform.json` describe pstack and nothing else.
- **Changing what a pstack skill says upstream.** Adaptations change only how a
  skill runs in this harness. A content change belongs in `cursor/plugins`, and
  the next sync brings it in.
