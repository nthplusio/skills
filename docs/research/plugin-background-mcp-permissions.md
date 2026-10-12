# Background MCP calls from a mod and the permission check

Researched 2026-10-06 against Claude Code 2.1.289 (bundled plugin-authoring skill and its types) and the 2.1.290 binary at `~/.local/share/claude/versions/2.1.290`. Byte offsets below are into that binary. The API is early access, so re-check these points after an upgrade.

Labels used below:

- **[verified]**: read directly in a primary source (engine code, the shipped type declarations, or the official docs).
- **[inferred]**: reasoned from verified facts, but not observed directly.

## The question

The plugin is a mod made of function hooks: `doorbell`, at `plugins/doorbell`. Its timer callbacks (`$.clock.after` / `$.clock.every`), and async work that outlives the `session.start` hook that started it, call `$.mcp.call`. Can those calls be approved by the plugin's own permission hooks, so that the auto-mode classifier does not deny them, without the user adding `permissions.allow` rules? And does the harness have a sanctioned pattern for this?

## Short answer

**Not from inside the same plugin. Yes from a second plugin.**

- **Same plugin: no.** The engine skips every hook of a plugin for a `$` call that plugin's own code raised outside a live hook dispatch. A timer callback is outside any dispatch, so doorbell's `classic.PreToolUse` and `tool.check` hooks never see its background calls. This is deliberate re-entry protection, and the plugin has no way to opt out of it. **[verified]**
- **Second plugin: yes.** The skip applies only to modules with the *same plugin name* as the caller. A separate plugin, with its own hooks module, does see doorbell's background calls. It sees `next.origin = { plugin: 'doorbell', tier: 'user' }`, which the host sets and a plugin cannot forge. If that plugin's `tool.check` hook answers `{ decision: 'allow' }`, the call runs with no classifier check. The docs describe exactly this route: "A mod you install that handles `tool.check` can approve an action before step 3, and the classifier doesn't check an action the mod approves." **[verified]**
- **Best option:** ship a small companion plugin, for example `doorbell-grant`, in the same marketplace. Doorbell lists it under `dependencies`, so installing doorbell installs and enables it. Its one hook is a `tool.check` hook that allows exactly doorbell's own tool list when `next.origin.plugin === 'doorbell'`, and passes everything else to `next(e)`. Nothing goes into the user's settings. **[verified mechanism; the end-to-end run is not yet probed]**

The harness has no dedicated "background grant" event or noun. The `$.mcp.call` doc sentence "the plugin's call ... is the grant" does not mean what it seems to mean (see below).

## How the engine decides re-entry

### 1. The origin chain of a `$` call

When a plugin's environment calls `$`, the host builds the caller's `origin` (a chain of frames) from the dispatch the call claims to belong to. **[verified]**

Same-thread runtime, at offset ≈211920131:

```js
function pHt(e,n){let r=e??[],s=Nzt(n),g=typeof n==="string"?void 0:n.registration;
  return r.some((S)=>typeof S==="string"?S===s:S.plugin===s&&S.registration===g)?r:[...r,n]}
function nce(e,n,r){let s=e!==void 0&&r!==void 0;
  return pHt(e?.origin,s?{plugin:n,registration:r}:n)}
function oce({state:e},n,r){let{environmentId:s,dispatchId:g,registration:h,serving:S}=n, ...
  H=g===void 0?void 0:e.dispatches.get(g), W=e.names.get(s), ...
  return{plugin:W??`environment ${s}`, ..., origin:W===void 0?H?.origin??[]:nce(H,W,h), ...}}
```

The worker runtime does the same thing, in `A5t`/`Ffe` at offset ≈212456924. It uses `e.inFlight.get(dispatchId)`.

The two cases:

- **The call comes from a hook while its dispatch is still in flight.** Both `H` and the registration number are known, so the frame is `{ plugin: 'doorbell', registration: 11 }`.
- **The dispatch has settled, or no hook registration is attached.** This covers a timer callback, a continuation after the hook returned, and a Button press handler. The frame is the **bare string** `'doorbell'`. Dispatches are deleted from the map in a `finally` once they settle (`S.dispatches.delete(he.id)`, offset ≈212405500).

