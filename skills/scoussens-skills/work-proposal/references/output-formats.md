# Output formats and theme

A proposal is read in one of three places, and the choice changes the writing
as much as the export. This covers the constraints of each, and how to take a
theme from the project rather than reaching for a template.

## Contents

- [Choosing the format](#choosing-the-format)
- [Artifact](#artifact)
- [PDF](#pdf)
- [Email and Markdown](#email-and-markdown)
- [Taking the theme from the project](#taking-the-theme-from-the-project)
- [When the project has no design system](#when-the-project-has-no-design-system)
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

The default for anything with a cost table. Load the `artifact-design` skill
before writing the page; it carries the design fundamentals and the theming
rules the platform requires.

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

## Taking the theme from the project

Look for a design system before choosing colours. The repository's own agent
instructions — `CLAUDE.md`, `AGENTS.md`, a `docs/` standards directory — usually
name the package that owns styling. Failing that:

```bash
rg -l '@theme|--color-|:root\s*\{|tailwind.config' --type css --type ts
fd -e css -e ts 'theme|tokens|design|brand' packages apps src 2>/dev/null
```

Prefer a shared package (`packages/ui/**`, `libs/design-system/**`) over an
individual app's stylesheet when both exist. Read the comments as well as the
values — a well-kept tokens file records which colours are decorative, which
are safe as text, and which pairings someone measured.

Take the values literally rather than approximating them, and keep the notation
the file uses so a reader comparing the proposal to the product sees the same
colour. Extract in this order: brand anchors, the surface ladder (page, card,
grouped area), text roles, semantic status colours, then radius and shadow.

Honour the constraints the file documents. The common ones:

- **A decorative-only accent.** Many brand colours fail contrast as text, so
  the system ships a darkened variant for that purpose. Use it.
- **A stated baseline weight.** A body face specified at medium reads wrong at
  a browser's default 400.
- **Deliberate absences.** If the system is sans-only, do not add a serif.

Licensed typefaces will not load in a published page. The fallback stack
usually already names the intended open substitute — use it, and keep the
licensed face first so a viewer who has it sees the real thing.

## When the project has no design system

Derive a restrained palette from the client's public brand — their site, their
logo, a brand sheet in the repository. Two colours and a considered neutral
beat any template.

A neutral with a slight hue bias toward the accent reads as chosen; a pure
mid-grey reads as inherited. Where the brand is a single colour, pair it with a
neutral drawn from the same hue family rather than introducing a second brand
colour it never uses.

Say in your reply that you chose the palette rather than found it, so the user
can correct you before it reaches the client. Where a repository issue records
a known brand inconsistency — logo artwork disagreeing with a brand sheet, for
instance — flag it rather than silently picking a side.

## Theme constraints per format

| | Artifact | PDF | Email |
| --- | --- | --- | --- |
| Full palette | Yes, both themes | Light only | None |
| Web fonts | Google Fonts only | Any the renderer can reach | None |
| Tables | Scroll container | Print block, repeat headers | Three columns maximum |
| Logo | Inline SVG, token-driven fills | Inline SVG | Omit |
| Dark theme | Required | Never | Not applicable |
