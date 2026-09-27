# Catch broken links inside skills

## Problem Statement

A skill's `SKILL.md` points at its own `references/` and `scripts/` files with relative Markdown links. When a file is renamed or moved, the link breaks, and nothing notices: the pack still validates and still installs. An agent that follows the broken pointer finds nothing and carries on without the material, so the skill quietly gets worse. This has already happened once, when `pr-digest` renamed a reference file.

## Solution

The validator checks every relative link in every Markdown file inside a skill, and fails when a link points at a file that does not exist. It should be fast enough to run in a pre-commit hook.

## Implementation Decisions

- Reuse the shared skill-discovery module so the link check walks exactly the skills the validator walks.
- Only relative links are checked. Links starting with `http://`, `https://`, or `#` are skipped.
- A link that points outside its own skill folder is an error too, because the pack builder installs each skill on its own and the target would not travel with it.
- Report each broken link as `file:line → target`.
