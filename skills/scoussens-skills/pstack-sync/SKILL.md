---
name: pstack-sync
description: >-
  Sync a managed skill set, pstack by default or any set under `sets/`,
  from its upstream repository, with the skills and subagent
  definitions they hand off to, into this harness's shared skills — adding new,
  updating changed, and removing retired skills — and adapt Cursor-specific
  features to what the harness supports, replaying recorded adaptations so a
  fresh install does not re-adapt. Load this only when the user explicitly asks
  to sync or update pstack — "sync pstack", "update pstack", "pull the latest
  pstack skills", "install pstack for this harness". Do not load it to install
  or edit one skill no set hands off to, to sync a repository that has no set
  file, or to change what a synced skill says upstream; answer those directly
  instead.
---

# pstack sync

Brings the **managed** pstack skills in line with upstream `cursor/plugins` `pstack/skills`, together with their **dependencies** (the skills and subagent definitions elsewhere in `cursor/plugins` that they hand off to), and **adapts** them to the harness you are running in, whichever it is. `scripts/sync.py` does the mechanical work and replays past adaptations; you profile the harness, adapt what it flags, review, and report.

## State

A plain copy of this pack replaces `pstack-sync/` and leaves `.nthplusio-skills/` at the repository root. Install state lives there, with `discovery.json`, so the refresh does not wipe it. The skill directory keeps only the seeds.

The sync manages **sets**. A set is one upstream repository, one root plugin whose skills are the roots, and the dependencies they pull in. pstack is the default set; `--set <name>` picks another, and several sets share one install. A set's text is adapted through a **dialect**, the catalog of constructs its source harness uses (Cursor, for every set from `cursor/plugins`), plus the set's own rows. Code the harness must replace as a unit is a **port**: the set names the upstream files, and an adapter under `adapters/<harness>/<port>/` provides them; until the adapter exists the port is reported pending and its files are not installed.

Shipped in `pstack-sync/`, replaced on refresh:

- `dialects/<dialect>.json`: the constructs of one source harness, the markers that flag them, and the discovery fields that answer a need. Shared by every set with that dialect.
- `sets/<set>/set.json`: the set's upstream, root plugin, skills subdirectory, plugin marker, dialect, agents directory, collision prefix, `extra_needs` in the catalog shape, `exclude` (names never installed, joined with the manifest's), `ignore` (file globs never installed, such as upstream tests), and `ports`.
- `sets/<set>/transform.json`: the set's seed adaptations. The first run copies it into durable state.
- `adapters/<harness>/<port>/<file>`: this harness's replacement for a port's files.
- `harness/TEMPLATE.md`, and `harness/<harness>.md` when the pack ships one: the seed profile. The first run copies it into durable state.

Durable, in `.nthplusio-skills/pstack-sync/` at the root of the repository that holds the skills, with each set's files under `sets/<set>/` and the profiles shared:

- `sets/<set>/manifest.json`: what is installed: set, upstream commit, harness, `exclude`, and per skill its upstream `source`, and per file the upstream and installed hashes, any `pending` adaptation, and the `port` that owns it. A skill whose upstream and transforms are unchanged is left as installed.
- `sets/<set>/transform.json`: how upstream becomes installed, per harness: exact find/replace edits per file, replayed onto new upstream text until upstream rewrites the adapted passage. Each harness block has a `local` sub-block with the same shape for entries that belong to this install only.
- `sets/<set>/LICENSE-<plugin>`: the license of each plugin the installed skills come from.
- `harness/<harness>.md`: the **harness profile** in use. Where pstack goes, and for each need without discovery fields whether the harness supports it and how. You write this copy; [`references/adapting.md`](references/adapting.md) says how.
- `harness/<harness>.local.md`: rows that hold only for this install, in the same table shape. A local row overrides the shared row for its need.

