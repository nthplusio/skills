# Harness profile: <harness>

How pstack's needs map onto <harness>. Built and maintained per [`../references/adapting.md`](../references/adapting.md); need IDs come from [`../dialects/cursor.json`](../dialects/cursor.json) and each set's `extra_needs` in `sets/<set>/set.json`.

## Orchestration naming

Map the portable [run-membership contract](../references/orchestration.md#make-run-membership-visible) to observed tools. Name the launch title/name/description field, inspection and rename operations, and returned handle type for sessions and subagents. Cite their schemas or a verified probe. If a capability is unavailable, record the limitation and use the prefixed task description and brief. Native `preflight.naming` supplies titles; scripted execution retains its existing persisted run tag. Neither platform nesting nor a shared worktree establishes membership.

## Destination

- **Skills directory**: which of the locations discovery records in `skills.locations` pstack goes into, and how to prepare it. Source:
- **Publish**: what makes a change take effect (commit and push, copy, nothing). Source:
- **Reload**: after publishing, as discovery records in `skills.reload`.
- **Name shadowing**: which other skill sources mask this directory. Source:

## Needs

Add a row for each need in [`../dialects/cursor.json`](../dialects/cursor.json), and in each set's `extra_needs`, that names no discovery fields. The others take their facts from the repository's `.nthplusio-skills/discovery.json`; give one a row only to override it, per [`../references/adapting.md`](../references/adapting.md).

| Need | Support | <harness> equivalent | Source |
| --- | --- | --- | --- |
| `<need id>` | native / keep / substitute / partial / none | | |
