# Output types and hand-offs

Three output types. Choose by lifetime, by who else reads it, and by whether
a picture carries the argument.

| Output | Choose when | Lifetime | Pictures | Interaction |
| --- | --- | --- | --- | --- |
| Chat reply | The user is the reader, or will forward it; one decision; read once | This turn | Text diagram blocks, small tables | None, unless the harness renders an inline view and step 5 found interaction earns its cost |
| Markdown document | Read again from the repository: onboarding, a runbook, a schema-change record, a decision record; must make sense without the thread | Until superseded | Text diagram blocks and tables; images only where the repository already stores them | None |
| HTML page | Readers outside the thread must review and comment; a before-and-after picture, motion, or something to operate carries the argument; referenced over days by a stable link | Stable link, revised in place | Rich pictures, animation | When step 5 found it earns its cost |

Length is not a reason to leave the chat. A reader who is also the user gets a
chat reply however long, unless one of the rows above holds. When both the
chat row and the Markdown row fit, as with an onboarding explanation, write
the chat reply and offer to file it; write the document only when the user
asks for one, names a place for it, or says others will read it later.

## When interaction earns its cost

A still picture serves most explanations. Make the output interactive only
when the reader must:

- step through an ordered sequence of more than about five steps where the
  order is the point
- choose a path and see its consequence, such as a what-if over a rule
- predict an answer and then check it, which is how teaching sticks
- expand a structure with more than about twelve parts one region at a time

When one of these holds, write a one-paragraph spec before any hand-off: the
reader's action, the first state shown, what each interaction reveals, and
the one thing that must stand out. The first state is the takeaway, already
visible before the reader touches anything.

## Hand-offs by harness

Hand the medium to the skill that owns it. Carry the takeaway, the altitude,
the anchor, the profile's budget, and the interaction spec into that skill's
input, so that the medium skill does not re-decide them.

For a page, the link is the output in step 7's reply shape: link, then the
lines the page skill asks for, then the reader line and the assumptions. The
reader line also goes on the page, under its summary. The profile's budget
binds the page's prose, and the page template's summary rows, decisions, and
risks count toward it, so delete template sections the budget cannot afford
rather than fill them.

- **Chat first when selected.** Write the reply and text diagrams directly.
  No Python, filesystem, discovery state, page helper, or installation is needed.
- **For HTML, inspect only the needed capabilities.** Reuse relevant saved
  `artifacts` facts or inspect the session's tools and documentation for present,
  update, audience/access, comments, and required interaction support. Record
  the source and any uncertainty in the hand-off. A local file counts only
  when the user has a supported way to open it. Verify that the destination
  retains the page's styles and scripts; text storage is not an HTML destination.
- **Durable discovery is conditional.** When orchestration or repeated setup
  needs a repository record, use `harness-discovery` and its existing registry.
  With that skill and Python available, read a saved entry using
  `python3 <harness-discovery>/scripts/state.py resolve --harness '<harness>'`.
  A single destination lookup can remain session-local; it does not require
  seeding a registry, installing a companion, or contributing upstream.
- **Authorize delivery separately.** Apply the settings contract's content,
  destination, and audience gate before uploading or widening access. A single
  public destination does not authorize publication. Preserve approved settings
  and authority on refresh; recheck access if it changed or is uncertain.
- **HTML unavailable or held.** Report the missing capability or permission.
  Keep an unshared HTML draft if possible. If the user or caller requires HTML
  or interaction, do not silently replace it with Markdown. Offer a different
  output only as an explicit scope change, not a completed HTML workflow.

## Markdown document placement

Put the document where the repository keeps that kind of document: a
`docs/` folder, a runbooks folder, an architecture decision records folder.
Follow the naming the folder already uses. Link it from the folder's index
when one exists. A document nobody can find has the lifetime of a chat reply.

When the thing explained lives in another repository than the one you are
in, write the document for that repository, state the path it belongs at,
and leave it in the reply or in the artifacts folder for the user to move.
