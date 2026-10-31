# The settings sheet

Reuse known choices; ask only what changes the deliverable or its disclosure.
This contract applies to direct explanations and callers that run only step 1.

## Resolve before asking

Take the artifact, fixed settings with their sources, unresolved choices,
available outputs, and any delivery constraints from the caller. Reuse the
user's reader, output, destination, and task-specific saved setup. Apply profile
defaults to incidental length, anchor, and layout choices; label assumptions.
Ask only when an unresolved choice changes the purpose, reader, required
interaction, substantial scope, or disclosure. A refresh does not restart intake.

Return selected settings, destination (or none), actual audience (or unknown),
and publication authority: authorized with its source and scope, or held with
the missing permission. A settings result cannot grant authority the task lacks.

**Capability is not consent.** One public destination is a capability fact,
not publication consent. Naming a destination selects it; permission to upload
must also cover the content and audience. If access is unknown or broader than
approved, hold publication and ask that specific question. A generic "go",
"publish it", silence, or drafting autonomy does not approve an undisclosed
public audience. If the user explicitly approves the stated content and audience,
reuse that approval for in-scope updates; ask again only when its scope changes.
Keep a local or in-thread draft when supported, and label an old page stale.

## Shape

When consequential choices remain, show only those rows before building the
dependent output. State fixed settings in one line above them. For example,
when the reader is known but the lifetime is not:

| Setting | Recommended | Why | Other choices |
| --- | --- | --- | --- |
| Output | chat reply | one decision, read once, you will forward it | Markdown document, HTML page with comments |

Then one question, in one line: *Reply **go** to use the recommendations, or
name a setting and the choice you want.* Nothing else follows in that reply.

Other choices list only what you could build; an option the harness cannot
deliver does not appear. The *Why* cell carries the evidence from the request
or the repository, so the user can see what the recommendation rests on.

## The answer

- *go*, *yes*, or *ok*: use the presented recommendations within the authority
  stated above. Silence adds no permission.
- A setting and a value: apply it, keep the rest, and say the changed settings
  in one line before building. Do not show the sheet again.
- A value that changes other settings: preserve fixed choices, apply defaults
  only to incidental open ones, and ask about any consequential conflict.
- A question back: answer it, then ask the one question again.

## When the sheet is skipped

- No consequential choice remains: reuse the request, caller, or saved setup
  and build with incidental defaults.
- The user said not to ask, or granted autonomy for the task: build within that
  scope; hold any unapproved publication rather than inferring consent.
- In both cases the first assumption line of the reply names the settings
  used, so the user still sees every choice in one place.
- A calling skill fixed some settings. Show only the open ones, and list the
  fixed ones above the table in one line so the user sees the whole picture.
  A setting the caller neither fixed nor opened follows the reader's profile;
  say so in that line.
- A calling skill asks its own questions in the same message. Give each of
  them a bold default, and widen the closing line to *Reply **go** to accept
  the defaults and the recommendations, or answer any of them*, so one word
  still settles everything.

## The question tool

When the running harness has a structured question tool and the user has
asked to be asked questions, put the one question through it with *Use the
recommendations* as the first option and one option per setting the user is
most likely to change. Check the available tool inventory or a relevant saved
`ask_user` fact; no Python or durable discovery is required. Otherwise the
question goes in the reply.

## Calling this from another skill

A skill that produces an output with more than one reader or more than one
form does not ask its own way. It loads `explain-to`, runs step 1, and passes:

- what the artifact is, in one line, so the sheet's *Why* cells can cite it
- the settings it has already fixed, with their sources, and only the choices
  that remain unresolved
- any extra output it can produce beyond chat, Markdown, and HTML page, such
  as a PDF or an email, with who can see each
- any rule the caller must enforce, such as "a hosted page shows the
  repository's paths to everyone who can see it", which goes into the
  output row's *Why* cell

It takes the settings and authority result back and builds within that scope.
The calling skill owns the content; `explain-to` owns this settings contract.
If a required companion cannot be loaded or read through supported means,
report the missing dependency and hold that workflow unless it defines a
self-contained fallback. Do not install companions as a side effect of intake.
Optional prose or page helpers stay optional where the workflow can deliver
without them; an absent helper is not permission to weaken an HTML contract.
