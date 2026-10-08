# Representative orchestration cases

These historical orchestration failure patterns test the runner's reusable
decisions. They are not current ticket status or extra standing authorization.

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

The runnable local checks validate JSON and HTML contracts. The prompts in
`evals/evals.json` test the agent's decisions. Running the former does not mean
the latter were executed, nor does either replay the historical checks.
