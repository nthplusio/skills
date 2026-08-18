---
name: speak-clearly
description: Write human-facing prose in Google developer style — named actors, condition-first sentences, timeless tense, no filler. Use when drafting docs, READMEs, comments, commit messages, PR descriptions, error messages, or UI copy; when editing existing prose; or when asked to make writing clearer, tighten wording, or fix tone.
---

# Speak clearly

Rules for prose a human reads. Apply them to what you write, in the moment you
write it. Derived from the
[Google developer documentation style guide](https://developers.google.com/style).

## Name the actor

Say who or what performs the action. A sentence with no actor leaves the reader
guessing whether it is them, the server, or the library.

- Write: `The server sends an acknowledgment.`
- Not: `An acknowledgment is sent.`

Passive earns its place when the actor is genuinely irrelevant or the object is
the point: `The file is saved.` `The database was purged in January.` It also
softens blame worth softening: `Over 50 conflicts were found` beats `You created
over 50 conflicts`.

## Address the reader as "you"

- Write: `This document shows you how to deploy an app.`
- Not: `This document shows the user how to deploy their app.`
- Not: `Let's add a description to our table.`

Reserve *we* for the organization speaking: `We don't support C.` The imperative
already implies *you* — `Click Submit`, not `You should click Submit`.

## Lead with the condition

Put the circumstance, condition, or goal before the instruction, so a reader it
does not apply to can skip the rest of the sentence.

- Write: `To delete the document, click Delete.`
- Not: `Click Delete if you want to delete the document.`
- Write: `For more information, see the migration guide.`
- Not: `See the migration guide for more information.`

## Write timeless

Cut words that pin the text to the moment it was written: *currently*, *now*,
*new*, *soon*, *latest*, *existing*, *as of this writing*. Use present tense
rather than *will*.

- Write: `The emulator supports these filters.`
- Not: `The emulator now supports these filters.`

A version or date is fine when it is the actual fact: `Supported since v2.4.`
Release notes, changelogs, and blog posts are exempt — their whole job is to be
time-bound.

## Cut the filler

Delete words that claim ease, add ceremony, or pad: *simply*, *just*, *easy*,
*quickly*, *please*, *powerful*, *seamless*, *robust*, *blazing*, *note that*,
*it's important to note that*.

- Write: `To view the document, click View.`
- Not: `To simply view the document, please click View.`

Calling a task easy tells a reader who is stuck that they are the problem. State
the steps and let the difficulty go unclaimed.

Full substitution table, including inclusive-language swaps:
[references/word-swaps.md](references/word-swaps.md).

## Say where the link goes

Link text should carry meaning read on its own, with the important words first,
matching the title of the thing it points at.

- Write: `For more information, see [Using OAuth 2.0 to access Google APIs].`
- Not: `Click [here].` / `See [this document].` / `[http://example.com]`

## Write for translation

Short sentences, one idea each.

- Plain words: *use* not *utilize*, *start* not *commence*, *through* not *via*,
  *to* not *in order to*, *some* not *a number of*.
- Keep the helper words that mark structure — *that*, *then*, *of*, and the
  repeated *if*:
  - Write: `If the key is missing, then the default is returned.`
  - Not: `If the key is missing, the default is returned.`
- Put each modifier next to what it modifies:
  - Write: `Request no more than one token.`
  - Not: `Only request one token.`
- Idioms, sports, seasons, holidays, and jokes do not survive translation:
  *ballpark figure*, *back burner*, *out of the box*, *home run*.

## Keep the tone level

Sound like a knowledgeable colleague.

| Too informal | Level | Too formal |
| --- | --- | --- |
| Dude! This API is totally awesome! | This API lets you collect data about what your users like. | The API documented by this page may enable the acquisition of information pertaining to user preferences. |

One exclamation mark per document is usually one too many.

## When not to apply

- **Quoted material, error strings matched by tests, and the user's own words.**
  Leave them exactly as they are.
- **Release notes, changelogs, blog posts.** Time-bound language is correct there.
- **Prose you were not asked to touch.** Rewrite what you write; mention the rest
  rather than silently editing it.

## Done when

Every sentence you wrote or edited:

- names its actor, or is passive for one of the reasons above
- states its condition before its instruction
- carries no time anchor and no future tense
- contains no word from the swap table
- stands alone if it is link text
