# The settings sheet

One table, one question, one answer. The user sees every choice the skill is
about to make, with the reason, and changes any of them in one reply. The
inference is the recommendation; the user's answer is the decision.

## Shape

Show the sheet before any output, as a Markdown table in the reply. One
lead-in line naming what you are about to produce may precede it, such as
*Before I write the explanation for your product manager, the settings:*

| Setting | Recommended | Why | Other choices |
| --- | --- | --- | --- |
| Reader | business stakeholder | the request names a product manager deciding on sprint scope | end user, developer who owns the code |
| Output | chat reply | one decision, read once, you will forward it | Markdown document, HTML page with comments |
| Interaction | still | nothing to step through or try | interactive, if you want to toggle the before and after |
| Length | about 400 words | the profile's budget | shorter, longer |
| Anchor | yes | the reader does not hold the concept | definitions only |

Then one question, in one line: *Reply **go** to use the recommendations, or
name a setting and the choice you want.* Nothing else follows in that reply.

Other choices list only what you could build; an option the harness cannot
deliver does not appear. The *Why* cell carries the evidence from the request
or the repository, so the user can see what the recommendation rests on.

## The answer

- *go*, *yes*, *ok*, or silence after an explicit grant to proceed: use every
  recommendation.
- A setting and a value: apply it, keep the rest, and say the changed settings
  in one line before building. Do not show the sheet again.
- A value that changes other settings, such as a reader whose profile has a
  different default output: apply the profile's defaults for the settings the
  user did not name, and say so in that one line.
- A question back: answer it, then ask the one question again.

## When the sheet is skipped

- The request fixes every setting, for example "a 200-word chat note for the
  on-call engineer, no analogies". Build with them.
- The user said not to ask, or granted autonomy for the task. Build with the
  recommendations.
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
most likely to change. Read whether the tool exists from the harness entry's
`ask_user` fact (`state.py resolve --harness '<harness>'`). Otherwise the
question goes in the reply.

## Calling this from another skill

A skill that produces an output with more than one reader or more than one
form does not ask its own way. It loads `explain-to`, runs step 1, and passes:

- what the artifact is, in one line, so the sheet's *Why* cells can cite it
- the settings it has already fixed, with the reason each is fixed
- any extra output it can produce beyond chat, Markdown, and HTML page, such
  as a PDF or an email, with who can see each
- any rule the caller must enforce, such as "a hosted page shows the
  repository's paths to everyone who can see it", which goes into the
  output row's *Why* cell

It takes the agreed settings back and builds. The calling skill owns the
content; `explain-to` owns the reader and the form.
