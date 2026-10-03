# context-statusline

A Claude Code plugin that draws a card above the prompt with the model, the
context window, prompt cache warmth, and the git repo and branch.

```
╭──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ ◆ Opus 5.5   ctx 450k ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▌▓▓▓▓▓▓▓▌▓░░░▏░░▏░▏░ 1M (550k left)   cache warm 57m · hit 97%    platform   ui-676 │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## Install

```
/plugin marketplace add nthplusio/skills
/plugin install context-statusline@nthplusio
```

The repo and branch icons are Nerd Font glyphs. Without a Nerd Font they draw
as blank cells.

## What the card shows

- **Model**: the session's model, for example `Opus 5.5`.
- **Context**: tokens used on the left, the window size on the right, and a
  bar of the whole window between them. The bar is split into bands by how
  comfortable that much context is:
  - The target band, green, takes half the bar. It runs to 200k on a larger
    window, or over the first half of a window of 200k or less.
  - Five bands from yellow to red split the rest of the window into equal
    token ranges, but each takes less of the bar than the one before (20, 12,
    8, 6 and 4%), since that context is a worse place to be.
  - Used cells are bright, the window ahead is dimmed in its band's colour,
    and `▌`/`▏` marks where a band starts. A band too narrow for a divider is
    marked by its colour alone.
  - Past 200k, or at the cap, the room left follows: `(550k left)`.
- **Cache**: how long the prompt cache stays warm after the last response,
  and the share of the last request the cache served:
  `cache warm 57m · hit 97%`. Once the time runs out it reads
  `cold 12m ago`; after a model switch, `cold (model switch)`. The countdown
  updates every 15 seconds and ignores subagents, which cache their own
  prefixes.
- **Git**: the repository and branch of the working directory, outside a
  repository nothing.

## Narrow terminals

The card always fits on one line. As the terminal narrows, the bar first
shrinks from 40 cells to 20, then parts give way in this order:

1. The repository name, trimmed to 12 cells and then dropped.
2. The cache hit rate.
3. The branch, trimmed from the front (`…ui-676`) and then dropped.
4. The room note.
5. The cache segment.
6. The bar shrinks to 10 cells, then the `ctx` label and the bar go.
7. The model name is trimmed last.

A narrower terminal never shows more than a wider one, and never a longer
bar.

## Settings

`/config` lists one setting, **Prompt cache TTL** (`cacheTtl`): `1h`, the
default, or `5m`. Claude Code reports the cache lifetime only when the model
changes, so until then the card counts down from this setting.
Subscription sessions use a 1-hour cache; API-key sessions default to 5
minutes.

## Develop

Load a checkout in place of the installed plugin:

```bash
claude --plugin-dir plugins/context-statusline
```

Run the tests, which include a sweep over every terminal width from 20 to 200
columns:

```bash
claude plugin test plugins/context-statusline
claude plugin validate plugins/context-statusline
```

`tsconfig.json` extends `.claude-plugin/types/tsconfig.json`, which Claude
Code writes the first time it loads the plugin. Once it has loaded the plugin,
`npx tsc -p plugins/context-statusline` type-checks it. The generated types
are gitignored.

All layout and formatting is pure and lives in `hooks/format.ts`;
`hooks/register.tsx` gathers the figures and draws the strings the layout
returns.
