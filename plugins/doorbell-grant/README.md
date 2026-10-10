# doorbell-grant

Approves the [doorbell](../doorbell/README.md) plugin's own read-only inbox
calls at Claude Code's permission check, so doorbell's inbox view can refresh
in the background, including in auto mode. Installing doorbell installs this
plugin; you don't install it yourself.

## Why it is a separate plugin

Doorbell's inbox view refreshes from a timer, and every refresh is an MCP tool
call that meets the permission check. When a plugin raises a call outside one
of its own running hooks, Claude Code skips every hook of that plugin for the
call. So doorbell cannot approve its own background calls, and in auto mode the
classifier denies them.

Another plugin's hooks still run for that call, and the host tells them which
plugin raised it (`next.origin`). That is the only part doorbell-grant relies
on. A plugin cannot set its own origin.

## What it approves

One `tool.check` hook answers `allow` when all of these hold:

- The host reports doorbell as the caller.
- The tool is one of doorbell's four read-only inbox tools, under any MCP server
  name: `list_agent_roles`, `peek_mcp_pending`, `list_mcp_message_sources`, or
  `get_mcp_message_history`.
- The normal check did not deny it.

Every other call goes to the normal permission check unchanged. That includes
doorbell's writes (leases, acknowledgments, publishing, binding), any other
plugin's calls, and Claude's own calls.

An approval from a plugin's `tool.check` hook settles the check before your
permission mode is asked, so these four calls run without a prompt or a
classifier decision. The hook asks the normal check first and keeps any `deny`
it returns, so a deny rule for these tools, yours or your organization's, still
blocks them. It only turns a would-be prompt into an approval. Managed settings
can also stop the plugin from loading.

## Verify

```bash
npm run test:doorbell-grant
```

The tests load stand-in plugins named `doorbell` and `other` that ask the
permission check about a tool, and check the verdicts.

The script's `tsc` step needs the API types Claude Code writes into
`.claude-plugin/types/` when it loads the plugin, and `claude plugin test`
does not write them. In a fresh checkout, run `npm run test:plugins`: doorbell's
connected check loads both plugins before this script runs.
