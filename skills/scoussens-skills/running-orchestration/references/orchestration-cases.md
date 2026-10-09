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
| Tool capabilities are known, but configuration and working-directory paths have not been chosen. | Propose both local paths in one focused question and wait before saving settings. | Treating a discovered capability or a suggested default as a user choice. |
| An explicit project/team configuration overrides personal defaults. | Use the selected local JSON and its saved choices; leave personal settings unchanged. | Reconfirming unchanged choices or overwriting personal defaults with project settings. |
| The harness restores the conversation, but local display files are missing. | Restore owners, decisions, IDs, and scoped evidence assessments from accessible context. Retrieve missing receipts and rebuild the display, with remaining gaps explicit. | Reassigning owners, replaying sufficient checks, or introducing a separate recovery service because display files are absent. |
| Several owners need unrelated user decisions. | Show one prioritized queue with recommendations, affected work and direct discussion routes. Local choices stay with their owners; cross-ticket choices stay with the coordinator. | Serializing every conversation behind a coordinator's blocking dialog. |
| The user answers a local choice in its owner conversation or by ID to the coordinator. | Apply or relay the actual answer within its scope, retain its source once, and remove the answered item from the pending queue. | Asking the user to repeat it or treating a local answer as broad publication permission. |
| An owner is stopped at a human-only native input gate. | Link the user to that conversation and keep the decision pending until the gate is actually answered. | Claiming a queued message, clipboard action or helper can satisfy the gate. |

The runnable local checks validate JSON and HTML contracts. The prompts in
`evals/evals.json` test the agent's decisions. Running the former does not mean
the latter were executed, nor does either replay the historical checks.
