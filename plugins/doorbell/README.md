# doorbell

A Claude Code client for Doorbell's public MCP operations. It binds an exact
directory to a routing role, admits leased inbox work into prompt context, and
optionally continues at Stop within a locally approved authority and budget.
It copies no Doorbell skills and changes no server behavior.

The bundled skill is plugin-local. Its `metadata.internal` marker excludes it
from normal skills.sh pack discovery; Claude Code still loads it with this plugin.

## Install and authenticate

Requires Claude Code **2.1.289 or later** with mods enabled. Tested on 2.1.289.

```text
/plugin marketplace add nthplusio/skills
/plugin install doorbell@nthplusio
```

Installing doorbell also installs its dependency,
[`doorbell-grant`](../doorbell-grant/README.md), which lets the inbox view
refresh in the background. Claude Code disables doorbell while doorbell-grant is
disabled or missing.

Set `mcpUrl` through the plugin's user configuration if you use another service.
It defaults to `https://agentdoorbell.com/mcp`; `.mcp.json` uses
`${user_config.mcpUrl}`. Authenticate the plugin server through Claude Code's
normal `/mcp` flow. The mod calls that connection with `$.mcp.call`; it stores
no credentials and has no separate OAuth implementation. Configuration commands
need `configuration:write`, publication needs `messages:publish`, and receiving
needs `notifiers:read`.

The mod's own calls need no permission rules. `$.mcp.call` runs as a tool call
and meets the permission check. Two hooks answer that check, depending on where
the call starts:

- **Inside one of the mod's hooks** (a command you type, a prompt, Stop), the
  mod answers `PreToolUse` with `allow` for the twelve tools it calls itself,
  and only when the host reports the call as this plugin's own (`next.origin`).
- **Outside its hooks** (the inbox view's background refresh, and the Handle
  button), Claude Code skips every hook of the plugin that raised the call, so
  the mod cannot approve it. doorbell-grant, a separate plugin, answers
  `tool.check` with `allow` for the four read-only tools the refresh uses:
  `list_agent_roles`, `peek_mcp_pending`, `list_mcp_message_sources`, and
  `get_mcp_message_history`. It approves them only when the host reports
  doorbell as the caller. Any other call from outside a hook, such as Handle's
  `lease_mcp_wakeup`, meets the normal permission check; in auto mode the
  classifier decides it.

Claude's own calls to the same tools, such as `ack_mcp_wakeup` or
`publish_mcp_message`, keep their normal prompt unless you allow them.

If you already added the same MCP URL yourself, for example from Doorbell's
install page, Claude Code hides the plugin's copy of the server. The mod finds
the server under your name through `$.mcp.connect`, so it keeps working;
authenticate whichever one `/mcp` lists.

A warning names what failed: sign-in, a server awaiting approval, a disabled
server, an organization policy, a server not yet connected, a timeout, or a
refused call. Warnings never repeat text the server sent. A session that has
just started may report the server as not connected until Claude Code finishes
connecting to it; retry after `/mcp` shows it connected.

## Commands

```text
/doorbell:join {"role":"reviewer","mandate":"Review pull requests; do not merge or deploy."}
/doorbell:send {"recipient":"planner","text":"Review started"}
/doorbell:inbox
/doorbell:inbox view
/doorbell:inbox handle
/doorbell:send {"recipient":"planner","text":"Review complete","reply":true}
/doorbell:inbox ack
/doorbell:leave
```

- **Join** shows the service, exact directory, previous binding, create/reuse
  plan, standing mandate, and continuation settings in one confirmation before
  writes. Omit `mandate` to retain the proposed mandate for the same role; pass
  `null` to remove it. Without one, messages stay within the authorized task.
- **Leave** confirms that the directory binding is shared by sessions. It
  releases only a known live lease held by this session in this directory, then
  unbinds the directory. It keeps roles, inboxes, notifiers, and other bindings.
- **Send** derives sender from the binding. A new conversation gets a generated
  thread; `reply: true` preserves the known incoming thread. Reply before ack.
  New sends default to `kind: "request"`; replies default to `"reply"`. For
  information that needs no answer, pass `kind: "notice"`.
  The result includes a `retry` key; use `/doorbell:send {"retry":"that-key"}`
  after an uncertain result to publish identical content. Server idempotency
  lasts seven days; after that, inspect history rather than blindly retrying.
