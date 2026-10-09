# Synthetic selector and aggregate-gate dossier

The selector uses a project graph. A missing comparison base, unknown file, or
truncated diff must select the full suite. `packages/shared-lock.json` and
`ci/task-map.yml` are shared inputs with transitive consumers `api`, `web`, and
`worker`.

Current aggregate gate checks only that at least one child job succeeded. It
does not inspect the expected task list, and provider skip status is treated as
success. Required tasks are `api`, `web`, and `worker`. A valid selector may
justify a skip only when it records the comparison revision and selected set.
Failed, cancelled, or missing prerequisites must not yield a successful gate.
