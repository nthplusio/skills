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
| [`scoussens-skills/work-proposal`](skills/scoussens-skills/work-proposal/SKILL.md) | Turn a body of scoped work into a client-ready proposal — effort grounded in the codebase, priced against the agreement that already exists, delivered as a themed Artifact, PDF, or email. Invoked explicitly. |

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
npm run validate
npm run check:builder
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
npm install
npm run validate
```

The pack builder fails *quietly*: it skips invalid `SKILL.md` files and omits
binary or over-2 MB files without reporting an error, so a broken pack still
installs — just with skills missing. The validator turns those silent omissions
into a non-zero exit, and runs in CI on every push and pull request.

It checks:

- frontmatter parses as YAML, using the same parser the builder uses
- `name` and `description` exist, are strings, and `name` matches its directory
- no file exceeds 2 MB
- no binary files are committed inside a skill

### The builder-agreement check

```bash
npm run check:builder
```

The validator *encodes* the builder's rules, and encoded rules drift. This
check encodes nothing: it runs the real skills.sh CLI against the checkout and
asserts it finds every skill the repository contains, so it cannot fall out of
step by construction. When the two disagree, it prints the file, the builder's
own reason, and what the gap costs:

```
✗ the builder skipped .../meeting-index/SKILL.md
    YAML parse error: Nested mappings are not allowed in compact mappings at line 2, column 14:
✗ "meeting-index" exists in this repo but the builder did not find it
✗ the builder reported 2 skill(s); this repository contains 3
```

It reaches the network and runs `skills@latest`, so an upstream change can fail
the build without anything here changing. That is the point — upstream changing
the rules is worth being told about — but it is why CI runs it as its own job,
separate from the hermetic validator, so the two failures are never confused.

The validator has one dependency, `yaml`, and that is deliberate. Frontmatter
must be parsed with the parser the builder uses, because a reimplementation
drifts and the drift is silent. A hand-rolled reader here once accepted a
description containing `": "` — which YAML reads as a nested mapping — and
reported three valid skills while the pack shipped two.

### Descriptions cannot contain `": "`

A colon followed by a space makes an unquoted YAML value ambiguous with a
nested mapping, and the whole skill is dropped. Introduce a list of trigger
phrases with an em dash instead:

```yaml
# Breaks the skill, silently
description: Load this when the user asks for an index: "index my meetings".

# Correct
description: Load this when the user asks for an index — "index my meetings".
```

## Licence

[MIT](LICENSE)
