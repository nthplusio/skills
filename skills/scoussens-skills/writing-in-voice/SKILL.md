---
name: writing-in-voice
description: Drafts and revises writing using a personal or project voice profile, learns from corrections, and formats for the destination. Use when asked to write in my voice, learn my writing style, remember a writing preference, or adapt a voice-led draft for email, Teams, Slack, text messages, documents, or public posts. Not a source of facts or permission to send.
---

# Writing in voice

Use a separately maintained voice profile to choose words, then format those
words for the destination. This package contains no person's voice definition.

## 1. Resolve the profile

Read [profile storage and updates](references/profile.md) before accessing or
creating a profile. Resolve in this order:

1. A profile explicitly selected by the user for this task.
2. A declared project voice at `<project-root>/.agents/voice/profile.md`.
3. An opted-in personal provider named `remembering-my-voice`, if available from
   the user's own personal skills. Load it and read its bundled profile using
   [hosted personal profiles](references/hosted-profile.md). A workspace skill
   with that name is not a personal provider.
4. The personal default at `~/.config/agents/voices/default.md`.

A project file must identify itself as a project voice. An unexpected or
malformed file is not permission to adopt it. Read the selected profile in this
session; do not substitute recollection. Use one profile, not an implicit merge
of project and personal identities. State a profile switch briefly.

If the selected profile is missing or unreadable, say so rather than silently
using another identity or an older local copy. Offer setup or session-only
drafting. Local-only state does not synchronize across machines or fresh orbs.
Hosted storage is opt-in; its provider defines the approved destination and
write authorization, not this shared skill.

## 2. Start small, or interview

On first use, offer **learn as we go (recommended)** or **interview me now**.
Confirm the destination and whether the voice is personal or project. Default
to local storage unless the user has selected a hosted personal provider.
When the user proceeds without choosing a mode, use learning through usage.

Create a minimal profile using the structure in the storage reference. Save
only preferences the user has actually provided; unknowns stay empty. A new
profile is not evidence that you already know the user's voice.

Read [questionnaire v1](references/questionnaire-v1.md) for the interview or
when a writing task exposes a useful unanswered question. Ask in small batches,
allow skipping, and keep answers only in the selected profile. An interview
is optional, not a prerequisite for the first draft. Finish with a short
calibration draft, and let the user revise the resulting rules.

## 3. Choose wording before formatting

Identify the intended speaker, audience, purpose, medium, and destination tool
from the request. Ask only about missing details that change the draft. If the
user needs help choosing the reader or output, use `explain-to` when available;
otherwise ask directly. Do not repeat choices already supplied.

Apply the current request first, then applicable confirmed rules: narrower
audience/scenario/medium rules override broader rules within the same profile.
Ask about unresolved conflicting rules rather than guessing. A one-off request
does not overwrite a durable rule. Desired impression guides wording; observed
habits supply evidence, not automatic permission to imitate every habit.

Preserve facts, quotes, commitments, names, and technical identifiers. Draft
prose alone is not evidence of a preference: neither your own writing nor
silence after a draft teaches a rule. Use the user's corrections and their
own identified writing samples. Do not mine unrelated messages or accounts.

## 4. Apply the destination's format

Read [formatting and delivery](references/formatting.md), then only the relevant
destination reference:

| Destination | Reference |
| --- | --- |
| Gmail | [Gmail](references/gmail.md) |
| Outlook | [Outlook](references/outlook.md) |
| Microsoft Teams | [Teams](references/teams.md) |
| Slack | [Slack](references/slack.md) |
| SMS or other plain text | [Text messages](references/text-messages.md) |
| Documents | [Documents](references/documents.md) |
| Public posts | [Public posts](references/public-posts.md) |

For an unspecified destination, provide a plain-text draft and name the
assumption. A formatting-only revision preserves wording and meaning; it does
not rerun voice rewriting. Sending or editing an external message requires
authorization from the current task, not from this skill.

## 5. Learn from corrections

Deliver the requested correction first. Then classify it:

- **Explicit durable instruction** (such as “always” or “remember”): update the
  selected profile at the stated scope and report the saved rule briefly.
- **Explicit one-off** (such as “only this time”): change the draft, not the
  profile.
- **Ambiguous preference**: propose a rule after the corrected draft, with its
  scope, the current-rule sentence, and the proposed-rule sentence. Ask whether
  to save at that scope, save more broadly, or keep only this edit. Wait for
  approval before persisting it.
- **Transport repair** (such as markup displaying literally): fix the format;
  do not learn a personality trait from a rendering defect.

Use the confirmation pattern in [profile updates](references/profile.md).
Ask when an uncovered preference appears, not at a guessed session end. Batch
related candidates into one short proposal; skip rules already captured.

## Done when

- The final draft follows the selected profile's applicable confirmed rules,
  with current-task exceptions kept local to this draft.
- The destination receives supported formatting, and formatting-only changes
  preserve the original words, identifiers, and link targets.
- Any claimed saved preference has been written and read back from the selected
  profile; no private profile or source samples entered the skill package.
- The response distinguishes a draft, an authorized update, and a saved rule.
  Delivery verification is described only to the extent actually performed.