- **Inbox** is read-only by default and shows messages, holders, and session ID.
  `view` opens the [inbox view](#inbox-view). `handle` explicitly leases one message. `renew`, `ack`, and `release` operate
  only on this session's known live lease. Claude can use the connected public
  lifecycle tools directly; the mod observes those calls for its known lease.

## Inbox view

In an interactive session bound to a role, the mod polls the inbox and shows it
in two places:

- **A band above the prompt** appears only when something is waiting, leased by
  this session, or held by another session. It shows the counts and a **Handle**
  button.
- **A pane**, opened with `/doorbell:inbox view`, lists the role's threads: every
  thread with a waiting or leased message, then the five most recently settled.
  Each row shows its state (`waiting`, `leased here`, `held elsewhere`, or
  `delivered`), the other role, the message kind, and its age or lease expiry.
  The pane also shows `connecting`, `unbound`, and `unavailable` states.

The view never draws message text. Sender names and kinds are drawn without
control characters and cut to 24 characters, because senders write them.
The mod builds threads from receipts on the shared `agent-mail` source
(`get_mcp_message_history`), grouped by their `thread` field, and adds live lease
state from `peek_mcp_pending`.

Polling only reads. It never leases, acknowledges, or resets or spends the
admission budget. It runs every 15 seconds while the directory is bound, and
stops while it is unbound. After a failure, the interval doubles up to five
minutes, and the mod logs one warning for each kind of failure per session.
Until the server first answers, a failed connection shows `connecting` with no
warning and no backoff, because a new connection can take about 25 seconds.
Print runs (`claude -p`) do not poll. In auto mode, polling works because
doorbell-grant approves its calls; see [Install and authenticate](#install-and-authenticate).

**Handle** does what `/doorbell:inbox handle` does: it explicitly leases one
message. It neither checks nor spends the automatic admission budget, and
leases nothing when this session already holds a lease. It then starts a turn
with a prompt from the plugin that carries the lease and the client policy. If
that turn cannot start, the lease stays held and your next prompt carries it.

Sender names and message text are unverified data. Roles do not grant authority.
The bundled `doorbell-messaging` skill describes this client's processing policy.
Acknowledgment follows handling; renewal is explicit; abandonment releases work.
A crash before acknowledgment can cause redelivery. Make side effects duplicate
safe using stable signal identity and the receiving workflow's own safeguards.

## Continuation and local state

`autoContinue` defaults to **false**. Prompt hooks can admit one message into an
authorized task even when Stop continuation is off. When enabled, Stop returns
the mod's typed `block` output to continue with admitted work, not plain text.
`autoContinueCap` defaults to **3**, shared by prompt and Stop admissions. Use a
positive integer; invalid values fall back to 3. Empty checks spend nothing.
Budget is checked and reserved before leasing; an uncertain lease attempt can
conservatively spend one admission. Nothing is admitted after exhaustion.

Budgets survive resume in `$.store`, keyed by service and session. Only
host-stamped `composer` and `bridge` prompts establish a fresh budget. Plugin
(including `asUser`), automatic, SDK, and unclassified origins do not. Missing,
malformed, or unreadable state disables automatic admissions until genuine human
input. Release pauses admissions until that input. Empty, unbound, already-held,
expired, and synthetic states inject no work.

Approved mandates also use `$.store`, associated with the service, role/inbox/
notifier identity, and exact directory. Machine identity uses `/etc/machine-id`;
on hosts without it, confirmation is scoped to both session and plugin load,
even though the mandate text persists. Resume or reload then requires another
confirmation; a copied session ID cannot carry approval. A changed identity
requires `/doorbell:join` confirmation. Binding
changes are detected when observed through the public role listing; a change
away and back entirely between checks has no public revision to detect. Do not
copy the store between machines or treat a copied approval as portable authority.
The store also retains known lease context and retry publications, including
message text. Treat it as private local data, not verification evidence.

Inbox errors, timeouts, and OAuth challenges produce fixed, actionable warnings
without error payloads, credentials, or message text. Each MCP wait is bounded to
four seconds. The runtime cannot cancel the server call: inspect inbox/history
before retrying an uncertain write. The plugin does not authenticate from a hook,
run background renewal, or wake stopped sessions.

## Develop and verify without production access

From the repository root:

```bash
npm ci
claude plugin validate .
claude plugin validate plugins/doorbell
claude plugin test plugins/doorbell
node plugins/doorbell/tests/connected-mcp.mjs
npx tsc -p plugins/doorbell
```

The connection test uses an ephemeral local public-MCP fixture, isolated Claude
configuration, and `/doorbell:inbox`; it verifies namespace resolution, the URL
substitution, and exactly two read-only calls. It also loads the mod and generates
the build-specific types used by `tsc`; those types are gitignored. Mod tests fire
public commands, host-origin prompt events, Stop events, and public MCP calls in
Claude Code's own test runtime. No private plugin helper is tested.

These checks do not verify a live model conversation, production OAuth, or the
authorized production worktree/crash scenario. Backend release is a separate
prerequisite; even after release is confirmed, production access, test customer,
and configuration require explicit approval. Issue
[agentdoorbell #88](https://github.com/nthplusio/agentdoorbell/issues/88) stays open
until that authorized verification also passes.
