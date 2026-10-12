# Harness profile: amp

How pstack's own needs map onto Amp. Built and maintained per [`../references/adapting.md`](../references/adapting.md); need IDs come from [`../needs.json`](../needs.json). The needs that name discovery fields there take Amp's facts from the repository's `.nthplusio-skills/discovery.json`, so they have no row here.

## Destination

- **Skills directory**: the user's choice among the locations discovery records in `skills.locations`; ask when they have not said. In Amp there are three. The Workspace Skills repository (clone at `~/.cache/amp/repositories/ampcode.com-workspace-skills`) shares the skills with every workspace member. The User Skills repository keeps them personal. A project's `.agents/skills/` limits them to that project. For either repository, prepare its clone by fetching and `git reset --hard origin/main`, or clone it with the command `amp skills repositories` prints for it; that output must list it as writable. Source: `building-skills` skill.
- **Publish**: for a skills repository, commit in the clone, then `git push` after the user confirms; a push to the Workspace Skills repository changes skills for every workspace member. For `.agents/skills/`, the files take effect in that checkout, and committing them follows the project's own process. Source: `building-skills` skill.
- **Reload**: after publishing, as discovery records in `skills.reload`.
- **Name shadowing**: local, built-in, and personal skills mask a workspace skill with the same name. Source: ampcode.com/docs/customize/skills, "Skill Sources and Precedence".

## Needs

| Need | Support | Amp equivalent | Source |
| --- | --- | --- | --- |
| `role-model-config` | substitute | **Store**: a `## pstack models` section in `~/.config/amp/AGENTS.md` (loaded into every session), written by `/setup-pstack`; first line `budget: <label>`, then one line per role, `<role>: <value>` (panel roles take a comma list; one subagent per entry). **Values**: `inherit` (default for a missing line or section), an Amp agent-mode key from `list_agent_modes` (for example `low`, `medium`, `high`, or a plugin mode), or `oracle` (judge, synthesizer, and explainer roles only). **Honor**: `inherit` → `Task` on the parent model; a mode → `create_thread` with that `agent_mode`, the role's brief as the prompt, collected with `wait_for_threads` then `read_thread`; `oracle` → the `oracle` tool. A mode named in this section counts as the user's explicit choice for `create_thread`. Where a skill names a model for a role, it uses that role's line instead of a fixed model. **Roles**: the upstream role names from `setup-pstack`. In an orb the file lives in the orb, so `/setup-pstack` tells the user where it wrote. | `create_thread` schema (`agent_mode`, choice-in-guidance-file rule); `amp.list_agent_modes`; `oracle` schema; Amp loads `~/.config/amp/AGENTS.md` as user-private global instructions |
| `modes` | substitute | Remove `mode`, `icon`, `color`, `reminder`. Amp reads frontmatter `mode` as an agent-mode override, so `mode: true` is wrong, not ignored. | `building-skills` skill, "Optional fields" |
| `invocation-control` | keep | Amp does not document `disable-model-invocation`; the key is harmless and the skill stays model-visible. | ampcode.com/docs/customize/skills, "Skill Format" |
| `bugbot` | keep | GitHub app, independent of the harness. | — |
| `cursor-product` | substitute | Name Amp where the sentence still holds; cut Cursor-only claims. | — |
| `companion-skills` | partial | `create-skill` → the `building-skills` skill. Cursor's built-in `babysit` → none; pstack's Babysit playbook does the job, so cut text that steers away from the built-in. `/add-plugin` → none; pstack-sync installs pstack, so say that instead. `building-skills`, `building-schedules`, and `using-agent-browser` are Amp's own skills, accepted in `transform.json`. Skills pstack takes from cursor/plugins install as dependencies and keep their hand-offs. | Amp skill list (`using-agent-browser`, `building-skills`, `building-schedules`) |
| `custom-subagents` | substitute | No named subagent definitions. pstack-sync installs each definition pstack dispatches as `pstack-agents/<name>.md` in the skills directory. Dispatch `Task` with a prompt that gives that file's absolute path and tells the subagent to read and follow it before the task. | `Task` tool schema |
