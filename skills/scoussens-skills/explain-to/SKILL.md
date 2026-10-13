---
name: explain-to
description: >-
  Fit an explanation of a concept, problem, or change to one named reader —
  choose the audience, the altitude, an anchor analogy with its twist, the
  output type, and whether the reader must operate it, then hand sentences to
  speak-clearly and the medium to the harness's page or view skill. Use when
  asked to explain something to a named audience ("explain this to the PM",
  "write it up for the data engineers", "make this understandable to a
  customer"), to teach a concept, to write an overview or walkthrough for
  someone outside the code, or when the user says the last explanation was too
  technical or too vague. Do not load it for a one-line factual answer, a
  commit message, or a change summary for the developer who made it; answer
  those directly instead.
metadata:
  needs: artifacts, skills.load, helpers.invoke
---

# Explain to

One explanation, for one reader, that they can act on after reading it once.
The reader is not you and not the developer who wrote the code. Every choice
below follows from who they are.

## Step 1 — Name the reader

Pick one profile from [references/audiences.md](references/audiences.md): end
user, business stakeholder, developer new to the code, developer who owns it,
data engineer, or operator. Infer it from the request: who is named, where the
output goes, and what they will do with it. Write the choice as the **reader
line**, one line in italics that follows the output, for example *Written for a
product manager deciding whether to ship this week*, so the user can correct
it in one word.

Ask only when two readings would produce materially different outputs, such
as a page a customer reads versus one an engineer debugs from. When the user
names two readers, write for the less technical one and add a short block for
the other at the end, rather than one text that serves neither. When the user
asks for separate texts, or names three or more readers, write one output per
reader, each with its own reader line and its own assumptions.

**Done when** one profile is chosen, its line is written, and you can say what
the reader already knows, what they decide, and which of your words are jargon
to them.

## Step 2 — Write the takeaway

One sentence the reader could repeat to a colleague an hour later, in the
profile's own vocabulary.

- For a change: what behaves differently, and what that costs or saves them.
- For a concept: what it is and why it exists.
- For a problem: who is hurt, how, and what decision is needed.

This sentence opens the output. Everything after it supports it, most
important first. A reader who decides gets the ask and the recommendation in
the first two lines.

**Done when** the takeaway is written, uses only the profile's vocabulary, and
names a consequence the reader cares about.

## Step 3 — Choose the altitude

Four altitudes, from the top:

| Altitude | What the reader sees | Nouns |
| --- | --- | --- |
| Outcome | What a person sees or gets | screens, reports, time, money |
| System | Which parts talk, and what crosses between them | services, tables, jobs, requests |
| Part | How one part works inside | steps, states, rules |
| Code | The text itself | functions, fields, queries |

Start at the profile's altitude and stay inside what the profile allows: a
profile that says *only* means only. Each picture and each paragraph stays on
one altitude, and the prose that explains a picture shares the picture's
altitude. Below that, drop one altitude for the single mechanism the reader
needs in order to trust the takeaway, in one sentence or in the short code
excerpt a profile allows, then come back up. Drop further only when the reader
asks.

**Done when** you can name the altitude of every picture and paragraph, and no
picture mixes two.

## Step 4 — Anchor, then twist

When the profile says anchors help, connect each new concept to something the
reader already handles in their own work, the **anchor**, then state the one
way the software differs, the **twist**. The twist is not optional: an anchor
alone teaches the wrong model.

> For an end user: a seam is like the socket between a lamp and the wall. The
> twist: in code we build the socket on purpose, so that a test can plug in a
> fake lamp.

Take the anchor from the profile's anchor domain, not from this example. One
anchor per concept the reader must hold to follow the takeaway; a sub-term
gets a one-line definition instead of its own anchor. Carry the anchor
through: when the concept returns, reuse the anchor's words rather than
introducing a second comparison. Readers who already own the vocabulary get a
one-line definition instead, because for them the anchor is noise.
Speak-clearly removes idioms; an anchor is not an idiom, because the text
states and explains the comparison.

**Done when** every concept new to the reader has an anchor with a twist, or a
one-line definition in the reader's words.

## Step 5 — Choose the output

Read [references/formats.md](references/formats.md) and choose one of chat
reply, Markdown document, or HTML page, by lifetime, by who else reads it, and
by whether a picture carries the argument.

A still output is the default, and its text diagrams are yours to draw under
visuals.md. Make it interactive only when the reader must do something a still
picture cannot let them do: step through an ordered sequence, choose a path
and see its consequence, or predict and then check. When interaction earns its
cost, hand off to the harness skill that formats.md names, with a
one-paragraph spec: the reader's action, the first state shown, what each
interaction reveals, and the one thing that must stand out.

**Done when** one output type is chosen, and an interactive output has its
spec and its hand-off named.

## Step 6 — Build within the load budget

Follow [references/visuals.md](references/visuals.md) for every picture. The
rules that bind every output:

- One picture makes one point, and its caption states that point in one
  sentence. A picture without a caption, or a caption that says what the
  picture is rather than what it shows, is unfinished.
- Seven or fewer boxes per picture, twelve at the limit. Past that, split by
  altitude rather than shrink the boxes.
- Label on the thing. A legend makes the reader look away and back.
- Every claim that matters gets a picture or a concrete example, never only an
  adjective.
- The takeaway recurs in different words, in at least three of these four
  places: the lead, a caption, the worked example, and the close.
- Load `speak-clearly` if it is in your available skills and apply it to every
  sentence. Address the reader as *you* even when the user will forward the
  text. Describe a change that has not shipped by its condition, *from the
  next release, the grid shows your level names*, which keeps the timeless
  rule. Define each term outside the profile's vocabulary at first use, or
  replace it.
- Stay within the profile's reading budget. It counts prose outside pictures,
  tables, and code blocks; the reader line and the assumption lines sit
  outside it, and *about* allows a fifth over. Cut detail, never the takeaway
  or a stated risk.

**Done when** each picture has a caption and at most twelve boxes, the prose
is within the profile's budget, and the takeaway appears in at least three of
the four places.

## Step 7 — Check against the reader

- **First question.** Each profile lists the question that reader asks first.
  The output answers it on the first screen.
- **Stranger test.** A reader with no access to this thread or the code can
  follow every sentence. Names coined in the thread do not appear; an
  invented name used as an example is fine when the text says it is one.
- **Jargon count.** List every term outside the profile's vocabulary. Each one
  is defined where it first appears, or gone.
- **Grounding.** Every fact traces to something you read or ran. Anything else
  is labelled as an assumption, in the text, where the reader meets it. When
  the profile requires a fact the source does not give, such as a contact, a
  date, or the effort, say so in the text and name who can supply it.

Reply with the output, then the reader line from step 1, then up to three
assumption lines, as bullets or sentences. With several readers, each output
gets its own reader line and assumptions.

## When not to apply

- A factual one-liner or a quick status answer.
- A commit message or a pull request description for the author's own team.
- A change explained to the developer who made it. Answer at the Code or Part
  altitude directly.
