# Synthetic agent-grown test suite dossier

GitHub Actions, private TypeScript service. Coding agents write most changes.
Over 13 weeks, test lines grew from 41,000 to 88,000 while `src/` grew from
52,000 to 61,000 lines. The required `test` job's median successful duration
grew from 6m10s to 13m50s across 30 comparable first attempts per period, all
on the same runner class. Setup is a stable 1m40s; the remainder is Vitest.

Excerpts from the suite:

1. `src/audit/hash.test.ts` asserts
   `expect(digest).toMatch(/^sha256:[a-f0-9]{64}$/)` and then
   `expect(digest).not.toContain("synthetic")`. A separate test,
   `disclosure.test.ts`, checks that synthetic records are labeled in the
   exported report. Runtime 40 ms.
2. `src/net/retry.test.ts` mocks the private helper `computeDelay` and asserts
   it was called with `(1)`, `(2)`, `(3)` in order. `src/net/retry.behavior.test.ts`
   drives the public `withRetry` against a fake clock and asserts three attempts,
   backoff totals, and no retry on HTTP 400. Both pass today.
3. `src/config/parse-config.test.ts` (212 lines) and
   `src/config/config-parser.test.ts` (198 lines) were added by different agent
   sessions. 31 of their 38 cases assert the same defaults and validation errors;
   7 cases in `config-parser.test.ts` cover environment-variable overrides that
   no other test checks.
4. `src/webhooks/delivery.test.ts` fails about 1 in 15 first attempts with a
   port-in-use error and passes on retry. It is the only test that verifies
   webhook signature rejection. Runtime 9 s.
5. `src/billing/invoice.e2e.test.ts` takes 3m05s, the slowest file. It is the
   only test that exercises tax rounding through the database.

No test-growth limit exists. Maintainers have not stated a deletion target.
