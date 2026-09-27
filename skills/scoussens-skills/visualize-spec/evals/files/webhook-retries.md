ORD-212 · Harden outbound webhook delivery

**Context.** `send_webhook` is fire-and-forget over a synchronous `requests.post` with no timeout, invoked inline on the order-create hot path. A slow subscriber blocks order creation; a 5xx or connection reset drops the event on the floor. Merchants reconcile by polling, and support gets ~30 tickets/week about "missed" order events.

**Ask.** Make delivery at-least-once and idempotent:

- Decouple dispatch from the request path — the handler enqueues a `DeliveryJob`, and a worker drains the queue.
- Retries with exponential backoff + full jitter, base 2s, cap 5m, max 8 attempts. Retry on 5xx, 429 (honour `Retry-After`), timeouts, and connection errors. 4xx other than 429 is terminal.
- Stamp an `Idempotency-Key` header (stable per event × subscriber) so consumers can dedupe on replay.
- Exhausted jobs go to a DLQ with the last error; ops can redrive from an admin endpoint.
- Introduce a `DeliveryTransport` port with an `HttpTransport` adapter so the dispatcher is testable against a fake without monkeypatching `requests`.
- Per-attempt timeout 10s.

**Testing.** Unit-test the dispatcher through the `DeliveryTransport` port with a `FakeTransport` that scripts responses: retry schedule (inject the clock + RNG so backoff is deterministic), terminal-vs-retryable classification, DLQ on exhaustion, same `Idempotency-Key` across attempts. Keep the existing app test green; extend it to assert order-create returns 201 even when the subscriber is down.

**Acceptance.**
- p99 order-create latency unaffected by subscriber latency.
- No event lost on a subscriber outage shorter than the retry window (~17 min).
- Redrive from DLQ re-sends with the original `Idempotency-Key`.

**Not doing.** Webhook signing (ORD-219). Persistent queue — in-memory is fine for this pass; durability is ORD-220.
