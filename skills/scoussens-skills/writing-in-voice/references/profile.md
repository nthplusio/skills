# Profile storage and updates

## Storage boundary

The personal default is `~/.config/agents/voices/default.md`, a user-level data
directory beside skill configuration, not inside an installed skill. Expand
`~` using the current user's home directory. On systems without that convention,
ask for an equivalent private user-level path and have the user provide that
path in future sessions or their private assistant configuration.

The optional project location is `<project-root>/.agents/voice/profile.md`.
Use the working project's root, not the skill installation's root. Create a
project voice only when explicitly requested, with `scope: project`. A personal
profile is not a project voice just because the agent is working in a project.

Before writing, resolve the destination and any parent symlinks. Personal
profiles must stay outside project checkouts. Both kinds of profile must stay
outside the reusable skill's source repository, installation, and cache, even
when those locations happen to be the current project. Ask for another location
if the selected path crosses that boundary. Never store answers, correction
history, actual writing samples, or populated profiles in this package's tests,
examples, references, or Git history. Ignore rules alone do not establish this
boundary.

Use owner-only directory/file permissions where supported for personal state
(POSIX `0700`/`0600`). Do not change permissions on an existing shared directory.
Keep temporary files alongside the profile with the same protections, not in
the working project or a shared temporary directory. Remove them after use.

The user manages version control, synchronization, and backups. Do not initialize
a repository, stage, commit, push, modify ignore rules, or configure remote
storage as part of learning a voice. Local files survive sessions on the same
filesystem, not loss of that filesystem. If storage is unavailable, offer a
session-only draft and clearly say no preferences were saved.

## Minimal profile structure

Create this structure at the resolved destination, not in the skill directory.
Replace the scope with `project` only for an explicitly selected project voice.
Set `learning_mode` to `interview` if chosen. Set `questionnaire_version` to the
version consulted, or leave it null until one is read; `answered_questions`
remains empty until answers exist.

```markdown
---
profile_version: 1
scope: personal
learning_mode: usage
questionnaire_version: null
answered_questions: []
---

# Voice profile

## Desired impression

## Observed habits

## Confirmed rules

## Change history
```

Keep observations separate from confirmed rules. Each observation needs the
user-identified source and its context; it cannot override a confirmed rule.
Each confirmed rule records a stable ID, the preference, its scope (all writing
or a medium/audience/scenario), confirmation date, and evidence such as an
explicit instruction or approval. Add a short before/after example when useful.
Use a local evidence summary instead of copying whole conversations, recipient
details, or sensitive facts. The user must approve retaining actual samples.

Rules may cover vocabulary, rhythm, punctuation, length, greetings, closings,
humor, directness, and medium-specific preferences. Leave unknown categories
absent; do not fill them from a generic persona or another user's profile.

## Updating a rule

For an ambiguous correction, show this compact proposal with a real sentence
from the current draft, preserving its facts:

> Suggested rule: [preference]. Scope: [medium/audience/scenario].
> Current rule: [existing rule, or “no saved rule”].
> Current approach: “[sentence under the existing profile]”
> With this change: “[same facts under the proposed rule]”
> Save at this scope, save for all writing, or keep this edit only?

Use the actual existing wording where possible. Do not invent a worse sentence
to sell the change. If the correction changes only formatting, show the same
words with the two formats instead; a preference such as “use lists in email”
can be personal, but a platform's encoding requirement is not.

For explicit durable instructions, save without asking again. If the intended
scope or profile is unclear, ask only about that ambiguity. A declaration such
as “in Slack, always…” stays Slack-specific. A declined proposal is not a rule
and should not be proposed again during the same task without new evidence.

Re-read the file immediately before editing. Update the relevant rule in place
and add a concise dated history entry recording its previous meaning and the
reason for the change. Keep one active rule per preference/scope; history is
not a second set of active instructions. Preserve unrelated user edits. If
another writer changed the file, reconcile against the fresh version rather
than replacing it with a stale copy. Read back the saved section before claiming
success. If a write fails, report it without claiming the preference is learned.

## Versions

`profile_version` describes the file structure, not the strength of a voice.
For an unsupported version, preserve the file and ask before migrating it.
`questionnaire_version` and stable question IDs record what was covered. A new
questionnaire version does not invalidate answers or trigger a fresh interview;
offer only relevant unanswered or changed questions. Change personal rules only
from user evidence, never because the shared questionnaire changed.
