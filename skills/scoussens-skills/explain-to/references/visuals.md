# Drawing rules

Rules for every picture, whether a text diagram block, an HTML figure, or a
chart. Each rule names the research it rests on, so that a rule can be
revisited when the evidence changes.

## One picture, one point

Write the point as one sentence before drawing. It becomes the caption. Draw
only what that sentence needs. A picture that makes two points becomes two
pictures.

*Dual coding (Paivio): a picture and the words for it are stored through
separate channels, and recall improves when both are present and agree.*

## Count the boxes

Seven or fewer boxes per picture, twelve at the limit. A before-and-after
pair counts as two pictures, so the limit applies to each pane. When a
picture needs more, split by altitude: one picture at System, one at Part
for the region that matters. Never shrink the boxes to fit.

*Cognitive load (Sweller): working memory holds a handful of items; every
extra box is paid for by attention taken from the point.*

## Label on the thing

Write the name on or beside each box and each arrow. Put what crosses an
arrow on the arrow; a label longer than the arrow goes on the line beneath
it. A legend forces the eye to leave the picture and return.

## Fit the column

A text diagram stays under 72 columns, so that it does not wrap in a chat
reply or a Markdown viewer. When a row of boxes would be wider, stack the
boxes vertically, shorten the labels, or split the picture by altitude.

## Group by closeness, join with straight lines

Put parts that belong together next to each other, and leave space between
groups. The eye reads closeness as belonging, so no border or colour is
needed. Run lines horizontally and vertically, with square corners. The eye
follows a straight line faster than a diagonal and loses a crossing less
often.

*Gestalt principles of proximity and continuity.*

## Colour means one thing

Everything is neutral except the one decisive path, state, or change. In a
text diagram, light lines are the unchanged structure and heavy lines are
the accent. When a colour or weight does not mark a state, a group, or the
point, leave it out.

## Before and after share a layout

To show a change, draw the before and the after with the same boxes in the
same places, so that only the difference moves. Draw both whenever the before
had a shape of its own, such as one job that becomes two. Draw the after
alone only when the before is its absence, and say so in the caption.

## One altitude per picture

A picture at System shows parts and what crosses between them. A picture at
Part shows steps or states inside one part. Mixing them in one picture makes
the reader change scale mid-glance.

*The C4 model's context, container, and component levels apply the same
idea to architecture.*

## Draw a schema

A schema picture shows tables, the columns that matter, and the joins
between them. It is the picture a data engineer reads first, so the rules
above apply with these additions:

- **One card per table or view.** The card's title is the object's full
  name. Under it, one line per column that the explanation needs: keys, the
  join column, and the columns that change. Leave out the rest and say
  "…" once. Mark a key with `PK` and a reference with `FK`.
- **The join sits on the connector.** Label each line between cards with the
  column that joins them. The direction runs from the table that holds the
  reference to the table it points at.
- **Consumers hang off the object they read.** A view, a report, or a job
  that reads an object sits beside it, joined by a connector labelled
  *reads* that runs from the object to its reader. The two arrow kinds point
  opposite ways on purpose: a join arrow points at what is referenced, a
  reads arrow points at who reads. That makes "who is affected" visible
  without a list, and a schema picture with its consumers is also the
  lineage picture; no separate lineage drawing is needed.
- **Before and after share the layout.** The same cards in the same places.
  Accent only the key that changed, the object that is new, and the
  connector that moved. A removed object stays in place, drawn light, and
  labelled with when it goes away.
- **In a text diagram**, stack cards vertically when the row would pass 72
  columns; put the after picture under the before picture, never beside it.
- **On an HTML page**, draw each card as a box with a title row and one row
  per column, put the before pane and the after pane side by side at full
  width, and stack them on a narrow screen. Draw connectors as straight
  lines with square corners and the join column written on them. Keep every
  colour neutral except the accent on what changed.

Example in text form, after only, for a placement table that gains a key:

> Placements now point at a level by `LEVEL_ID`; `ORDINAL` stays for ordering.

```diagram
┌────────────────────────┐          ┏━━━━━━━━━━━━━━━━━━━━━━━┓
│ DIM.ACCOUNT_HIERARCHY  │ LEVEL_ID ┃ LEVEL.HIERARCHY_LEVEL ┃
│ NODE_ID        PK      │ ━━━━━━━━▶┃ LEVEL_ID        PK    ┃
│ HIERARCHY_ID   FK      │          ┃ HIERARCHY_ID    FK    ┃
│ ORDINAL                │          ┃ ORDINAL               ┃
│ LEVEL_ID  new  FK      │          ┃ NAME, DISPLAY_NAME    ┃
└────────────────────────┘          ┗━━━━━━━━━━━┳━━━━━━━━━━━┛
                                                ┃ reads
                                                ▼
                                    ┌───────────────────────┐
                                    │ DIM.V_ACCOUNT_MAP     │
                                    └───────────────────────┘
```

## Repeat the point, not the picture

The takeaway appears in the lead sentence, in a caption, in the worked
example, and in the close, each time in different words. The reader meets
the idea four times in four contexts without reading the same sentence
twice.

*Spaced and varied repetition moves an idea from short-term to long-term
memory. The often-cited "10-7 rule" has no primary source; the repetition
itself is the defensible part.*

## Example

A text diagram that follows the rules. Caption first, five boxes, labels on
the arrows, the changed path heavy:

> After this change, the request returns before the card is charged.

```diagram
┌─────────┐  enqueue()  ┏━━━━━━━━┓  charge()  ┌────────┐
│ Handler │ ───────────▶┃ Worker ┃ ──────────▶│ Stripe │
└────┬────┘             ┗━━━━━━━━┛            └────────┘
     │ 200 OK in 20 ms
     ▼
┌─────────┐
│ Caller  │
└─────────┘
```

## Sources

- Sweller, J. Cognitive load theory. Summarised for technical writers in
  https://online.stanford.edu/10-tips-communicating-technical-ideas-non-technical-people
- Paivio, A. Dual coding theory.
- Gestalt grouping, applied to data and diagrams:
  https://www.goldensoftware.com/communicate-complex-data/
- Minto, B. The pyramid principle, summarised in
  https://www.theanalystacademy.com/communicating-complex-ideas-clearly/
- Brown, S. The C4 model for visualising software architecture.
  https://c4model.com
