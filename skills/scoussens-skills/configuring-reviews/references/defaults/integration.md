# Integration review defaults

Apply to changed boundaries between modules, services, external APIs, event producers/consumers or deployment components. The boundary may be in-process, synchronous, asynchronous or file-based.

- Read both sides of the contract: payload/schema, units, ordering, error behavior and version compatibility. Trace who actually produces and consumes the changed value.
- Check validation at the external boundary and ownership inside it. Verify missing, malformed and boundary values that distinguish the correct implementation from a plausible wrong one.
- Exercise timeout, retry, duplicate delivery and partial-success behavior when the integration supports them. Establish which operation can have committed before a failure; do not blindly retry non-idempotent work.
- Verify authentication, secret handling and least-privilege access at the real enforcement point. Do not infer a missing guard from the absence of a local decorator or wrapper.
- Check rollout order and observability: can operators detect, diagnose and recover from the changed failure mode without leaking sensitive payloads?

Use contract tests or an authorized integration environment for the affected boundary. A unit test with matching producer/consumer mocks can reproduce the same wrong assumption on both sides. Record provider access limits instead of claiming live compatibility.
