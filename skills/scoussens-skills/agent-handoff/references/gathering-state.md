# Gathering the state, and turning it into a preflight

One sweep, two uses. The facts you gather here become Context; the commands you
gathered them with become the preflight. So record the pair — the command and
the answer it gave you — rather than the answer alone. A fact with no command
behind it cannot be rechecked, and a command with no recorded answer asks the
receiver to compare a result against nothing.

## The sweep

### Position

```bash
git status --porcelain --branch      # branch, upstream divergence, dirty files
git rev-parse --short HEAD
git stash list
git worktree list
git log --oneline -5
```

Divergence from upstream matters more than it looks: local commits nobody has
pushed are work that exists in exactly one place, and a receiver in a different
checkout cannot see them at all. Say so explicitly when the count is non-zero.

Staged and unstaged changes are different states, and `--porcelain` shows both
in one pass. Anything half-applied — a partial patch, a popped stash with
conflicts, a rebase in progress — belongs in Context in full.

### Work in flight

```bash
gh pr view --json number,state,isDraft,mergeStateStatus,reviewDecision
gh pr checks
```

`mergeStateStatus` catches the conflict that appeared while you were working;
`reviewDecision` distinguishes *waiting on a human* from *waiting on you*, which
is the internal-versus-external distinction the action table depends on.

A red check is only useful with its reason attached. *Three tests failing, all
in the fixture that needs regenerating* is a Context fact; *CI is red* is not.

### Environment

What must the receiver do before anything runs? Fresh checkouts and worktrees
routinely need an install, a generated client, or an environment file that is
not in the repository. Generated artifacts are the quiet one: they are usually
ignored by git, so they never appear in `git status`, and a stale one produces
a failure that looks like the receiver's own change broke something.

Name any long-running process the work assumes — a dev server, a database
container, a tunnel — and how to start it.

### Tracker

Status, assignee, and blocked-by links. The assignee is how a receiver claims
work; the blocked-by links are external blockers already recorded by somebody
else, and lifting them into the action table is cheaper than rediscovering them.

### Deployed state

Merged and live are different, and any row that verifies against production
depends on which one you meant. Check what is actually deployed rather than
inferring it from the log.

## What decays, and how fast

Preflight the facts whose staleness would invalidate an action. Not all of them
— a preflight that checks everything is one nobody reads.

| Fact | Goes stale when | Preflight it when |
| --- | --- | --- |
| `HEAD` and branch tip | anyone pushes to the branch | An action cites line numbers, or assumes a particular diff |
| Uncommitted changes | the session ends, a stash is popped, an editor saves | Any action builds on work that is not committed |
| Check status | a re-run, a dependency update, a merge into the base | An action assumes a green baseline |
| Issue status and assignee | anyone touches the tracker | The receiver is meant to claim the work |
| Deployed revision | any merge that triggers a release | An action verifies against production |
| Generated artifacts | a schema or codegen input changes anywhere | The receiver will build or typecheck |

## Writing a check that is worth running

Three properties, and a check missing any of them is noise:

- **It states the result you observed.** `git rev-parse --short HEAD` →
  `a4f19c2`, not `git rev-parse --short HEAD`.
- **It says what a disagreement means.** A moved `HEAD` might be a colleague's
  unrelated commit or might be the rebase that renumbered every line the table
  cites. You know which; the receiver does not.
- **It is fast.** A preflight runs before any work, so it earns nothing by being
  thorough. A full test suite is not a preflight — it is `A1`.
