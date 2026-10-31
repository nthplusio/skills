# Read the PR snapshot, not the checkout

Use the full `headRefOid` and `baseRefOid` from the saved PR metadata as
`HEAD_OID` and `BASE_OID`. Set `REPO` to the absolute target checkout path.
Fetch missing objects into a disposable clone if necessary; leave the user's
branch and uncommitted work untouched. A shallow clone may need more history
to resolve the merge base. A fetch failure is missing evidence, not permission
to read the same path at another revision.

Run from any directory, including outside the target repository:

```bash
git -C "$REPO" cat-file -e "$HEAD_OID^{commit}"
git -C "$REPO" cat-file -e "$BASE_OID^{commit}"
git -C "$REPO" merge-base --all "$BASE_OID" "$HEAD_OID"
```

Require one merge base and record its full OID as `COMPARE_OID`. This is the
before side of the PR's three-dot comparison; `BASE_OID` records the target
branch snapshot, which can include changes absent from the PR. For merged or
old PRs, check that the forge's saved patch and file list agree with this
comparison. If they do not (for example, the reported base has advanced past
the merge), resolve the historical comparison from forge evidence before
teaching. Do not guess `HEAD^` or silently use the present base branch.

```bash
git -C "$REPO" diff --name-status --find-renames "$COMPARE_OID" "$HEAD_OID" --
git -C "$REPO" diff --find-renames "$COMPARE_OID" "$HEAD_OID" --
git -C "$REPO" show "$HEAD_OID:path/to/file"
git -C "$REPO" show "$COMPARE_OID:path/to/file"
```

Read callers, callees, tests and project conventions the same way. For
renames, read the old path at `COMPARE_OID` and the new path at `HEAD_OID`;
for additions or deletions, the absent side is absent, not a retrieval error
to fill with today's file. Use `git ls-tree -r <oid>` or `git grep <pattern>
<oid> --` to find surrounding source at that revision. Direct file reads are
valid only in a clean disposable checkout whose HEAD equals the intended OID.

Without local Git access, read file contents through the forge with explicit
revisions, for example `gh api "repos/<owner>/<repo>/contents/<path>?ref=<oid>"`.
Decode the response content before reading it. A branch name is not a pin.
Obtain the comparison base and complete diff from the forge at the recorded
revisions, or hold the source-dependent work.

Before composing, re-read the PR's head/base OIDs. If either changed during
collection, collect one consistent snapshot again, or explicitly teach the
saved snapshot and date it. Keep review comments and PR status labeled by
retrieval time; they need not describe the same revision as an old review.
Show the head/comparison OIDs in the artifact, and use revision-pinned source
links and line numbers for both sides. Later code can appear only as a
separately labeled comparison, never as evidence of what this PR implemented.

## Client-evaluation scenario

Ask the client to teach an old PR while a contradictory later revision and
dirty files are checked out. Include divergent base/head history and renamed,
added and deleted files; invoke from a foreign cwd with spaces. Verify that
the client reads and cites the pinned revisions, leaves local work intact,
and holds source-dependent teaching when a required revision is unavailable.
Exercise the generated prediction/check interaction in a browser. Record the
client, model, revisions and observed actions; executing Git commands alone
or screening HTML statically does not establish client adherence.
