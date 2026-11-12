# Security review defaults

Apply where a change affects trust, identity, authorization, sensitive data, resource access or execution of untrusted input. Inspect the actual enforcement path and attacker-controlled input before assigning severity.

- Check authentication separately from authorization, including tenant/owner boundaries and privilege changes. Exercise a denied actor as well as an allowed actor.
- Trace untrusted values into queries, shell execution, file paths, redirects and rendered content. Verify the relevant encoding or parameterization at the sink.
- Check credential and sensitive-data handling in logs, errors, storage and output. Preserve documented retention and access rules.
- Check whether dependency, build or deployment changes add execution or supply-chain privileges outside the intended boundary.
- Verify resource limits and abuse paths when the change exposes expensive or repeatable operations.

Describe reachability, the affected actor and concrete consequence. An unreachable hypothetical or missing local guard is not a proven vulnerability. Do not perform destructive tests, disclose secrets or exercise a production exploit to obtain evidence.
