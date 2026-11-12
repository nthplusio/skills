# Portable skill and distribution review

## Applicability and sources

Apply these checks when a skill's instructions, bundled resources, configuration, host metadata or installation path changes. The source contracts are `README.md`, `distribution/README.md`, `docs/installation.md` and `distribution/agent-evaluation.md`. Use `package.json` and `.github/workflows/validate.yml` for the checks that exist now.

## Checks and evidence

- Keep reusable behavior independent of a particular harness or ticket provider. Repository choices belong in setup/configuration outputs. Native integrations may remain product-specific when their scope and prerequisites are explicit. Trace changed choices to their owning configuration and actual consumers.
- Check complete installed bundles, required companions and local resource links. Where a skill owns shared copies, verify its existing consistency check. For packaging changes, inspect generated/installed files rather than source alone.
- Preserve invocation and action boundaries. Loading a skill or selecting a reviewer mode grants no external-write authority. Check affected authority and invocation controls, including a case where permission or capability is absent.
- Keep secrets and repository-specific private material out of reusable bundles. Inspect exported paths/content. Record when the private-terms check has no configured patterns; its successful exit then provides no private-term coverage.
- Separate deterministic tests, agent behavior with fixtures and actual target-client execution. Cite pinned source, commands, observed results and exclusions. Missing client or runtime evidence remains missing; do not turn it into a success or an automatic claim that the implementation is defective.

## Finding thresholds

A documented-contract violation or independently reproduced incorrect behavior can block the relevant axis. Missing required evidence is an evidence gap owned by the person who can obtain it; unexamined coverage is reviewer-owned incomplete work. State the criterion, evidence and smallest unblock. A portability preference without a violated contract or demonstrated consequence is nonblocking advice. Do not require another harness, tracker, live deployment or a new test framework merely to satisfy this checklist.
