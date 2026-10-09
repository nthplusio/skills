# Synthetic evidence: consumption

Fictional private GitHub repository. One month: PR class 100 attempts at 8 raw
runner minutes each; push-to-main class 24 attempts at 8 raw minutes each.
Strict up-to-date rules cause open PR reruns after main moves. Billing rounds
each job upward to a whole minute; these raw durations do not state account
charges or a price. The proposed two-shard trial has two jobs of 5 minutes
each, including duplicated setup. The current job takes 8 minutes. These are
synthetic comparable observations, not a prediction that all sharding doubles work.

Main push consumers: Railway deploy gate waits for its check suite, and the
`migrate` job has `needs: verify`.
