# Verification

Run the public-CLI suite from any directory:

```bash
python3 -B -m unittest discover -s "$SKILL/evals" -p 'test_*.py' -v
```

It creates a disposable Git application from `evals/fixtures/shop/orders.py` and
the synthetic conversation in `assets/capture.example.json`. It exercises capture,
approval, idempotent replay, exact payload binding, unresolved exceptions, future
effectivity, immutable history, pinned relationships, catalogue reconciliation,
waiver expiry, and base/head reporting. It runs actual application scenarios:

| State | Accepted original policy | Changed implementation |
| --- | --- | --- |
| New order | Cancellation allowed | Allowed |
| Packing order | Cancellation allowed | Denied |
| Shipped order | Cancellation denied | Denied |

The asymmetric packing case proves the violation. A proposed amendment does not
clear it. An approved replacement plus head conformance changes the old-policy
finding's disposition to `approved-policy-change`, preserving the discrepancy.
Missing assessments become `not-assessed`, and stale report digests fail.

The repair regression reverses the code change without changing approved policy.
The base violation becomes `resolved-in-head` only with head/base conformance
to the same rule revision. Its original evidence remains visible and the summary
still requires review. Missing or nonconforming head/base assessments leave the
historical violation unresolved, even when head/head is reported conforming.

The integration test runs the actual catalogue CLI through discovery, partition,
checking, batches, and build before importing its output. It uses prepared reader
and checker records: this proves compatibility, not independent extraction accuracy.
When the catalogue is installed elsewhere, set `BR_CATALOGUE_SKILL` to its directory.
Without it the integration test skips explicitly; registry tests still run.

`evals/evals.json` describes separate agent workflow evaluations. Run them with
retained source decisions and outputs before claiming extraction or authority
recognition accuracy. Unit fixtures do not prove those judgments, questionnaire
identity, hosting access controls, or production conformance.

No explorer UI code changes are required by the integration. If changing its
renderer, use the catalogue's browser verification workflow rather than treating
a generated HTML file as visual proof.
