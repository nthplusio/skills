# Trace the changed trust boundary

## Identify who can influence execution

Trace contributor-controlled source, workflow configuration, event data,
dependencies, caches, and artifacts into credential-bearing tasks. Record
reader and writer identities, token permissions, reachable networks, runner
persistence, and artifact consumers.

A checksum establishes content identity, not who authorized or produced it.
A short-lived credential limits lifetime but still needs a restrictive identity
and audience policy. A clean runner does not make downloaded code trusted.

## Keep privileged consumers separate

Run untrusted review code without release credentials or writable trusted caches.
Before privilege elevation, verify the allowed source revision, producer identity,
workflow or builder, expected build inputs, and artifact digest. Downloading an
artifact from a successful run is not itself an authorization decision.

Prefer isolated disposable execution where untrusted code can run. Inspect
self-hosted persistence, shared directories, container privileges, and network
access. Preserve least privilege, action and dependency pinning policy, package
integrity, required scans, and secret handling when changing setup for speed.

For caches, distinguish read access from write access. Include all output-changing
inputs and segregate trust where the provider requires it. A lockfile hash does
not identify a trusted cache writer. Cache and artifact retention must not expose
credentials or unnecessarily retain private source and diagnostics.

## Verify provenance at consumption

Connect the authorized source, build, tested output, and deployed digest. Enforce
the consumer's trusted builder and parameter policy rather than merely upload an
attestation. Choose controls from repository threats and release requirements.

[SLSA artifact verification](https://slsa.dev/spec/v1.1/verifying-artifacts)
describes checks at consumption. Provenance, isolation, declared-input builds,
and [bit-reproducible output](https://reproducible-builds.org/docs/definition/)
are distinct properties. A pinned image alone does not prove all of them.

## Check the boundary without production credentials

Use disposable tests or configuration inspection to check fork inputs, cache
writer scope, artifact substitution, unexpected revisions, missing verification,
and permission propagation. Inspect secret names and policy, not secret values.
Keep hosted access-control changes separately authorized.

Accept the change when every newly reachable privileged operation has a verified
trust decision and the runner, cache, and artifact policies agree. Use the
detected provider reference for effective event and credential semantics.
