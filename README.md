# skills

A [skills.sh](https://www.skills.sh) pack — a collection of reusable skills for
AI coding agents.

## Install

Install the [pack](https://www.skills.sh/docs/packs):

```bash
npx skills add https://skills.sh/p/LnXuSpHo8Jw01lUf
```

To install from this repository instead, bypassing the pack:

```bash
npx skills add nthplusio/skills
```

To install a single skill:

```bash
npx skills add nthplusio/skills --skill speak-clearly
```

## What's in here

| Skill | Description |
| --- | --- |
| [`scoussens-skills/meeting-index`](skills/scoussens-skills/meeting-index/SKILL.md) | Index a period of recorded meetings — the threads that carried across them, a per-meeting ledger, and what got decided, owned and left at risk. Reads from Plaud or any source with a listing and per-meeting notes. Invoked explicitly. |
| [`scoussens-skills/release-brief`](skills/scoussens-skills/release-brief/SKILL.md) | Turn a window of shipped work into a brief for a non-technical stakeholder, verified against what actually reached production. Invoked explicitly. |
| [`scoussens-skills/speak-clearly`](skills/scoussens-skills/speak-clearly/SKILL.md) | Write human-facing prose in Google developer style: named actors, condition-first sentences, timeless tense, no filler. |

## Layout

The skills CLI discovers skills by convention — there is no manifest to
maintain. It walks the `skills/` container directory up to three levels deep
looking for `SKILL.md`, and a shallower `SKILL.md` shadows any nested beneath
it.

```
skills/
  <skill-name>/
    SKILL.md        required — frontmatter + instructions
    references/     optional — detail loaded on demand
    scripts/        optional — executable helpers
```

Flat (`skills/<name>/`) and categorised (`skills/<category>/<name>/`) layouts
are both supported.

## Adding a skill

```bash
mkdir -p skills/my-new-skill
$EDITOR skills/my-new-skill/SKILL.md
node scripts/validate-skills.mjs
```

`SKILL.md` requires exactly two frontmatter fields:

```yaml
---
name: my-new-skill
description: What it does. Use when <trigger>, <trigger>, or <trigger>.
---
```

- `name` — lowercase-with-hyphens, and **must match the directory name**.
- `description` — the only text an agent sees before deciding to load the
  skill. See [writing good descriptions](docs/writing-good-descriptions.md).

## Validation

```bash
node scripts/validate-skills.mjs
```

The pack builder fails *quietly*: it skips invalid `SKILL.md` files and omits
binary or over-2 MB files without reporting an error, so a broken pack still
installs — just with skills missing. The validator turns those silent omissions
into a non-zero exit, and runs in CI on every push and pull request.

It checks:

- frontmatter is present and parses
- `name` and `description` exist, and `name` matches its directory
- no file exceeds 2 MB
- no binary files are committed inside a skill

## Licence

[MIT](LICENSE)
