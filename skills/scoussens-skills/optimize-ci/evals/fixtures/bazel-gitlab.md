# Synthetic Bazel and GitLab evidence

Bazel tests declare inputs and dependencies; remote cache accepts writes from
trusted main jobs and reads from branch jobs. The proposal also sets an ad hoc
`TESTS_ALREADY_PASSED=1` flag to skip test execution. Keep a cold/uncached test
path for validation; external-state tests are not eligible for result reuse.

GitLab fixture is a merge-request project. Push and merge-request pipeline
creation can both occur for one branch push unless workflow rules prevent the
duplicate. `rules:changes` on a branch push compares the previous commit; for
merge requests it compares the target branch. Merged-results pipelines test a
temporary source-plus-target revision. Job `needs:project` fetches the latest
successful artifact at a ref and does not wait for an in-flight current
pipeline; it is not automatically the artifact from this pipeline.
