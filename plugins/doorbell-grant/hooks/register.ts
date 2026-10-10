import type { Register } from 'claude-code'

// Doorbell refreshes its inbox from a timer. A call a plugin raises outside a
// live dispatch skips every hook of that plugin, so doorbell cannot approve its
// own background calls, and auto mode's classifier denies them. Another
// plugin's hooks still run for that call, with next.origin set by the host.
// This plugin approves only doorbell's read-only inbox tools, only when
// doorbell raised the call, and never over a deny; every other call goes
// to the normal check.
const DOORBELL = 'doorbell'
const READ_ONLY_TOOLS = new Set(['list_agent_roles', 'peek_mcp_pending', 'list_mcp_message_sources', 'get_mcp_message_history'])

export const register: Register = on => {
  on('tool.check', async ($, e, next) => {
    // Any server name: Doorbell may run under a name other than the plugin's.
    const tool = e.tool.startsWith('mcp__') ? e.tool.slice(e.tool.lastIndexOf('__') + 2) : ''
    // Not caught: a failure in the normal check must reach the caller unchanged.
    if (next.origin.plugin !== DOORBELL || !READ_ONLY_TOOLS.has(tool)) return next(e)
    // The verdict beneath comes before the mode settles an ask, so the
    // classifier is not consulted here. A deny, such as your own rule, wins.
    const verdict = await next(e)
    return verdict.decision === 'deny' ? verdict : { decision: 'allow', reason: 'doorbell-grant: the doorbell plugin reading its own inbox' }
  })
}
