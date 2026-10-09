# Representative orchestration cases

These cases cover historical failure patterns and confirmed setup/resume
choices. They are not current ticket status or extra standing authorization.

| Situation | Coordinator action | Mistake this prevents |
| --- | --- | --- |
| An owner provides focused test receipts for the unchanged code and environment. | Inspect and retain the receipt once. Reuse it for the same claim. | Running the same suite again to reassure the coordinator. |
| A workflow hash differs but its relevant behavioral difference is already explained and checked. | Assess that difference against the claimed outcome. Proceed if the evidence settles it; name any uncovered failure before another check. | Searching every branch for matching bytes or asking for a branch refresh without a behavioral reason. |
| Reviewer workflow succeeds but the posted-review result is empty. | Keep review completion pending/blocked. The successful job is limited proof, not an actual review. | Treating green CI as a delivered review. |
| Scoped tests pass while an inherited whole-suite failure remains. | Record both receipts and the agreed scope of readiness. Keep live persistence and business acceptance separate. | Erasing the failure or claiming authenticated/live acceptance from local tests. |
| Expanded investigation disproves an earlier repair-complete verdict. | Preserve the old evidence as superseded, record the correction, and return fixes to the existing owner. | Losing failed evidence or creating a replacement owner for a new phase. |
| Two owners need one authenticated runtime. | Separate their environments or reserve one runtime lane. Keep unrelated tickets moving. | Unnecessary global serialization or overlapping mutation of one runtime. |
| An approved merge would also trigger a broader automatic deployment. | Describe the indirect effect and obtain the missing scope before that action. | Treating merge permission as permission for an unapproved deployment consequence. |
| A worker becomes idle with required CI or a requested review still outstanding. | Treat it as unfinished and route the next action. | Closing an owner because its agent stopped talking. |
| An owner finishes its assignment and all known obligations. | Capture durable proof/work location/handoff, update status, close it with the harness operation, and retain its owner reference. | Leaving completed owners open or losing evidence when closing them. |
| Discovery is absent when setup starts. | Run discovery and read its saved report before the durable interview. | Asking the user for inspectable tool facts or configuring unsupported features. |
| Another harness already has a setup profile. | Add the discovered name's profile while preserving the other profile and shared project policy. | Overwriting choices when moving between harnesses. |
| A new run overrides setup's scan interval. | Confirm and save the interval in this run only. | Changing the default for future runs or repeating the project interview. |
| The harness restores the conversation, but local display files are missing. | Restore owners, decisions, IDs, and scoped evidence assessments from accessible context. Retrieve missing receipts and rebuild the display, with remaining gaps explicit. | Reassigning owners, replaying sufficient checks, or introducing a separate recovery service because display files are absent. |
| Several owners need unrelated user decisions. | Show one prioritized queue with recommendations, affected work and direct discussion routes. Local choices stay with their owners; cross-ticket choices stay with the coordinator. | Serializing every conversation behind a coordinator's blocking dialog. |
| The user answers a local choice in its owner conversation or by ID to the coordinator. | Apply or relay the actual answer within its scope, retain its source once, and remove the answered item from the pending queue. | Asking the user to repeat it or treating a local answer as broad publication permission. |
| An owner is stopped at a human-only native input gate. | Link the user to that conversation and keep the decision pending until the gate is actually answered. | Claiming a queued message, clipboard action or helper can satisfy the gate. |
| A closed owner appears available for an unrelated ticket. | Inspect its original binding and locate or assign the unrelated ticket's own owner. Reopen the closed owner only for its original ticket's follow-up. | Treating closure as permission to repurpose an owner. |
| Repository ticket policy is missing or unconfirmed. | Route to setup's interview and hold affected assignments until setup validates. | Treating a suggested format as settled or moving the project interview into run. |
| A ticket combines independent outcomes or exceeds the confirmed criterion limit. | Preserve the parent and draft smaller children for approval, with all outcomes and proof retained. | Silently rewriting shared tickets or hiding extra outcomes inside five broad criteria. |

The runnable local checks validate JSON and HTML contracts. The prompts in
`evals/evals.json` test the agent's decisions. Running the former does not mean
the latter were executed, nor does either replay the historical checks.
