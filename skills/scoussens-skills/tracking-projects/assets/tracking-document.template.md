# <Project>: work done and remaining

<Editor> is the only editor of this page. Workers read the mirror before starting a piece and report changes to <Editor> by message instead of editing this page.

Workers read the mirror with:

```bash
git fetch --quiet origin <project>-status && git show origin/<project>-status:STATUS.md
```

Last updated: <YYYY-MM-DD>

![Overview](<overview URL; delete this line when the host cannot show a visual>)

## Where things stand

- **Outcome so far:** <What works now, in one sentence.>
- **Delivery head:** <branch> at [`<short sha>`](<commit URL>). <CI result, with a link to the run.>
- **Waiting on <Owner>:** <N decisions. The one holding up the most work is ….>
- **Mirror:** `STATUS.md` on branch `<project>-status`, committed only by <Editor>. It has no pull request and is never merged.

## Lanes

| Lane | Owner | Branch | State | Now |
| --- | --- | --- | --- | --- |
| 1, <purpose> | [<thread or person>](https://<link>) | <branch or —> | Working | <What it is doing, in a few words> |

## How open questions get answered

<Owner>'s rule, <YYYY-MM-DD>: answers come from these sources, in this order:

1. <First source, for example meeting recordings and transcripts>
2. <Second source, for example the design reference>
3. <Third source, for example the existing applications>
4. When necessary: <last source, for example the database, read only>

Each open question first goes to a research thread with its sources, which returns a recommendation. Only a question the sources cannot settle goes to <Owner>, under **Needs <Owner>**, with the sources checked and what it is holding up. <Editor> decides reversible, in-scope questions itself and records them as **Decided by me**, open to <Owner>'s veto.

## Remaining work

### Needs <Owner>

<Decision items: use decision-item.template.md. Open items first, the one holding up the most work at the top.>

### Decisions already approved

- [x] **<Short name>:** <What was approved, as the rule now reads.> *Holds:* <what it unblocked>.

### Answered by research (open to <Owner>'s veto)

- [x] **<Short name> (research, <YYYY-MM-DD>):** <The answer.> Sources: <citations>. ([research](https://<link>))
- [x] **<Short name> (decided by me, <YYYY-MM-DD>):** <The decision and why it is reversible.>

### Stopped

- **<What was stopped>:** <Why, and what replaced it.>

### Lane work

- [ ] **Lane <N>:** <The piece, its state and what it waits on.>

## Done

| Date | What | Where |
| --- | --- | --- |
| <YYYY-MM-DD> | <What landed, in one sentence.> Checks: <names and counts>. CI: <green or failed, with a link to the run> | [`<short sha>`](<commit URL>) |
