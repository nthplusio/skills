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

Reuse the form fixed by the request or saved setup through `explain-to`'s
settings contract. Ask only unresolved consequential choices before drafting.
These signals recommend defaults, not overrides of the user's chosen output
or permission to send:

| Signal from the user | Format |
| --- | --- |
| "send it to them", "forward this to the board" | Artifact — a link survives forwarding; an attachment gets detached |
| "attach it", "they need to sign", "print it" | PDF |
| "reply to this thread", "put it in the email" | Markdown in the body |
| Tables, cost breakdowns, anything columnar | Artifact or PDF — email clients mangle tables |
| Fewer than roughly 300 words | Email draft, unless another output is fixed |

Offering both an Artifact and a Markdown summary is often right — the link for
the detail, a short summary in the email body so the recipient reads something
without clicking.

## Artifact

The default for anything with a cost table. Use saved destination facts or
narrow capability inspection as `explain-to`'s `references/formats.md` ("Hand-offs by
harness") describes. If an `artifact-design` skill is available, load it before
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

Before uploading proposal content, verify the destination's access rules:
named recipients, workspace members, anyone with the link, or public access.
Report the observed audience and its evidence, not a blanket privacy promise.
Publish only when that destination and audience are authorized. If access
cannot be verified or exceeds the approved audience, keep the draft local or
in the conversation and ask before publication.

## PDF

PDF generation requires Bash, Python 3, and a Chrome-compatible browser; plain
Markdown drafting does not. Resolve the script from the installed skill
directory, add a print stylesheet to the HTML, then render it:

```bash
bash "$SKILL_DIR/scripts/html-to-pdf.sh" proposal.html proposal.pdf
# If automatic discovery misses your installed browser:
CHROME_BIN="/absolute/path/to/chrome" bash "$SKILL_DIR/scripts/html-to-pdf.sh" proposal.html proposal.pdf
```

Set `SKILL_DIR` to the installed `work-proposal` directory. The script searches
PATH, standard macOS application paths, and agent-browser/Playwright Linux
caches. `CHROME_BIN` selects an executable, not a shell command with arguments.
It reports the selected browser and requires both exit status 0 and a fresh,
nonempty file with a PDF signature before replacing the destination. A failed
rerender leaves an older PDF unchanged and reports failure; that older file is
not evidence of a successful rerender. The signature check does not prove
content, page layout, or asset availability: inspect the result below.

If no renderer is available, return the HTML or Markdown draft and state that
PDF export is unavailable. Do not claim a PDF was produced. Use `@page` for
size and margins and check that the renderer preserves the intended theme.

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

Prepare email and tracker text as a draft. A drafting request does not authorize
message sends, tracker comments, or shared-document writes. Send or post only
when the user authorizes the content, destination, and recipients; otherwise
return the text for review. Report whether delivery was drafted, attempted,
confirmed, or unverified from the tool result.

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
