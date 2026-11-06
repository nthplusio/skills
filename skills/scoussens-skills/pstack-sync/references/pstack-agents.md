---
name: pstack-agents
description: Provides bundled pstack role definitions. Use when a workflow needs the installed path to poteto-agent.md or comment-sicko.md.
---

# Pstack role definitions

Resolve the selected file from this skill's loaded absolute directory.

- `poteto-agent.md` defines the delegate style for `poteto-mode`.
- `comment-sicko.md` defines the comment-review role for `no-comments`.

Pass the selected file's absolute path to the delegate and tell it to read and
follow that file before starting. For Poteto agent, also pass the loaded
`poteto-mode/SKILL.md` absolute path.

Use the caller's supported dispatch tool and retain its scope and approval
limits. Role definitions add instructions, not capabilities or authorization.
