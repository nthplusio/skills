# Local requirements and review completion

This repository uses local Markdown files for requirements. Resolve the file named by the task, PR or owner; existing plans live in `docs/plans/`. A review can name another repository-relative Markdown path. No hosted tracker or issue-ID format is required.

Read the file's acceptance criteria and relevant recorded owner decisions. Do not treat every historical plan as current policy or choose a spec by title similarity alone. If the governing file is unclear, ask for its path and mark Spec incomplete; do not create a ticket or invent acceptance criteria.

When a PR has a confirmed linked Linear ticket, read its current status before completing the assessment. Record the ticket link, status and retrieval time beside the local requirement evidence, keeping ticket status separate from the PR state and acceptance result. Flag mismatches against a documented lifecycle; do not infer a universal required status. If the lookup fails, report status as unknown and name the evidence needed. A PR without a linked Linear ticket remains valid under the local-file policy. This check is read-only: leave statuses, labels and automation-owned transitions unchanged.

Review assessment does not authorize changing requirements, labels or completion state. Report criterion-level results and remaining code, evidence, owner-decision or reviewer work. A merge or green CI alone does not establish acceptance. Leave any completion notation unchanged unless the owner authorizes its update.
