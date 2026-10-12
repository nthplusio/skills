# Synthetic evidence: latency with a deploy gate

Fictional private repository; all figures are illustrative. PR and push runs
are separate classes. Comparable PR samples show 27 minutes elapsed: setup and
install 50 seconds, one `pnpm verify` step 25 minutes, other required work 65
seconds. Treat durations as synthetic observations, not benchmarks.

Repository ruleset requires check `verify`. Classic branch protection has no
required checks. `migrate` has `needs: verify`; Railway waits for the main
commit's check suite. Do not cancel in-progress main runs. Mutation testing,
advisory coverage, and nightly work were already removed.
