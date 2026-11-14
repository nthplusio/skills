# Verification review defaults

Apply to every substantive review; scale the checks to the changed contract. Repository verification configuration owns commands, required environments and coverage exclusions.

- Map every acceptance criterion to its quoted source, implemented path, observed evidence/source/time, result and limit. Separate independent verification, author reports, missing evidence and scoped owner-accepted gaps.
- Run available checks against pinned head/base revisions. Use a separate clean verification worktree for mutable app/test sessions; identify the actual served build, not just the checkout a command started from.
- Choose inputs where likely wrong implementations differ from the contract, including disagreeing concrete variants inside one broad category (such as two archive formats), not only unrelated categories. Include both sides of an affected boundary; check observable results, not only exit status or mocked call counts.
- Exercise changed behavior through real first-party consumers when runnable. A helper-only or mocked component test does not verify its callers' event handling, state, persistence or accessibility. Fake external boundaries where needed; use repository test-boundary policy for what may be replaced. Scope this to changed behavior, not an unrelated legacy-suite rewrite.
- Preserve failures through shell pipelines and log printing. Retain commands, environment assumptions, tested states and exclusions. A passing gate proves only what it exercises.
- For changed UI, inspect rendered representative states when runnable and exercise changed pointer/keyboard behavior. For a service or CLI, inspect its actual observable output/state. Missing tools or access remain explicit evidence gaps.
- Refresh current discussion and owner decisions before reusing a verdict. Preserve the original evidence time and scope, and invalidate affected checks when code, requirements or review references change.

Green tooling cannot satisfy a required runtime demonstration or prove unexamined work. Keep code defects, missing evidence, owner decisions and unfinished review distinct, with an owner and a concrete next action.
