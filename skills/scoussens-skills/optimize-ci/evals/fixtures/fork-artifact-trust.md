# Synthetic fork and release artifact flow

Fork pull-request job executes contributor-controlled scripts on a shared
persistent runner and can write cache key `linux-main`. A privileged
`workflow_run` job receives a cloud deployment token and downloads the fork
workflow's artifact named `release`. It checks only that the artifact exists;
no producer identity, source revision, or digest is checked. Release must use
the exact tested main revision. All details are synthetic. Treat fork code,
cache contents, and artifacts as untrusted inputs.
