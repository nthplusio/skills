# Harness profile: amp

How pstack's needs map onto Amp. Built and maintained per [`../references/adapting.md`](../references/adapting.md); need IDs come from [`../needs.json`](../needs.json).

## Destination

- **Skills directory**: the Workspace Skills repository clone at `~/.cache/amp/repositories/ampcode.com-workspace-skills`. Prepare it by fetching and `git reset --hard origin/main`, or clone it with the command `amp skills repositories` prints for Workspace Skills; that output must list it as writable. Source: `building-skills` skill.
- **Publish**: commit in the clone, then `git push` after the user confirms; a push changes skills for every workspace member. Source: `building-skills` skill.
- **Reload**: `reload_skills` tool after the push. Source: Amp tool list.
- **Name shadowing**: local, built-in, and personal skills mask a workspace skill with the same name. Source: ampcode.com/docs/customize/skills, "Skill Sources and Precedence".

## Needs

| Need | Support | Amp equivalent | Source |
| --- | --- | --- | --- |
| `skill-locations` | substitute | Project skills: `.agents/skills/<name>/`. Personal: the User Skills repository (`amp skills repositories`), or `~/.config/agents/skills/` on one machine. Reload with `reload_skills`. | ampcode.com/docs/customize/skills; `building-skills` skill |
| `persistent-rules` | substitute | User-wide: `~/.config/amp/AGENTS.md`. Project: `AGENTS.md` in the repository (scoped to its directory tree). | Amp AGENTS.md loading |
| `role-model-config` | none | No per-role model config. Every role uses the parent model; drop the config read. | `Task` tool schema (no model parameter) |
| `model-selection` | partial | `Task` subagents run on the parent model. A run on another model: `create_thread` with `agent_mode` from `list_agent_modes`. A stronger-model review: `oracle`. | `Task`, `create_thread`, `oracle` schemas; `amp.list_agent_modes` |
| `subagents` | substitute | `Task` tool; calls issued in one turn run in parallel. No `subagent_type`. | `Task` tool schema |
| `readonly-subagents` | partial | Say "read-only: do not edit files" in the `Task` prompt. | `Task` tool schema (no readonly parameter) |
| `ask-user` | partial | Ask in the reply. `ask_user_choice` (2-5 options) only when the user asked to be asked questions. | `ask_user_choice` tool description |
| `transcripts` | substitute | Past chats are Amp threads: `find_thread` to search, `read_thread` to read. Scope to the current repository. | `amp` module (`tool_search "find thread"`); `read_thread` tool |
| `loop` | partial | A thread schedule via the `building-schedules` skill; the check stays the stop condition. | `building-schedules` skill |
| `background-agents` | substitute | An orb thread via `create_thread`. | `create_thread` schema; ampcode.com/docs/orbs |
| `worktrees` | partial | `git worktree list`; `create_thread` with `worktree` creates `<checkout>-<name>` siblings on runners only. | `create_thread` schema |
| `modes` | substitute | Remove `mode`, `icon`, `color`, `reminder`. Amp reads frontmatter `mode` as an agent-mode override, so `mode: true` is wrong, not ignored. | `building-skills` skill, "Optional fields" |
| `invocation-control` | keep | Amp does not document `disable-model-invocation`; the key is harmless and the skill stays model-visible. | ampcode.com/docs/customize/skills, "Skill Format" |
| `bugbot` | keep | GitHub app, independent of the harness. | — |
| `cursor-product` | substitute | Name Amp where the sentence still holds; cut Cursor-only claims. | — |
| `companion-skills` | partial | `create-skill` → the `building-skills` skill. `control-ui` → the `using-agent-browser` skill (browser and web UIs, in an orb). `control-cli` → no skill; drive the CLI from the shell, with tmux for interactive TUIs. `deslop` → no skill; do the slop-strip pass on the diff yourself. | Amp skill list (`using-agent-browser`, `building-skills`) |
| `custom-subagents` | partial | No named subagent definitions. Dispatch `Task` and put the role's instructions in its prompt; pstack's `agents/*.md` are not synced, so carry the essential rules inline. | `Task` tool schema |
