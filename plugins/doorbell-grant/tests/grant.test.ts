import type { Plugin } from 'claude-code/testing'
import { expect, test } from 'claude-code/testing'

// Stand-ins that ask the permission check about a tool, as the named plugin.
// The host stamps next.origin from the caller, so the grant sees their names.
const doorbell: Plugin = {
  name: 'doorbell',
  register(on) {
    on('command.run', { command: 'ask' }, async ($, e) => ({ text: JSON.stringify(await $.tool.check({ tool: e.args, input: {} })) }))
  },
}
const other: Plugin = {
  name: 'other',
  register(on) {
    on('command.run', { command: 'ask' }, async ($, e) => ({ text: JSON.stringify(await $.tool.check({ tool: e.args, input: {} })) }))
  },
}

const READ_ONLY = ['list_agent_roles', 'peek_mcp_pending', 'list_mcp_message_sources', 'get_mcp_message_history']
const ask = (tool: string) => ({ command: 'ask', args: tool, origin: { kind: 'composer' } as const, presentation: { isFullscreen: false, columns: 80 } })
const verdict = (run: { text?: string }) => JSON.parse(run.text ?? 'null')

test('allows each read-only Doorbell tool that doorbell asks about, under any server name', { plugins: [doorbell] }, async ($, on) => {
  on('tool.check', () => ({ decision: 'ask' as const, reason: 'the engine would ask' }))
  for (const server of ['plugin_doorbell_doorbell', 'agent-doorbell']) {
    for (const tool of READ_ONLY) {
      expect(verdict(await $.command.run(ask(`mcp__${server}__${tool}`)))).toMatchObject({ decision: 'allow' })
    }
  }
})

test('passes doorbell\'s writes and every other tool to the normal check', { plugins: [doorbell] }, async ($, on) => {
  on('tool.check', () => ({ decision: 'ask' as const, reason: 'the engine would ask' }))
  const tools = [
    'mcp__plugin_doorbell_doorbell__lease_mcp_wakeup', 'mcp__plugin_doorbell_doorbell__ack_mcp_wakeup',
    'mcp__plugin_doorbell_doorbell__publish_mcp_message', 'mcp__plugin_doorbell_doorbell__bind_agent_role',
    'mcp__plugin_doorbell_doorbell__list_agent_roles_and_more', 'list_agent_roles', 'Bash',
  ]
  for (const tool of tools) {
    expect(verdict(await $.command.run(ask(tool)))).toEqual({ decision: 'ask', reason: 'the engine would ask' })
  }
})

test('passes the same read-only tools to the normal check when another plugin asks', { plugins: [other] }, async ($, on) => {
  on('tool.check', () => ({ decision: 'ask' as const, reason: 'the engine would ask' }))
  for (const tool of READ_ONLY) {
    expect(verdict(await $.command.run(ask(`mcp__plugin_doorbell_doorbell__${tool}`)))).toEqual({ decision: 'ask', reason: 'the engine would ask' })
  }
})

test('a test\'s own check, which no plugin raised, is not approved', async ($, on) => {
  on('tool.check', () => ({ decision: 'ask' as const, reason: 'the engine would ask' }))
  expect(await $.tool.check({ tool: 'mcp__plugin_doorbell_doorbell__list_agent_roles', input: {} })).toEqual({ decision: 'ask', reason: 'the engine would ask' })
})

test('a deny from the normal check still wins over the grant', { plugins: [doorbell] }, async ($, on) => {
  on('tool.check', () => ({ decision: 'deny' as const, reason: 'denied by your rule', rule: 'mcp__plugin_doorbell_doorbell__peek_mcp_pending' }))
  expect(verdict(await $.command.run(ask('mcp__plugin_doorbell_doorbell__peek_mcp_pending')))).toMatchObject({ decision: 'deny', reason: 'denied by your rule' })
})
