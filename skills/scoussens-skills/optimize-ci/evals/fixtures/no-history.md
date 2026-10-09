# Synthetic repository profile: no CI history

Small team (three maintainers), TypeScript service, one production deployment
per week. A change must pass unit tests and typecheck before merge; deployment
must use the exact revision that passed integration checks. Contributions come
from same-repository branches only today, but the project intends to accept
fork contributions later. No run history, runner contract, or provider account
is available. This fixture intentionally contains no timing observations.

The repository uses Node 22, npm, and a committed package-lock.json. Native
commands are `npm ci`, `npm run typecheck`, `npm run test:unit`,
`npm run test:integration`, and `npm run build`. The build produces `dist/`.
Integration tests use a disposable PostgreSQL 15 service. There is one package,
no task graph tool, and no maintainer assigned to operating a runner fleet.
