---
name: example-skill
description: Template skill demonstrating the layout this pack expects. Copy this folder as the starting point for a real skill, then rewrite the frontmatter and body. Not intended to be invoked directly.
---

# Example Skill

This file is a working template. It is valid enough to install, and its only
real job is to show the shape a skill in this pack should take.

## When to use

Trigger conditions belong here, written as concrete situations rather than
abstractions. An agent matches on the `description` frontmatter first, so the
description carries the triggering weight — this section explains the judgement
calls the description has no room for.

Use this skill when:

- You are creating a new skill in this pack and want the standard layout.
- You need a reminder of which frontmatter fields are required.

Do **not** use this skill when:

- You are looking for a real capability. This is a template.

## Steps

1. Copy this directory: `cp -r skills/example-skill skills/<your-skill-name>`.
2. Rewrite the frontmatter. `name` must be lowercase-with-hyphens and must match
   the directory name. `description` must state *what it does* and *when to use
   it* — that string is the entire basis on which an agent decides to load it.
3. Replace this body with real instructions. Write for an agent, not a human
   browsing docs: imperative steps, exact commands, explicit failure modes.
4. Move long reference material into `references/` and link to it, so the agent
   only pays for those tokens when it actually needs them.
5. Put executable helpers in `scripts/` and invoke them by relative path.
6. Run `node scripts/validate-skills.mjs` from the repo root before committing.

## Layout

```
skills/<name>/
  SKILL.md        required — frontmatter (name, description) + instructions
  references/     optional — deep detail loaded on demand
  scripts/        optional — executable helpers the skill calls
```

## Progressive disclosure

Keep `SKILL.md` short enough that loading it is cheap. Anything long, rarely
needed, or exhaustive goes in `references/` — see
[references/writing-good-descriptions.md](references/writing-good-descriptions.md)
for how to write a `description` that actually triggers.
