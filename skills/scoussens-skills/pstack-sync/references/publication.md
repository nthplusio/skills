# Optional publication and contribution

Read this only for a separately requested publication, pack refresh or seed
contribution. Ordinary sync ends with its local report. Resolve the named
destination and affected audience before writes; personal repositories need
publication authority just as shared repositories do. Saved profile commands
describe a capability, not consent. A contribution request does not authorize
publishing an installation, and publication does not authorize an upstream PR.

Use the installed absolute `scripts/sync.py` path and quote all path arguments,
as in the main workflow. Preserve unrelated work and complete preparation
before discovery or profile writes. If an operation requires a clean clone,
hold it or use a separate clean checkout rather than discarding local drift.

## Publish an ordinary sync

After the local review and commit, publish and reload as the profile's
Destination says, only with explicit authority for that destination. Confirm
the personal or shared audience before pushing. Report whether publication
and reload succeeded; a local commit is not evidence of either.

## Refresh a workspace repository from the pack

This is an administrative refresh of repositories this pack feeds, not a
general package builder or a portable ZIP exporter.

```bash
python3 "<installed skill directory>/scripts/sync.py" publish \
  --pack "<pack checkout>" --repo "<workspace clone>" --harness <harness> --dry-run
```

Run the dry run first. It uses throwaway worktrees without changing, committing
or pushing either destination clone. Inspect its report and affected paths
before running without `--dry-run` under the approved refresh authority.

The refresh copies the pack's tracked skill files, excluding ignored files
and `node_modules`; removes retired skills only when the previous
`.nthplusio-skills/pack-manifest.json` names them; runs `sync` for every shipped
set; appends `profile_gaps_in_seed` rows to the durable profile and syncs again.
It commits `Refresh workspace skills from nthplusio/skills@<sha>` with that
repository's identity. Exit code 2 refuses a commit containing a `node_modules`
directory or a file over 2 MB and names the offending paths; both prevent skill
indexing.

For Amp plugins, add `--plugins-repo "<workspace plugins clone>"`. This replaces
pack-named plugin directories, removes retired plugins only when that clone's
manifest names them, and commits with that clone's identity. Other plugin
directories remain untouched. Authorize both destinations before including
them; `--push` pushes both repositories, not just the skills repository.

The report's `attention` list needs human or agent reconciliation through the
ordinary adaptation step: `needs_adaptation`, `local_drift`, `profile_gaps` and
unresolved dependencies are not cleared by publication. Keep unrelated drift
intact and withhold the push until the required reconciliation is complete.

Add `--push` only after explicit confirmation for the named repositories.
For Amp, `--verify` queries `amp skill info` for one pack skill and one from
each set, and checks loaded plugins when supplied. The index reads pushed
state, so a verification before pushing describes the previous publication,
not the local refresh. Report unavailable verification tools rather than
claiming index success. Done when the report shows the intended commit,
nothing refused, and each requested post-push check found its target.

## Contribute reusable adaptations

When shared adaptations could help other installations, offer a seed
contribution. With authority to change the pack checkout, run:

```bash
python3 "<installed skill directory>/scripts/sync.py" seed \
  --repo "<skills-dir>" --harness <harness> \
  --out "<pack checkout>/skills/scoussens-skills/pstack-sync"
```

Add `--set <set>` for a non-default set. The command writes
`sets/<set>/transform.json` without its local block and the shared profile
using the pack's header and the install's rows. Repository-specific mappings
and local choices stay in durable install state. Review the resulting diff
for that boundary. Commit, push or open an upstream pull request only under
the corresponding authority. Done when the requested local contribution is
reviewed and its delivery state is reported without implying publication.