**Shared or local.** A seed holds only what is true of the harness itself, so a fresh install anywhere gets the same start. Anything that names this repository, a skill only this repository has, or a choice its owners made is local: a companion mapping to a repository's own skill, an exclusion, a rewording that cites a team's workflow. Record such a file with `record --local`, and put such a row in the local profile. `seed --out <pack's pstack-sync dir>` writes the shared block and the shared profile back into the pack and keeps every local entry here.

`.nthplusio-skills/pack-manifest.json` is what `publish` copied last: the pack commit and remote, when, and the skill names. `publish` removes a retired skill only when this file names it; a directory the file does not name is never touched.

`.nthplusio-skills/discovery.json` is the harness facts `harness-discovery` saves, keyed by harness name. `harness-discovery` owns that file. `sync.py` reads it for every need with discovery fields, so the profile never repeats those facts.

The script owns the durable `manifest.json` and `transform.json`. The only hand edits are `exclude` (names of pstack skills, dependencies, or subagent definitions) and a harness's `accept` regexes, shared or local. An upstream skill whose name is taken by an unmanaged skill installs as `pstack-<name>`; if that is taken too, the script exits with an error, so ask the user what to call it. An install from before sets kept the pstack files directly under `.nthplusio-skills/pstack-sync/`, or inside the skill directory; the next run moves them into `sets/pstack/`, and `status --since` still finds the old paths for its baseline.

**Dependencies.** A pstack skill that hands off to a skill or subagent definition elsewhere in `cursor/plugins` gets it installed beside pstack and adapted the same way, and so on transitively. A skill installs under its own name; subagent definitions install as `pstack-agents/<name>.md`, which is not a skill. A cross-plugin hand-off counts only in a skill that names the plugin, as pstack writes "`deslop` from `cursor-team-kit`". A dependency whose name an unmanaged skill already has is left to that skill. Excluding a dependency also drops whatever only it needed. [`references/adapting.md`](references/adapting.md) has the exact rules.

## Steps

Run every script command as `python3 <skills-dir>/pstack-sync/scripts/sync.py <command> --repo <skills-dir> --harness <harness> [--set <set>]`. Without `--set` the command works on pstack.

