# Capture and approval

## Extract without broadening the source

Read the relevant source window, including corrections and disagreement, not just
an isolated sentence. Resolve external references when permitted. If a referenced
document is inaccessible, retain that limitation instead of inferring its contents.

Classify each claim:

| Claim | Registry treatment |
| --- | --- |
| Explicit decision from a designated owner | Eligible for exact-meaning approval |
| Suggestion, tentative language, agent interpretation | Proposed revision |
| Report of another person's decision | Proposal until attribution is verified |
| Example | Supporting scenario, not an inferred universal rule |
| Conflicting statements | Preserve both claims and ask the owner to resolve |
| Technical fact available in code | Investigate it; record evidence, not approval |

Normalize vocabulary against the glossary. Preserve quantifiers, boundaries,
actor, trigger, timing, units, defaults, failure outcomes, and exceptions. A rule
denying shipped-order cancellation does not imply that all unshipped orders can
be cancelled. An unspecified timezone or currency remains a gap when it changes
the decision. A hierarchy groups rules; it grants no inherited conditions.

Match existing IDs before allocating one. For an amendment, append a revision
under the same business identity. For a split or merge, allocate successor IDs,
pin `supersedes` relationships to predecessor revisions, and stage retirement
revisions. Capture all proposals before approving the coordinated decision.

## Preserve the source-to-rule interpretation

The source ID identifies one immutable source version. Its locator identifies
the message, transcript span, or questionnaire publication and feedback UUID.
Use a stable claim ID for one interpretation of that span. On replay, reuse both.
If interpretation changes, allocate a correction claim ID and explain the change
in the correction source. Idempotence means safe replay, not identical extraction
from independent model runs.

Retain only authorized excerpts; `excerpt: null` is valid. Keep attribution,
locator, and an authorized source summary where source access is restricted.
The captured statement must stand alone without copying private context.

Before importing approval, compare every material rule field with the decision.
Representation-only normalization preserves approval; extra conditions, exceptions,
examples with new guarantees, or a narrowed scope require approval of that exact
interpretation. Record the comparison in the source's `authority_evidence`, with
the identity/authority evidence route and exact source locator. This is the
reader's accountable attestation, not a cryptographic identity check.

## Consume questionnaire decisions without inventing authority

Read the saved publication, original feedback, receipt, and proposal outcome.
The questionnaire's accepted answer stays accepted in its own workflow. The
registry separately establishes whether it is authorized policy.

Self-entered names and role-holder suggestions are not authority. Establish the
actor through the authenticated conversation or the project's trusted approval
process and match the designated domain owner. When that cannot be established,
retain the answer as proposal evidence with `authority_evidence: null`.

Retrieve the exact publication revision the owner saw. The latest JSONL handoff
alone may not preserve earlier wording; consult the questionnaire's publication
history/database or an authorized archived snapshot. If unavailable, leave
approval unresolved. Never reconstruct an approved payload from a newer question.

For direct approval in conversation, retain the exact message and the displayed
proposal revision, or document why the original explicit decision has exactly
the captured meaning. No second ceremony is needed when these facts are known.

## Example decision

Use `target` to populate `targets`; never guess or manually compute a digest.
Register `source_id` first. Replace all synthetic values with verified records.

```json
{
  "schema_version": 1,
  "id": "decision-001",
  "kind": "approve",
  "authority_id": "owner-1",
  "actor": "Order operations owner",
  "source_id": "conversation-001",
  "decided_at": "2026-01-01T12:00:00Z",
  "effective_at": "2026-01-01T12:00:00Z",
  "targets": ["replace this array with target command objects"],
  "waiver": null
}
```

The placeholder array above is intentionally not a valid decision. Each real
target contains `rule_id`, `revision`, and `digest`. A rejection resolves only that
revision; correction requires another proposal. A waiver uses `kind: waive`, one
target, and `waiver: {finding_id, code_commit, expires_at, reason}`. It does not
approve new policy. Its effective interval includes the start and excludes expiry.

Record policy effectivity explicitly. A future-approved revision does not replace
the effective revision early. Treat retroactive corrections as a separately
reviewed migration; the version-one CLI rejects effectivity before the decision.
