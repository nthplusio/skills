# Synthetic sharding and runner-size dossier

GitHub Actions, private repository. Every job uses a 16-vCPU larger Linux
runner. Synthetic account rate card for this exercise: 2-vCPU $0.008 per
minute, 4-vCPU $0.016, 16-vCPU $0.064, billed per job and rounded up to the
whole minute. These are not GitHub's published prices.

`unit` is a 24-shard matrix. Measured over 25 successful first attempts on the
same commit range:

- Every shard spends 2m30s to 2m50s on checkout, `npm ci`, and `npm run build`.
- 23 shards run tests for 25 to 70 seconds. Shard 7 runs for 4m10s because the
  file split places `report-render.test.ts` (3m20s alone) there.
- Peak CPU per shard stays under 20% of 16 vCPUs. Peak memory is 2.1 GiB of
  64 GiB. No out-of-memory events occurred.
- The required `ci-gate` job waits for all shards. Median trigger-to-gate time
  is 7m20s, and shard 7 finishes last in 24 of 25 runs.

`lint` runs `eslint` and `tsc --noEmit` serially for 2m10s after a 1m50s
install. Peak CPU is 7%.

The team's proposal is to raise the matrix to 40 shards to bring PR feedback
under 5 minutes. Runner queue time is under 10 seconds for all jobs. Cost and
PR feedback time both matter; no larger-runner contract or hosted rule
requires the 16-vCPU class.