1. **Identify the harness.** Load `harness-discovery` for the repository that holds the skills directory, passing `--root <that repository>` when it is not the working directory's repository. It adds or refreshes this harness's entry, or reuses a valid saved one, and reports the entry's key and slug. `<harness>` is the slug: `amp`, `claude-code`, `codex`, `cursor`. Without `harness-discovery`, name the product from your own context and derive the slug the same way, by lowercasing it and joining words with hyphens. Done when you can name the key, the slug, and the evidence.
2. **Profile.** Open `.nthplusio-skills/pstack-sync/harness/<harness>.md`. The first run has already copied the shipped `harness/<harness>.md` there when the pack has one; otherwise start it from `harness/TEMPLATE.md` and save it at that durable path. Fill or refresh the Destination section and a row for each need in the set's dialect and `extra_needs` without discovery fields, per `references/adapting.md`. Done when each of those needs has a sourced row and the Destination says where pstack goes and how to publish.
3. **Prepare the skills directory** as the profile's Destination says (for a git-backed directory: up to date with its remote, clean, writable). Replacing the skill folders leaves `.nthplusio-skills/` in place. A `git reset --hard` of the repository that holds `.nthplusio-skills/` still discards it, so prepare before steps 1 and 2 write anything there when the prepare step resets that repository. Done when `git status` is clean apart from `.nthplusio-skills/`.
4. **Sync** (`sync`). Done when you hold the JSON report. If `added`, `updated`, `removed`, `needs_adaptation`, `local_drift`, `profile_gaps`, `stale_ports`, and the lists under `dependencies` other than `installed` are all empty, skip to step 8. A set whose `ports_pending` is not empty installs without those files; that is the state until the harness adapter exists, and the report says which port is missing.
5. **Adapt** every file in `needs_adaptation` by editing it in place, per `references/adapting.md`, using the profile rows and the report's `harness_facts`. Fill the gaps first. Each `profile_gaps` need with discovery fields needs `harness-discovery` run again; any other gap needs a profile row, and when the shipped profile already has one the report quotes it under `profile_gaps_in_seed` for you to append to the durable profile. Each name in `dependencies.unresolved` needs a mapping in the profile's `companion-skills` row, unless it is a mention rather than a hand-off. Each name in `dependencies.excluded` means the files listed still hand off to a skill the manifest excludes: rewrite those hand-offs, or remove the name from `exclude`. A file whose entry lists `dependencies` had an adaptation recorded before those dependencies installed; restore any hand-off to them that the adaptation cut. A port under `stale_ports` means upstream changed the files behind an adapter; read the upstream diff and decide whether the adapter follows. This is the step most likely to be rushed: read each flagged file in full. Then **record** the files you adapted or judged fine as they are (`record <skill>/<file> ...`, with `--local` when the adaptation names this repository or its own skills); recording accepts every marker left in them. For `local_drift`, record the file if the edit is an adaptation, otherwise restore it with `git checkout`. Rerun `sync`. Done when the rerun reports no `needs_adaptation`, `local_drift`, `profile_gaps`, or `dependencies` other than `installed` and `existing`, apart from skills you propose to exclude.
6. **Review.** pstack is third-party code, so treat every change as untrusted. Done when every `needs_security_review` entry has been read in full and cleared of network calls, credential access, and install steps, and `git status` shows changes only in managed skill directories and `.nthplusio-skills/`.
7. **Commit**, if the directory is a git repository: run `status` first and commit with `<set>: sync to <owner/repo>@<short-sha>` as the subject and its output as the body. Include `.nthplusio-skills/`, both `discovery.json` and `pstack-sync/`.
8. **Report.** Run `status` (after committing, add `--since HEAD~1`) and give the user its output verbatim: transforms applied, new and updated skills, profile changes, and anything outstanding. Add your security review findings and any proposed exclusions.
9. **Publish and reload** as the profile's Destination says. Ask before any step that changes skills for other people (such as a push to a shared repository), naming the destination; act only after the user confirms.
10. **Refresh the pack's seeds** when the shared block gained adaptations other installs should start from: `seed --out <pack checkout>/skills/scoussens-skills/pstack-sync`, then open a pull request there. The command writes `sets/<set>/transform.json` without its local block, and the profile with the pack's header and the install's rows, so a stale link in an old durable profile never reaches the pack.
11. **Publish** a pack refresh in one command when the skills directory is a workspace skills repository this pack feeds: `publish --pack <pack checkout> --repo <workspace clone> --harness <harness> [--push] [--verify] [--dry-run]`. It replaces each pack skill with the pack's tracked files (never `node_modules`, never anything the pack ignores), removes the skills the previous publish copied that the pack has since retired, runs `sync` for every set the pack ships, appends the `profile_gaps_in_seed` rows to the durable profile and syncs again, and commits `Refresh workspace skills from nthplusio/skills@<sha>` with the repository's own identity. It refuses to commit, exit code 2, when the commit would add a `node_modules` directory or a file over 2 MB, and names each one; both make the skill index drop a skill. The report's `attention` list is yours, not the script's: `needs_adaptation`, `local_drift`, `profile_gaps`, and unresolved dependencies go through step 5 afterwards. Run with `--dry-run` first; it works in a throwaway worktree and leaves the clone untouched. `--push` pushes the branch, after the user confirms as in step 9. `--verify` asks `amp skill info` for one skill from the pack and from each set and reports found or missing; the index reads the pushed repository, so verify after the push. Done when the report shows a commit, nothing refused, and every verified skill found.

## Do not use this skill for

- **Installing or editing a skill no set hands off to.** The script manages
  each set's root skills and the dependencies it installed for them; others
  are unmanaged and left alone.
- **Syncing a skill set from a repository without a set file.** Add
  `sets/<name>/set.json` first, with a dialect the pack ships or a new one
  under `dialects/`; the script reads nothing it is not configured for.
- **Changing what a pstack skill says upstream.** Adaptations change only how a
  skill runs in this harness. A content change belongs in `cursor/plugins`, and
  the next sync brings it in.
