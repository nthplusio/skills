# Output formats and theme

A proposal is read in one of three places, and the choice changes the writing
as much as the export. This covers the constraints of each, including how much
of the project's theme each one can carry.

## Contents

- [Choosing the format](#choosing-the-format)
- [Artifact](#artifact)
- [PDF](#pdf)
- [Email and Markdown](#email-and-markdown)
- [Theme constraints per format](#theme-constraints-per-format)

## Choosing the format

Ask. The right answer depends on what the reader does next, not on which is
nicest to build.

| Signal from the user | Format |
| --- | --- |
| "send it to them", "forward this to the board" | Artifact — a link survives forwarding; an attachment gets detached |
| "attach it", "they need to sign", "print it" | PDF |
| "reply to this thread", "put it in the email" | Markdown in the body |
| Tables, cost breakdowns, anything columnar | Artifact or PDF — email clients mangle tables |
| Fewer than roughly 300 words | Email, whatever else was asked |

Offering both an Artifact and a Markdown summary is often right — the link for
the detail, a short summary in the email body so the recipient reads something
without clicking.

## Artifact

The default for anything with a cost table. Publish it to a hosted page: one of
the `artifacts` that the repository's `.nthplusio-skills/discovery.json` records
for the harness you are running in, when its tool is in your tool list;
otherwise a page-publishing tool from your tool list, such as an `Artifact`
tool. With neither, save the HTML file locally, open it when there is a desktop,
and give its path. If an `artifact-design` skill is available, load it before
writing the page; it carries the design fundamentals and the theming rules the
platform requires.

Two things matter more for a proposal than for most pages:

**It renders in the reader's theme.** Define the complete palette as tokens on
bare `:root`, redefine only the tokens under `prefers-color-scheme` and under
an explicit `[data-theme]` stamp, and give `body` an explicit token background.
A colour defined only inside a media query renders one theme's text on the
other theme's ground, and a proposal that arrives unreadable is worse than a
plain one.

**Tables need their own scroll container.** Wrap each in an element with
`overflow-x: auto` so a narrow window scrolls the table rather than the page.
Use `font-variant-numeric: tabular-nums` on every money and hours column so
digits line up down the column.

Tell the user the page stays private until they share it. Clients sometimes
assume a link is already public and hold back on that basis.

## PDF

Write the same HTML, add a print stylesheet, and render it with headless
Chrome:

```bash
scripts/html-to-pdf.sh proposal.html proposal.pdf
```

The script tries Chrome, Chromium, and Edge in turn, prints which one it used,
and fails loudly rather than producing a zero-byte file. It renders backgrounds
and honours `@page` — both off by default in headless Chrome, and both needed
for a themed document.

Print is a different medium, so add a print block rather than shipping the
screen styles:

```css
@page { size: Letter; margin: 18mm 16mm; }

@media print {
  :root { color-scheme: light; }          /* never print a dark theme */
  body  { background: #fff; font-size: 10.5pt; }
  .scroller { overflow: visible; }        /* scroll containers clip in print */
  table { break-inside: auto; }
  tr, .note, .phase { break-inside: avoid; }
  thead { display: table-header-group; }  /* repeat headers across pages */
  tfoot { display: table-row-group; }     /* print the total once, at the end */
  caption { break-after: avoid; }         /* keep the caption with its table */
  h2, h3 { break-after: avoid; }          /* no heading orphaned at a page foot */
  a::after { content: " (" attr(href) ")"; font-size: 9pt; }
}
```

Three failures account for nearly every bad proposal PDF, and all three are
invisible in the source:

**A scroll container clips.** `overflow-x: auto` scrolls on screen and *crops*
in print, silently cutting the right-hand columns off a cost table. The
`.scroller { overflow: visible }` line above is the fix.

**A table fragments into an empty stub.** When a long table starts near the
foot of a page, the renderer can place the repeated header and the footer total
there with no rows between them, so the reader meets a header, a bold total,
and then the actual rows overleaf. `tfoot { display: table-row-group }` stops
the total repeating on every fragment; if a stub still appears, force the table
onto a fresh page with `break-before: page` on its container.

**A dark theme survives.** A page that respects `prefers-color-scheme` will
print dark if the renderer reports a dark preference, producing a document that
is unreadable and expensive to print. Pin `color-scheme: light` and set an
explicit white background rather than trusting the default.

Open the rendered PDF and look at every page before sending. Page breaks are
the one thing here you cannot verify by reading the source, and each of the
three failures above renders as a plausible-looking page.

## Email and Markdown

Assume every stylesheet is stripped, because in most clients it is. That is a
writing constraint, not a styling one:

- Heading levels carry the hierarchy. Nothing else will.
- Keep tables to three columns or fewer, or replace them with a short labelled
  list. Wide Markdown tables are unreadable in a phone mail client.
- Put each reference or identifier on its own line so it survives pasting.
- No theme survives. Do not spend effort on one.

Markdown is also the right output when the proposal is going into a tracker
comment or a shared doc, where the destination applies its own styling.

## Theme constraints per format

Find the project's design system and take its values with
[theming-from-a-repo.md](theming-from-a-repo.md). This table adds what each
format allows.

| | Artifact | PDF | Email |
| --- | --- | --- | --- |
| Full palette | Yes, both themes | Light only | None |
| Web fonts | Google Fonts only | Any the renderer can reach | None |
| Tables | Scroll container | Print block, repeat headers | Three columns maximum |
| Logo | Inline SVG, token-driven fills | Inline SVG | Omit |
| Dark theme | Required | Never | Not applicable |
