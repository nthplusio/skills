# Synthetic pinned skills-repository evidence

This dossier is a fixture, not a claim about a live checkout. The provider is
GitHub Actions. The repository is public, and all three jobs use standard
GitHub-hosted Linux runners, not larger runners. Three jobs run in parallel:
`validate` (9 seconds), `plugins` (10 seconds), and `builder-agrees` (8 seconds).
`validate` is required by classic branch protection with strict up-to-date
enabled. The separate `builder-agrees` job depends on network access; its
failures must not be confused with the hermetic validator. No evidence of
redundant work, a capacity bottleneck, or a material maintenance burden is
provided.
