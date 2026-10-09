# Synthetic shared runner-pool evidence

Fictional organization pool shared by 12 repositories, capacity 8 Linux slots.
During the sampled hour, 7.5 slots were occupied on average; 90th percentile
ready-job queue wait was 11 minutes, dispatch delay 3 minutes, execution 4
minutes. CPU on running jobs averaged 42%; no evidence of per-job CPU saturation.
Other repositories have equally urgent workloads. The proposed split replaces
one task per PR with three shards, each needing its own setup. Pool capacity and dispatch
concurrency have not been independently verified. Figures are synthetic.
