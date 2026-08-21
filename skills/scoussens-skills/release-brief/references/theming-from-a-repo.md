# Theming from a repository

A brief that looks like the product it describes reads as the customer's
document. This is how to take a real design system rather than approximate one.

## Contents

- [Find the design system](#find-the-design-system)
- [Take the values literally](#take-the-values-literally)
- [Obey the constraints the stylesheet documents](#obey-the-constraints-the-stylesheet-documents)
- [Typefaces](#typefaces)
- [Logos and marks](#logos-and-marks)
- [Deriving a dark palette](#deriving-a-dark-palette)
- [When there is no design system](#when-there-is-no-design-system)

## Find the design system

Check the repository's own agent instructions first — `CLAUDE.md`, `AGENTS.md`,
or a `docs/` standards directory usually name the package that owns styling.
Failing that, search:

```bash
fd -e css -e ts 'theme|tokens|design|styles' packages apps src 2>/dev/null
rg -l '@theme|:root\s*\{|--color-|tailwind.config' --type css --type ts
```

A design system tends to sit in a shared package rather than an application, so
prefer `packages/ui/**` over `apps/web/src/index.css` when both exist. Read the
comments as well as the values: a well-kept tokens file explains which colours
are decorative, which are accessible as text, and which pairings were measured.

## Take the values literally

Copy the declarations rather than eyeballing an equivalent. If the file defines
its anchors in a colour space you can use directly — `oklch()`, `lab()`, or hex
— keep that notation, so a reader comparing the brief to the product sees the
same colour rather than a near miss.

Extract, in this order:

1. **Brand anchors.** Usually two or three literal values everything else
   derives from, often annotated with a Pantone or brand-sheet reference.
2. **The surface ladder.** Page canvas, card, grouped area, emphasis. These
   carry more of the product's feel than the accent does.
3. **Text roles.** Primary, secondary, tertiary, plus the border colour.
4. **Semantic colours** for status or severity, if the brief encodes any.
5. **Radius, shadow, and spacing** tokens. A system that uses warm-tinted
   shadows instead of black is making a deliberate choice worth carrying over.

## Obey the constraints the stylesheet documents

Design systems record hard-won rules, and a brief that breaks them looks
off-brand in a way readers feel without diagnosing. Watch for:

- **An accent that is decorative only.** Many bright brand colours fail contrast
  as text on a light surface, so the system ships a darkened variant for text.
  Use the variant the file names for that purpose.
- **A stated baseline weight.** A body face specified at medium reads wrong at
  the 400 a browser would default to.
- **Deliberate absences.** If the file says the brand is sans-only, do not
  introduce a serif for display.

## Typefaces

Licensed faces will not load in a published page. The stylesheet's fallback
stack usually already names the intended open substitute — use it, and keep the
licensed face first in the stack so a viewer who has it installed sees the real
thing.

Google Fonts is the one external host an Artifact may load from. Link the
substitutes there and declare a real fallback stack after them.

## Logos and marks

A small SVG mark inlines cleanly and is worth the space in a masthead. Drive its
fills from your theme tokens rather than hardcoding the brand hexes: a dark
brand colour disappears against a dark ground, and most brands ship a
light-surface variant precisely because of this.

Never redraw a mark by hand. Use the committed asset or omit it.

## Deriving a dark palette

Products often ship only a light theme, but a brief renders in the reader's
theme. Derive the dark set from the same hues rather than inverting:

- Re-lighten the surface ladder into the 0.17–0.30 lightness range, keeping the
  same hue and roughly the same chroma, so the warmth or coolness survives.
- Lift any accent that is too dark to read on the new ground, holding its hue.
  A deep brand blue may need to travel most of the lightness range; a mid-tone
  gold often needs no change.
- Define every colour as a token on the base `:root`, then redefine only the
  tokens in the dark blocks. A colour whose only definition sits inside a
  media query renders one theme's text on the other theme's ground.

Say in your reply that the dark treatment is derived rather than shipped, so
nobody mistakes it for an existing product decision.

## When there is no design system

Pick a restrained palette from the customer's public brand — their site,
their logo — and commit to it. Two colours and a considered neutral beat a
generic template. Tell the user you chose rather than found it, so they can
correct you.
