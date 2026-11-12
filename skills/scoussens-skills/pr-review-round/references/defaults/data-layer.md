# Data-layer review defaults

Apply when behavior reads, writes, migrates or caches persisted state, including changes hidden behind an API or UI. Use the repository's persistence model; do not assume SQL, an ORM or a particular database.

- Trace changed fields from every relevant writer to reader. Exercise existing records as well as new writes, especially renamed fields, changed defaults, nullability and serialization.
- For schema or data migrations, check forward application and recovery against the documented rollback/roll-forward strategy. Identify deployment ordering and mixed-version compatibility; do not require a destructive down migration as a universal rule.
- Check constraints, indexes, query predicates and tenant/owner scoping against actual reads and writes. Establish reachability before claiming data loss or an authorization bypass.
- For concurrent updates, retries or partial failure, verify the required atomicity and idempotency. Test an interrupted operation or competing writer when it can violate the contract.
- Check cache invalidation, pagination and query cost where the diff changes their behavior. Use representative data and a measured query plan when performance is part of acceptance; do not infer performance from code shape alone.

Retain source revisions, setup/data assumptions, observed results and untested environments. A mock that cannot enforce the changed storage constraint does not prove that constraint. Block only on a demonstrated failure or an unmet documented requirement; record unavailable integration evidence as an evidence gap.
