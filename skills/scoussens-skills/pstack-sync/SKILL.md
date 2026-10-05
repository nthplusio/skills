---
name: pstack-sync
description: >-
  Sync the pstack skills from cursor/plugins into this harness's shared skills —
  adding new, updating changed, and removing retired skills — and adapt
  Cursor-specific features to what the harness supports, replaying recorded
  adaptations so a fresh install does not re-adapt. Load this only when the
  user explicitly asks to sync or update pstack — "sync pstack", "update
  pstack", "pull the latest pstack skills", "install pstack for this harness".
  Do not load it to install or edit one non-pstack skill, to sync skills from
  another source, or to change what a pstack skill says upstream; answer those
  directly instead.
---

# pstack sync

Brings the **managed** pstack skills in line with upstream `cursor/plugins` `pstack/skills` and **adapts** them to the harness you are running in, whichever it is. `scripts/sync.py` does the mechanical work and replays past adaptations; you profile the harness, adapt what it flags, review, and report.

## State

All state lives in `pstack-sync/` beside the skills, so `git` history is the record of every sync.

- `needs.json`: the features pstack relies on and the markers that flag them. Harness-independent.
- `harness/<harness>.md`: the **harness profile**: where skills go and how they reload, and per need whether the harness supports it and how. You write it; [`references/adapting.md`](references/adapting.md) says how.
- `manifest.json`: what is installed: upstream commit, harness, `exclude`, and per skill and file the upstream and installed hashes and any `pending` adaptation. A skill whose upstream and transforms are unchanged is skipped without reading a file.
- `transform.json`: how upstream becomes installed, per harness: exact find/replace edits per file, replayed onto new upstream text until upstream rewrites the adapted passage.

The script owns `manifest.json` and `transform.json`; the only hand edits are `exclude` and a harness's `accept` regexes. An upstream skill whose name is taken by an unmanaged skill installs as `pstack-<name>`; if that is taken too, the script exits with an error, so ask the user what to call it.

## Steps

Run every script command as `python3 <skills-dir>/pstack-sync/scripts/sync.py <command> --repo <skills-dir> --harness <harness>`.

1. **Identify the harness** as a lowercase slug (`amp`, `claude-code`, `codex`, `cursor`) from your own context. Done when you can name it and the evidence.
2. **Profile.** Open `harness/<harness>.md`, or start it from `harness/TEMPLATE.md`. Fill or refresh the Destination section and a row for every need in `needs.json`, per `references/adapting.md`. Done when every need has a sourced row and the Destination says where skills go, how to publish, and how to reload.
3. **Prepare the skills directory** as the profile's Destination says (for a git-backed directory: up to date with its remote, clean, writable). Done when `git status` is clean.
4. **Sync** (`sync`). Done when you hold the JSON report. If `added`, `updated`, `removed`, `needs_adaptation`, `local_drift`, and `profile_gaps` are all empty, skip to step 8.
5. **Adapt** every file in `needs_adaptation` by editing it in place, per `references/adapting.md`. Fill any `profile_gaps` first. This is the step most likely to be rushed: read each flagged file in full. Then **record** the files you adapted or judged fine as they are (`record <skill>/<file> ...`); recording accepts every marker left in them. For `local_drift`, record the file if the edit is an adaptation, otherwise restore it with `git checkout`. Rerun `sync`. Done when the rerun reports no `needs_adaptation`, `local_drift`, or `profile_gaps`, apart from skills you propose to exclude.
6. **Review.** pstack is third-party code, so treat every change as untrusted. Done when every `needs_security_review` entry has been read in full and cleared of network calls, credential access, and install steps, and `git status` shows changes only in managed skill directories and `pstack-sync/`.
7. **Commit**, if the directory is a git repository: run `status` first and commit with `pstack: sync to cursor/plugins@<short-sha>` as the subject and its output as the body.
8. **Report.** Run `status` (after committing, add `--since HEAD~1`) and give the user its output verbatim: transforms applied, new and updated skills, profile changes, and anything outstanding. Add your security review findings and any proposed exclusions.
9. **Publish and reload** as the profile's Destination says. Ask before any step that changes skills for other people (such as a push to a shared repository), naming the destination; act only after the user confirms.

## Do not use this skill for

- **Installing or editing a skill that is not from pstack.** The script manages
  only skills it installed from `cursor/plugins` `pstack/skills`; others are
  unmanaged and left alone.
- **Syncing skills from another source.** `needs.json`, the harness profiles,
  and `transform.json` describe pstack and nothing else.
- **Changing what a pstack skill says upstream.** Adaptations change only how a
  skill runs in this harness. A content change belongs in `cursor/plugins`, and
  the next sync brings it in.