The `$.tool.call` path falls back the same way: `let H=n.origin??[w]` in `lj`, offset ≈212360207. `w` is the plugin's name.

### 2. Which modules are skipped

At offset ≈207831151:

```js
function so(e,r){let n=new Set;for(let i of e??[]){if(Nzt(i)!==r)continue;
  if(typeof i==="string")return"every";n.add(i.registration)}return[...n].sort(...)}
function Y(e,r,n){if(!n||n.length===0)return e;let i=so(n,e.name);
  if(i==="every"){t(`hooks module ${e.label} ${r} skipped: re-entry (the plugin's own code raised it; origin ${$zt(n)})`);return}
  let s=e.registrationsFor(r),m=i.filter((p)=>s.includes(p));if(m.length===0)return e;
  if(!e.hooks(r,m)){t(`hooks module ${e.label} ${r} skipped: re-entry (its own frame is being dispatched; origin ${$zt(n)})`);return}
  return t(`hooks module ${e.label} ${r}: hooks ${m.join(", ")} left out for re-entry (origin ${$zt(n)})`),{...e,leftOut:m,...}}
```

**[verified]** This code has three consequences:

- **Bare-string frame:** if the frame for this module's plugin is a bare string, the **whole module** is skipped for that event. That is the log line in the probe.
- **Frame with a registration:** only the calling registration is left out. The plugin's other hooks still run. That is the in-dispatch probe result ("tool.check nested in doorbell#11"), and it matches the type doc: "It runs through every hook but the calling one (the plugin's others see it)" (`types/claude-code.d.ts:2914`).
- **Other plugins:** a module with a **different name** matches no frame. `so()` returns `[]`, so `Y` returns the module unchanged, and **another plugin's hooks run normally**.

`next.origin`, the value hooks read, is the last frame turned into `{ plugin, tier }` (`fZ`, offset ≈207838300). The types say it is "Set by the host alone, from the environment the call came from (its own MessagePort) and that plugin's seat; nothing a plugin writes reaches it" (`types/claude-code.d.ts:6284-6293`). **[verified]**

### 3. What `$.mcp.call` actually does

At offset ≈212366936, `XYt` (`$.mcp.call`) resolves the tool and then calls `lj(...)`, which is the `$.tool.call` implementation. `lj` runs the call through `$B(be, Te, W.canUseTool, ke, ...)`, which is the normal tool pipeline with the full permission check. **[verified]**

The MCP tool's own `checkPermissions` returns `{ behavior: "passthrough", message: "MCPTool requires permission.", suggestions: [addRules ...] }`, whatever its annotations say (offset ≈237978600). That produces the "Permission suggestions ... addRules" line in the probe. **[verified]**

### 4. What "the plugin's call, seen by the hooks above it, is the grant" means

The type doc on `$.mcp.call` (`types/claude-code.d.ts:2598-2602`) says: *"No permission prompt: the plugin's call, seen by the hooks above it, is the grant."* The engine code does not support that reading. Every `$.mcp.call` goes through `canUseTool` (§3), and the official mods admin page lists `$.mcp.call` as *"Calls a tool on a connected MCP server, under the session's permission rules"* (https://code.claude.com/docs/en/plugins/mods/admin, `$.mcp.call` row of the API table). **[verified]**

The most plausible meaning, which matches the code: no extra *consent* step is required beyond the normal pipeline, and the hooks that may veto or approve the call are the ones "above" it, meaning every hook except the caller's own frame. **[inferred]** In practice "above" covers two things:

- **Other plugins, in any tier.** The order is `prepend`, `user`, `append`, `builtin`, `core`, outermost first (`TIERS`, `types/claude-code.d.ts:12042-12049`).
- **The plugin's other registrations,** but only while the call is nested in one of its live dispatches.

It does **not** mean the call skips the permission check. Treat the doc sentence as inaccurate for 2.1.289 and 2.1.290. **[verified by contradiction with the code and the docs]**

### 5. Related behaviour this explains

- **`$.prompt.submit` from a Button press handler is invisible to the plugin's own `prompt.submit` hook.** A press handler runs "in the plugin's own environment: the bottom of the ui.press" with no hook registration, so its frame is the bare name and the whole module is skipped. **[inferred from §1 and §2, consistent with the observation]**
- **`$.config.set` is not seen by the plugin's own hooks.** The types say so explicitly (`types/claude-code.d.ts:1897`), and the code passes `hookOrigin: r=[n]`, a bare name (offset ≈211925172). **[verified]**

## Ranked options

### 1. A companion plugin whose `tool.check` hook approves doorbell-origin calls (recommended)

**How it works.** Make a second plugin, for example `plugins/doorbell-grant/`, with its own `.claude-plugin/plugin.json` and `hooks/hooks.json`. A plugin has exactly one hooks module (reference.md "What a plugin of function hooks is"), so the hook has to live in a separate plugin. Its module:

```ts
const OWN = new Set(['list_agent_roles', /* ...doorbell's OWN_TOOLS... */])
export function register(on) {
  on('tool.check', async ($, e, next) => {
    const tool = typeof e.tool === 'string' && e.tool.startsWith('mcp__plugin_doorbell_doorbell__')
      ? e.tool.slice('mcp__plugin_doorbell_doorbell__'.length) : ''
    if (next.origin.plugin === 'doorbell' && OWN.has(tool)) return { decision: 'allow', reason: 'doorbell background poll' }
    return next(e)
  })
}
```

Then add `"dependencies": ["doorbell-grant"]` to doorbell's `plugin.json`, and add the new plugin to `.claude-plugin/marketplace.json`.

**Why it works:**

- The re-entry skip is keyed on plugin name (§2), so `doorbell-grant`'s hooks run for doorbell's timer calls. **[verified]**
- `tool.check` "Fires when the engine decides whether a tool call may run, after the `tool.call` and PreToolUse hooks and before the mode settles an ask ... return any `{ decision }`" (`types/claude-code.d.ts:3849-3859`). **[verified]**
- In auto mode: "A mod you install that handles `tool.check` can approve an action before step 3, and the classifier doesn't check an action the mod approves" (https://code.claude.com/docs/en/permission-modes, "How the classifier evaluates actions"). Also: "in auto mode, a call the mod approves runs without a classifier check" (https://code.claude.com/docs/en/permissions#extend-permissions-with-hooks). **[verified]**
- `next.origin.plugin` cannot be forged by a plugin (§2), and the model's own call to the same tool reads `{ plugin: 'engine', tier: 'core' }` (`types/claude-code.d.ts:12261-12262`). The model's calls therefore keep their normal permission handling. **[verified]**
- A `classic.PreToolUse` hook returning `{ allow: true }` in the companion should also work. The in-dispatch probe showed the PreToolUse allow became the `tool.check` verdict (`{"decision":"allow","hook":"PreToolUse"}`). `tool.check` is the documented mod route, so it is the better choice. **[inferred]**

**Does it avoid a user-side permission rule?** Yes. Nothing is written to the user's settings. The only extra user action is installing the dependency, and that happens automatically:

- "A plugin that an enabled plugin depends on starts enabled regardless" (https://code.claude.com/docs/en/plugins-reference#defaultenabled). **[verified]**
- `claude plugin install`, `/reload-plugins`, marketplace auto-update and `claude plugin marketplace add` "install any missing declared dependency" (https://code.claude.com/docs/en/plugins/dependencies). **[verified]**
- For local development, load both plugins with `--plugin-dir`, or point one `--plugin-dir` at the parent folder (v2.1.265 or later) (same page). **[verified]**

**Risks:**

- **Authority.** A user-tier mod that approves calls can override ask rules and non-managed PreToolUse blocks. Where there are no managed settings and no Team or Enterprise sign-in, it can even override deny rules: "Anywhere else, the mod can approve a call that a deny rule refuses" (https://code.claude.com/docs/en/permissions#extend-permissions-with-hooks). Keep the approval narrow: an exact tool list, `origin.plugin === 'doorbell'`, and never `mcp__*`. Consider honouring a core `deny`: call `await next(e)` first, and keep a `deny` that came from a settings rule (`rule` present). **[verified facts; the mitigation is a recommendation]**
- **Organisation policy.** `allowManagedModsOnly` or `allowManagedHooksOnly` stops both plugins from loading (https://code.claude.com/docs/en/plugins/mods/admin). In that case there is no polling at all, so there are also no denials. **[verified]**
- **Engine changes.** The re-entry rule is undocumented engine internals. It could change, and the API is early access. The `tool.check` mod approval is documented, which is the stable part.
- **Managed hooks.** A managed-settings PreToolUse block still holds over the mod: "unless the hook is in managed settings" (permissions doc). **[verified]**
- **Not yet probed end to end.** Repeat the earlier probe with both plugin dirs (`claude -p --permission-mode auto --plugin-dir doorbell --plugin-dir doorbell-grant --debug-file ...`). Expect the line `hooks module doorbell-grant@inline: tool.check nested in doorbell`, or no re-entry line for doorbell-grant, and a `tool.check` verdict of allow.

### 2. Run the MCP call only inside a live doorbell dispatch (partial)

**How it works.** A call made from a hook while that hook's dispatch is in flight leaves out only the calling registration, so doorbell's own `classic.PreToolUse` approves it. The probe showed this for `command.run`. **[verified]** The timer would set a flag ("poll due"), and the actual `$.mcp.call` would happen in the next engine-raised event doorbell hooks. Candidates are `turn.start` and `turn.complete`, `classic.UserPromptSubmit`/`Stop`, the doorbell commands, and `ui.press` hooks for its own Buttons.

**Does it avoid a user rule?** Yes, within one plugin.

**Risks:**

- **No polling when idle.** Nothing the engine raises fires on a schedule while the session is idle. That defeats a 15 s poll. **[verified: api.md, "The timer's callback runs outside any event"]**
- **Every hop counts.** A continuation that runs after the hook returned loses the frame (§1). The call must be awaited inside the hook. Its time does not count against the 10 s budget ("Time spent waiting on `next` or on a mods API call doesn't count", https://code.claude.com/docs/en/plugins/mods/api). **[verified]**
- **A press handler has no registration.** A Button's `onPress` closure does not count, but a `ui.press` *hook* (`on('ui.press', ...)`) does. **[inferred from §1]**
- **No self-triggering.** The plugin's own `$` calls (`$.state.set`, `$.ui.invalidate`, `$.prompt.submit`, `$.config.set`) cannot trigger its own hooks to get a frame: those dispatches carry the bare-name frame. Exception: an engine-raised `ui.render` of its own pane after an invalidate is raised by the engine, so it is not re-entry. But render hooks must not have side effects, and doing MCP work there is a hack. Not recommended. **[inferred]**

Use this as a complement to option 1, for example to refresh opportunistically on `turn.complete`. It does not replace option 1.

### 3. `$.tool.check` as a pre-flight (fallback that reduces noise; not a fix)

**How it works.** Before each background `$.mcp.call`, call `$.tool.check({ tool, input })`. The types say it "Asks the engine's permission decision ... nothing runs, no dialog opens, no PreToolUse hook or classifier is asked" (`types/claude-code.d.ts:2922-2932`). If the answer is not `allow`, skip the call and show a one-time `$.ui.status` hint, so the classifier is never sent an unapprovable call and no denial is recorded. **[verified for the API]** With option 1 installed, the companion's `tool.check` hook would answer `allow` here too, because the re-entry rule is name-based. **[inferred]**

**Does it avoid a user rule?** No. On its own, it only avoids classifier traffic and denial noise.

**Risk:** a query reports the rules and mode decision without the classifier, so in auto mode `ask` means the call "would go to the classifier". Treat anything other than `allow` as "do not call".

### 4. A user-side allow rule written with the person's consent (excluded by the question; for completeness)

`permissions.allow: ["mcp__plugin_doorbell_doorbell__*"]` would work. "Allow rules accept tool-name globs only after a literal `mcp__<server>__` prefix", and `mcp__<server>` matches every tool on that server (https://code.claude.com/docs/en/permissions). In auto mode, a matching allow rule resolves at step 1, before the classifier. **[verified]**

A plugin cannot ship this rule itself:

- The plugin `settings` key and `settings.json` take effect only for `agent` and `subagentStatusLine`; "other keys are dropped at load" (https://code.claude.com/docs/en/plugins-reference#settings). **[verified]**
- `$.settings` is read-only (`types/claude-code.d.ts:3455-3483`). **[verified]**
- `$.config.set` writes `/config` panel rows; permissions are not among them. **[inferred]**
- Writing `~/.claude/settings.json` through `$.fs.write` is technically possible, but it edits the user's settings, which the question rules out, and it goes around the protected-path design. Not recommended. **[inferred]**

### Ruled out

- **MCP `readOnlyHint` annotations.** For an MCP tool, `isReadOnly()` returns `annotations.readOnlyHint` (offset ≈237978340). The tool's `checkPermissions` still returns `passthrough` regardless (offset ≈237978600). The auto-mode "safe allowlist" (`Cmt`, offset ≈213301137) is a fixed set of tool names that never reads `isReadOnly`, and the docs' step 2 ("Read-only actions ... are auto-approved") names file reads and read-only shell commands. The annotation feeds `isReadOnly` in results and telemetry, and what the classifier transcript includes. It does not approve a call. **[verified in code for the allowlist and checkPermissions; overall conclusion inferred]**
- **`consent` on `$.tool.call`.** `consent` is "the person's own words for the press that raised the call" (`types/claude-code.d.ts:12118-12125`). It adds a human turn that the permission path reads as the user's request. `$.mcp.call` does not pass it. Making up consent for unattended polling would misrepresent the user to the classifier. Not applicable. **[verified]**
- **A sanctioned "background work" event or noun.** Neither the docs (reference.md "Work that outlives a dispatch", api.md "Run work in the background") nor the types describe a permission exemption for timer work. The timer callback "runs outside any event". **[verified]**
- **A second hooks module in the same plugin.** Each plugin has exactly one hooks module (`hooks/hooks.json` "names under `modules` (one path...)", reference.md line 13). Even if it had two, the re-entry match is by plugin *name*, so they would share the skip. **[verified / inferred]**
- **`next.to(e, tier)` tricks.** `next.to` only skips links toward *less* authority, it is available only on a hook's own `next` inside a dispatch, and "nothing skips to" `prepend` or `user` (`types/claude-code.d.ts:6251-6260`, `11759-11762`). It does not help a call made outside a dispatch. **[verified]**
- **A `classic.PermissionRequest` hook in doorbell.** It is dispatched through the same hook chain with the same origin, so doorbell's module would be skipped in the same way. It also answers prompts, and in auto mode the classifier decides before any prompt. **[inferred]**

## What I could not verify

- An end-to-end run of option 1 (two plugins, auto mode, a timer-driven call). The mechanism is verified in code; the run is not.
- Whether the companion's hook receives `tool.check` for the timer call *before* the auto-mode classifier in the exact 2.1.290 code path. The docs and the types say `tool.check` runs "before the mode settles an ask", and the probe log shows doorbell's `tool.check` dispatch being *skipped* (so it was dispatched) before the classifier line. **[strongly inferred]**
- The intended meaning of "is the grant" in the `$.mcp.call` doc. No primary source explains it, and it contradicts the code and the admin docs.
- Whether `$.config.set` can reach any permission-bearing row. There appears to be none, but I did not enumerate `$.config.list` in a live session.
- I found no public reports of this behaviour. A web search for the re-entry log text returned nothing relevant.

## Evidence quotes

Engine (2.1.290 binary), re-entry, offset ≈207831400:

> `hooks module ${e.label} ${r} skipped: re-entry (the plugin's own code raised it; origin ${$zt(n)})`
> `hooks module ${e.label} ${r} skipped: re-entry (its own frame is being dispatched; origin ...)`
> `hooks module ${e.label} ${r}: hooks ${m.join(", ")} left out for re-entry (origin ...)`

Engine, nesting log (offset ≈207830759): `` t(`hooks module ${R_t(e)}: ${r}${g} nested in ${$zt(i)}`) ``.

Engine, `$.mcp.call` → `$.tool.call` (offset ≈212366936): `` let W=await lj(Iys(w.name,r),s);if(W.deny!==void 0)throw new Oe(`${s.plugin}: $.mcp.call(${e}, ${n}) refused: ${W.deny}`) ``.

Types, `$.mcp.call` (`types/claude-code.d.ts:2600-2601`):

> A `cached` server is dialed on first use. No permission prompt: the plugin's call, seen by the hooks above it, is the grant.

Types, `$.tool.call` (`:2913-2916`):

> It runs through every hook but the calling one (the plugin's others see it), the permission check and its dialog, then the tool.

Types, `$.tool.check` (`:2926-2928`):

> The hooks run (the calling hook's own frame skipped, `next.origin` this plugin, no `tool_use_id`); nothing runs, no dialog opens, no PreToolUse hook or classifier is asked.

Types, `next.origin` (`:6284-6289`):

> Who raised this dispatch ... Set by the host alone, from the environment the call came from (its own MessagePort) and that plugin's seat; nothing a plugin writes reaches it. Every hook of one dispatch sees the same origin, and `next.to` keeps it.

Skill reference (`plugin-authoring/reference.md:126-134`, "Work that outlives a dispatch"):

> Work meant to outlive a dispatch belongs elsewhere: start it from a `session.start` hook ... and keep it going with `$.clock.every` and `$.clock.after`, whose timers run until cancelled or until the module reloads.

Docs, mods API (https://code.claude.com/docs/en/plugins/mods/api, "Run work in the background"):

> The timer's callback runs outside any event, so it keeps running between turns and doesn't start one.

Docs, mods admin (https://code.claude.com/docs/en/plugins/mods/admin):

> `$.mcp.call` | Calls a tool on a connected MCP server, under the session's permission rules

Docs, permission modes (https://code.claude.com/docs/en/permission-modes, "How the classifier evaluates actions"):

> A mod you install that handles `tool.check` can approve an action before step 3, and the classifier doesn't check an action the mod approves.

Docs, permissions (https://code.claude.com/docs/en/permissions#extend-permissions-with-hooks):

> **The auto mode classifier**: in auto mode, a call the mod approves runs without a classifier check

Docs, plugin manifest (https://code.claude.com/docs/en/plugins-reference):

> `settings` | Object | Settings Claude Code applies while the plugin is enabled. Only `agent` and `subagentStatusLine` take effect

> A plugin that an enabled plugin depends on starts enabled regardless.

The probe evidence (timer call) that started this research:

```
$.tool.call (doorbell): mcp__plugin_doorbell_doorbell__list_agent_roles (no input)
hooks module doorbell@inline tool.call skipped: re-entry (the plugin's own code raised it; origin doorbell)
hooks module doorbell@inline classic.PreToolUse skipped: re-entry (the plugin's own code raised it; origin doorbell)
hooks module doorbell@inline tool.check skipped: re-entry (the plugin's own code raised it; origin doorbell)
Auto mode classifier unavailable, denying with retry guidance (fail closed)
```

`origin doorbell` is printed by `$zt`, which renders a bare-string frame as just the name and a registration frame as `doorbell#N`. The bare name is the case §1 describes. **[verified]**
