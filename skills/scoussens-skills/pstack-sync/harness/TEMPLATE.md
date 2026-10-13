# Harness profile: <harness>

How pstack's needs map onto <harness>. Built and maintained per [`../references/adapting.md`](../references/adapting.md); need IDs come from [`../needs.json`](../needs.json).

## Destination

- **Skills directory**: which of the locations discovery records in `skills.locations` pstack goes into, and how to prepare it. Source:
- **Publish**: what makes a change take effect (commit and push, copy, nothing). Source:
- **Reload**: after publishing, as discovery records in `skills.reload`.
- **Name shadowing**: which other skill sources mask this directory. Source:

## Needs

Add a row for each need in [`../needs.json`](../needs.json) that names no discovery fields. The others take their facts from the repository's `.nthplusio-skills/discovery.json`; give one a row only to override it, per [`../references/adapting.md`](../references/adapting.md).

| Need | Support | <harness> equivalent | Source |
| --- | --- | --- | --- |
| `<need id>` | native / keep / substitute / partial / none | | |
