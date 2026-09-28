# Theming the page from a repository

Read this when step 4 finds a theme or style guide. It says what to take from the theme, and where each value goes in the template's `THEME` block. When a tokens file and a written guide disagree, use the tokens file, because the product uses it.

## What the theme owns, and what it does not

The page has two kinds of colour:

- **Chrome** is the page itself: `--bg`, `--surface`, `--ink`, `--muted`, `--line`, `--wire`, `--accent`, `--sans`, `--mono`. The repository's theme owns these. With them replaced, the page reads as the project's own.
- **Meaning** is the legend: `--new`, `--changed`, `--removed`, `--gap`, `--test`, and their `-bg` pairs. The skill owns these, because the legend must read the same on every page. Replace `--new`, `--changed`, and `--removed` only when the theme defines success, warning, and danger colours. Then map success to new, warning to changed, and danger to removed. `--gap` and `--test` always keep their defaults.

After any replacement, the five meaning colours must still look different from each other and from `--accent`. A brand accent that is purple collides with `--gap`. In that case, keep the default `--accent` and say so in your reply.

## Take the values literally

Copy each value in the notation the file uses: hex, `rgb()`, `oklch()`. A near match looks off to someone who knows the product.

Map by role, not by name. A tokens file rarely uses the template's names, so match what each one is for:

| Template token | The theme's role |
| --- | --- |
| `--bg` | page canvas, background |
| `--surface` | card, panel, raised surface |
| `--ink` | primary text, foreground |
| `--muted` | secondary text |
| `--line` | border, divider |
| `--wire` | stronger border, or the midpoint of `--line` and `--muted` when the theme has none |
| `--accent` | primary, brand, or link colour. Use the variant the file marks as safe for text, when it gives one |
| `--sans`, `--mono` | body and code font stacks |

Obey any rule the file states, such as "this accent is decorative only" or "body text is weight 500".

## Fonts

The page loads nothing from the network, so it must still work offline. Put the theme's font first in the stack, then keep the template's system fallbacks after it. A reader who has the font installed sees it, and everyone else gets the system font. Do not add a `<link>` to a font host.

## Dark mode

The template defines dark values twice, and the two blocks must match. `check_page.py` fails when they differ.

- **The theme defines dark values:** copy them into both dark blocks.
- **The theme is light only:** derive dark chrome from the same hues. Put the surfaces at roughly 8 to 18 percent lightness, and keep their tint. Lighten the accent until it reads on the dark surface. Tell the user in your reply that the dark version is derived, so nobody mistakes it for a product decision.

## Record the source

Your reply names the theme's source file, or says the page uses the default theme because no theme was found. Say also which tokens kept their default, and why.
