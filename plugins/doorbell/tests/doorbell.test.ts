import type { On, PromptOrigin } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

const cmd = (name: string, args = '') => ({ command: `doorbell:${name}`, args, origin: { kind: 'composer' } as const, presentation: { isFullscreen: false, columns: 80 } })
const prompt = (origin: PromptOrigin = { kind: 'composer' }) => ({ text: 'Continue my approved review', wait: false, origin })
// These are public MCP wire fixtures, not plugin internals.
const ROLE = { name: 'reviewer', inboxId: 'inbox-r', notifierId: 'notifier-r', active: true, pendingDepth: 2, bindings: ['/work/repo'] }
const item = (id: string, extra = {}) => ({
  signalId: id, synthetic: false, expired: false,
  wakeup: { signalId: id, synthetic: false, body: { events: [{ data: {
    text: `Review ${id}`, fields: { recipient: 'reviewer', sender: 'planner', thread: 'incoming-thread', kind: 'request' },
  } }] } }, ...extra,
})

function connection(on: On) {
  const calls: { tool: string; args: Record<string, unknown> }[] = []
  const warnings: string[] = []
  const questions: string[] = []
  const saved = new Map<string, unknown>()
  const state = { roles: [{ ...ROLE, bindings: [...ROLE.bindings] }], items: [item('signal-1')], error: '', answer: 'Approve', machine: 'machine-a', session: 'session-a', readError: false, hang: false, paginate: false, connect: { isConnected: true, server: 'plugin:doorbell:doorbell' } as { isConnected: true; server: string } | { isConnected: false; reason: 'unlisted' | 'unapproved' | 'disabled' | 'policy' | 'auth' | 'failed'; message: string }, servers: [] as string[], hangConnect: false }
  const clock = mock.clock(on, { now: Date.parse('2026-10-04T12:00:00Z') })
  let reached: () => void
  const started = new Promise<void>(resolve => { reached = resolve })
  on('session.cwd', () => ({ value: '/work/repo' }))
  on('session.id', () => ({ value: state.session }))
  on('fs.read', () => ({ value: state.machine }))
  on('store.get', ($, e) => state.readError ? { deny: 'unreadable local store' } : { value: saved.get(e.key) })
  on('store.set', ($, e) => { saved.set(e.key, e.value); return { value: undefined } })
  on('store.delete', ($, e) => { saved.delete(e.key); return { value: undefined } })
  on('ui.log', ($, e) => { warnings.push(e.text); return { value: undefined } })
  on('tool.call', ($, e) => {
    if (e.tool !== 'AskUserQuestion') return { result: { content: [{ type: 'text', text: JSON.stringify({ leaseId: 'lease-signal-1', expiresAt: '2026-10-04T12:45:00Z' }) }], isError: false } }
    questions.push(e.questions[0]!.question)
    return { result: { answers: { [e.questions[0]!.question]: state.answer } } }
  })
  on('prompt.submit', ($, e) => ({ text: e.text, context: e.context, origin: e.origin }))
  on('classic.Stop', () => ({}))
  on('classic.SessionStart', () => ({}))
  on('mcp.connect', ($, e) => {
    if (state.hangConnect) { reached(); return new Promise(() => {}) }
    return e.server === 'doorbell' ? { value: state.connect } : { value: { isConnected: false as const, reason: 'unlisted' as const, message: 'not in this manifest' } }
  })
  on('mcp.call', ($, e) => {
    state.servers.push(e.server)
    calls.push({ tool: e.tool, args: e.args ?? {} })
    reached()
    if (state.hang) return new Promise(() => {})
    if (state.error) return { value: { content: [{ type: 'text', text: state.error }], isError: true } }
    if (e.tool === 'lease_mcp_wakeup') {
      const pending = state.items.find(i => i.signalId === e.args?.signalId)!
      if (!pending) return { value: { content: [], isError: true } }
      const lease = { ...pending, leaseId: `lease-${pending.signalId}`, destinationId: 'inbox-r', holder: state.session, expiresAt: new Date(clock.now() + 15 * 60 * 1000).toISOString() }
      state.items = state.items.filter(i => i !== pending)
      return { value: { content: [{ type: 'text', text: JSON.stringify(lease) }], isError: false } }
    }
    const result = e.tool === 'list_agent_roles' ? { roles: state.roles }
      : e.tool === 'peek_mcp_pending' ? { destinationId: 'inbox-r', items: state.paginate ? state.items.slice(Number(e.args?.cursor ?? 0), Number(e.args?.cursor ?? 0) + 2) : state.items, ...(state.paginate && !e.args?.cursor && state.items.length > 2 ? { nextCursor: '2' } : {}) }
      : e.tool === 'create_agent_role' ? { created: false, role: state.roles[0] }
      : e.tool === 'list_mcp_message_sources' ? [{ id: 'mail-source', name: 'agent-mail' }]
      : e.tool === 'publish_mcp_message' ? { receiptId: 'receipt-1', routingOutcome: 'routed', duplicate: false }
      : e.tool === 'renew_mcp_wakeup_lease' ? { leaseId: e.args?.leaseId, expiresAt: '2026-10-04T12:45:00Z' }
      : {}
    return { value: { content: [{ type: 'text', text: JSON.stringify(result) }], isError: false } }
  })
  return { calls, warnings, questions, saved, state, started, clock }
}

test('/doorbell:inbox shows available and held work without consuming it', async ($, on) => {
  const f = connection(on)
  f.state.items.push(item('signal-2', { lease: { holder: 'someone-else', expiresAt: '2026-10-04T12:15:00Z' } }))
  const r = await $.command.run(cmd('inbox'))
  expect(r.text).toContain('signal-1')
  expect(r.text).toContain('someone-else')
  expect(f.calls).toEqual([
    { tool: 'list_agent_roles', args: {} },
    { tool: 'peek_mcp_pending', args: { destinationId: 'inbox-r', includeLeased: true } },
  ])
})

test('one prompt and two Stops exhaust cap 3; resume and non-human prompts cannot reset it', { options: { autoContinue: true } }, async ($, on) => {
  const f = connection(on)
  f.state.items = ['one', 'two', 'three', 'four'].map(id => item(id))
  expect((await $.prompt.submit(prompt())).context?.[0]).toContain('one')
  await $.command.run(cmd('inbox', 'ack'))
  expect((await $.classic.Stop({ stop_hook_active: false })).block).toContain('two')
  await $.command.run(cmd('inbox', 'ack'))
  expect((await $.classic.Stop({ stop_hook_active: true })).block).toContain('three')
  await $.command.run(cmd('inbox', 'ack'))
  await $.classic.SessionStart({ source: 'resume' })
  for (const origin of [{ kind: 'plugin', name: 'other', asUser: true }, { kind: 'auto-continuation' }, { kind: 'unclassified' }, { kind: 'sdk' }] as const) {
    expect((await $.prompt.submit(prompt(origin))).context).toBeUndefined()
    expect((await $.classic.Stop({ stop_hook_active: true })).block).toBeUndefined()
  }
  expect(f.calls.filter(c => c.tool === 'lease_mcp_wakeup').map(c => c.args.signalId)).toEqual(['one', 'two', 'three'])
  expect((await $.prompt.submit(prompt({ kind: 'bridge' }))).context?.[0]).toContain('four')
})

test('/doorbell:join confirms the complete plan once, persists a local mandate, and requires confirmation on another machine or changed inbox', async ($, on) => {
  const f = connection(on)
  const args = JSON.stringify({ role: 'reviewer', mandate: 'Review pull requests only; do not merge.' })
  expect((await $.command.run(cmd('join', args))).text).toContain('reviewer')
  expect(f.questions.length).toBe(1)
  expect(f.questions[0]).toContain('/work/repo')
  expect(f.questions[0]).toContain('Review pull requests only; do not merge.')
  expect(f.questions[0]).toContain('recipient, sender, thread, kind')
  expect(f.questions[0]).toContain('recipient equals "reviewer"')
  expect(f.questions[0]).toContain('consume the synthetic test wakeup')
  expect(f.questions[0]).toContain('activate the notifier')
  expect(f.calls.filter(c => c.tool !== 'list_agent_roles')).toEqual([
    { tool: 'create_agent_role', args: { name: 'reviewer', approved: true } },
    { tool: 'bind_agent_role', args: { role: 'reviewer', cwd: '/work/repo' } },
  ])
  f.state.session = 'session-b'
  expect((await $.prompt.submit(prompt())).context?.[0]).toContain('Review pull requests only; do not merge.')
  await $.command.run(cmd('inbox', 'ack'))
  f.state.machine = 'machine-b'
  f.state.items = [item('different-machine')]
  expect((await $.prompt.submit(prompt())).context).toBeUndefined()
  await $.command.run(cmd('join', args))
  expect((await $.prompt.submit(prompt())).context?.[0]).toContain('different-machine')
  await $.command.run(cmd('inbox', 'ack'))
  f.state.roles[0]!.inboxId = 'replacement-inbox'
  f.state.items = [item('binding-changed')]
  expect((await $.prompt.submit(prompt())).context).toBeUndefined()
  expect(f.questions.length).toBe(2)
})

test('declining /doorbell:join makes no configuration writes', async ($, on) => {
  const f = connection(on)
  f.state.answer = 'Cancel'
  await $.command.run(cmd('join', '{"role":"reviewer"}'))
  expect(f.calls.map(c => c.tool)).toEqual(['list_agent_roles'])
})

test('/doorbell:leave confirms shared-directory removal and abandons only this session lease; release pauses Stop', { options: { autoContinue: true } }, async ($, on) => {
  const f = connection(on)
  await $.prompt.submit(prompt())
  f.state.items = [item('another-session', { lease: { holder: 'session-b', expiresAt: '2026-10-04T12:15:00Z' } })]
  const start = f.calls.length
  await $.command.run(cmd('leave'))
  expect(f.questions[0]).toContain('shared')
  expect(f.calls.slice(start)).toEqual([
    { tool: 'release_mcp_wakeup', args: { leaseId: 'lease-signal-1' } },
    { tool: 'unbind_agent_role', args: { cwd: '/work/repo' } },
  ])
  f.state.items = [item('released-message')]
  expect((await $.classic.Stop({ stop_hook_active: false })).block).toBeUndefined()
  expect(f.calls.filter(c => c.tool === 'lease_mcp_wakeup').length).toBe(1)
  await $.prompt.submit(prompt())
  expect(f.calls.filter(c => c.tool === 'lease_mcp_wakeup').length).toBe(2)
})

test('/doorbell:leave with no known lease only unbinds the exact directory', async ($, on) => {
  const f = connection(on)
  await $.command.run(cmd('leave'))
  expect(f.calls).toEqual([{ tool: 'unbind_agent_role', args: { cwd: '/work/repo' } }])
})

test('/doorbell:send derives sender, generates a thread, preserves a reply thread, and retries identical publication', async ($, on) => {
  const f = connection(on)
  const first = await $.command.run(cmd('send', '{"recipient":"planner","text":"Review started"}'))
  const receipt = JSON.parse(first.text!)
  const publication = f.calls.find(c => c.tool === 'publish_mcp_message')!.args
  expect(publication).toMatchObject({ sourceId: 'mail-source', text: 'Review started', fields: { recipient: 'planner', sender: 'reviewer', kind: 'request' } })
  expect((publication.fields as Record<string, string>).thread).toMatch(/^[a-f0-9-]{36}$/)
  expect(publication.idempotencyKey).toMatch(/^[a-f0-9-]{36}$/)
  await $.command.run(cmd('send', JSON.stringify({ retry: receipt.retry })))
  expect(f.calls.filter(c => c.tool === 'publish_mcp_message').map(c => c.args)).toEqual([publication, publication])
  await $.command.run(cmd('inbox', 'handle'))
  await $.command.run(cmd('send', '{"recipient":"planner","text":"Review complete","reply":true}'))
  expect(f.calls.filter(c => c.tool === 'publish_mcp_message')[2]!.args.fields).toEqual({ recipient: 'planner', sender: 'reviewer', thread: 'incoming-thread', kind: 'reply' })
  await $.command.run(cmd('send', '{"recipient":"planner","text":"No answer needed","kind":"notice"}'))
  expect(f.calls.filter(c => c.tool === 'publish_mcp_message')[3]!.args.fields).toMatchObject({ kind: 'notice' })
  f.state.roles = []
  await $.command.run(cmd('send', '{"recipient":"planner","text":"Unbound"}'))
  expect(f.calls.filter(c => c.tool === 'publish_mcp_message').length).toBe(4)
})

test('default-off Stop does not poll or lease after prompt handling', async ($, on) => {
  const f = connection(on)
  await $.prompt.submit(prompt())
  await $.command.run(cmd('inbox', 'ack'))
  f.state.items = [item('waiting')]
  const before = f.calls.length
  expect(await $.classic.Stop({ stop_hook_active: false })).toEqual({})
  expect(f.calls.length).toBe(before)
})

test('empty checks spend no budget, even on resume; three later admissions remain', { options: { autoContinue: true } }, async ($, on) => {
  const f = connection(on)
  f.state.items = []
  expect((await $.prompt.submit(prompt())).context).toBeUndefined()
  for (let i = 0; i < 5; i++) expect(await $.classic.Stop({ stop_hook_active: true })).toEqual({})
  await $.classic.SessionStart({ source: 'resume' })
  f.state.items = ['a', 'b', 'c', 'd'].map(id => item(id))
  for (const id of ['a', 'b', 'c']) {
    expect((await $.classic.Stop({ stop_hook_active: true })).block).toContain(`Review ${id}`)
    await $.command.run(cmd('inbox', 'ack'))
  }
  expect(await $.classic.Stop({ stop_hook_active: true })).toEqual({})
  expect(f.calls.filter(c => c.tool === 'lease_mcp_wakeup').length).toBe(3)
})

for (const scenario of ['unbound', 'empty', 'held', 'synthetic', 'expired'] as const) {
  test(`${scenario} inbox state injects nothing and leases nothing`, { options: { autoContinue: true } }, async ($, on) => {
    const f = connection(on)
    if (scenario === 'unbound') f.state.roles = []
    if (scenario === 'empty') f.state.items = []
    if (scenario === 'held') f.state.items = [item('held', { lease: { holder: 'session-a', expiresAt: '2026-10-04T12:15:00Z' } }), item('available')]
    if (scenario === 'synthetic') f.state.items = [item('connectivity', { synthetic: true })]
    if (scenario === 'expired') f.state.items = [item('old', { expired: true })]
    expect((await $.prompt.submit(prompt())).context).toBeUndefined()
    expect(await $.classic.Stop({ stop_hook_active: false })).toEqual({})
    expect(f.calls.filter(c => /lease_mcp|ack_mcp|publish/.test(c.tool))).toEqual([])
  })
}

test('an unreadable budget allows ordinary work but cannot auto-admit until a fresh human prompt', { options: { autoContinue: true } }, async ($, on) => {
  const f = connection(on)
  f.state.readError = true
  const r = await $.prompt.submit(prompt({ kind: 'unclassified' }))
  expect(r.text).toBe('Continue my approved review')
  expect(r.context).toBeUndefined()
  expect(await $.classic.Stop({ stop_hook_active: false })).toEqual({})
  f.state.readError = false
  expect(await $.classic.Stop({ stop_hook_active: false })).toEqual({})
  expect(f.calls).toEqual([])
  expect((await $.prompt.submit(prompt())).context?.[0]).toContain('Review signal-1')
})

for (const error of ['inbox unavailable PRIVATE_TEXT bearer SECRET', 'OAuth challenge PRIVATE_TEXT token SECRET']) {
  test('MCP failure allows ordinary work and Stop, with content-free actionable warnings', { options: { autoContinue: true } }, async ($, on) => {
    const f = connection(on)
    f.state.error = error
    expect((await $.prompt.submit(prompt())).text).toBe('Continue my approved review')
    expect(await $.classic.Stop({ stop_hook_active: false })).toEqual({})
    expect(f.warnings.length).toBe(2)
    expect(f.warnings.join(' ')).toContain('/mcp')
    expect(f.warnings.join(' ')).not.toContain('PRIVATE_TEXT')
    expect(f.warnings.join(' ')).not.toContain('SECRET')
  })
}

test('an MCP timeout allows ordinary prompt work with no continuation', { options: { autoContinue: true } }, async ($, on) => {
  const f = connection(on)
  f.state.hang = true
  const pending = $.prompt.submit(prompt())
  await f.started
  await f.clock.advance(4001)
  const r = await pending
  expect(r.text).toBe('Continue my approved review')
  expect(r.context).toBeUndefined()
  expect(f.warnings.join(' ')).toContain('/mcp')
})

test('renewal is explicit, extends the known lease, and release pauses until human input', { options: { autoContinue: true } }, async ($, on) => {
  const f = connection(on)
  await $.prompt.submit(prompt())
  await f.clock.advance(5000)
  expect(f.calls.filter(c => c.tool === 'renew_mcp_wakeup_lease')).toEqual([])
  await $.command.run(cmd('inbox', 'renew'))
  await f.clock.advance(20 * 60 * 1000)
  await $.command.run(cmd('inbox', 'release'))
  expect(f.calls.filter(c => /renew_mcp|release_mcp/.test(c.tool))).toEqual([
    { tool: 'renew_mcp_wakeup_lease', args: { leaseId: 'lease-signal-1' } },
    { tool: 'release_mcp_wakeup', args: { leaseId: 'lease-signal-1' } },
  ])
  f.state.items = [item('signal-1')]
  expect(await $.classic.Stop({ stop_hook_active: true })).toEqual({})
  expect((await $.prompt.submit(prompt({ kind: 'plugin', name: 'other' }))).context).toBeUndefined()
  expect((await $.prompt.submit(prompt())).context?.[0]).toContain('signal-1')
})

test('public MCP renewal and release update this client policy; another lease does not', { options: { autoContinue: true } }, async ($, on) => {
  const f = connection(on)
  await $.prompt.submit(prompt())
  await $.tool.call({ tool: 'mcp__plugin_doorbell_doorbell__renew_mcp_wakeup_lease', leaseId: 'lease-signal-1' })
  await f.clock.advance(20 * 60 * 1000)
  f.state.items = [item('available')]
  await $.tool.call({ tool: 'mcp__plugin_doorbell_doorbell__release_mcp_wakeup', leaseId: 'someone-elses-lease' })
  expect(await $.classic.Stop({ stop_hook_active: false })).toEqual({})
  await $.tool.call({ tool: 'mcp__plugin_doorbell_doorbell__release_mcp_wakeup', leaseId: 'lease-signal-1' })
  expect(await $.classic.Stop({ stop_hook_active: false })).toEqual({})
  expect(f.calls.filter(c => c.tool === 'lease_mcp_wakeup').length).toBe(1)
  expect((await $.prompt.submit(prompt())).context?.[0]).toContain('available')
})

test('a transient budget read failure poisons a previously valid budget until human input', { options: { autoContinue: true } }, async ($, on) => {
  const f = connection(on)
  f.state.items = []
  await $.prompt.submit(prompt())
  f.state.readError = true
  expect(await $.classic.Stop({ stop_hook_active: false })).toEqual({})
  f.state.readError = false
  f.state.items = [item('after-recovery')]
  expect(await $.classic.Stop({ stop_hook_active: false })).toEqual({})
  expect((await $.prompt.submit(prompt())).context?.[0]).toContain('after-recovery')
})

test('a live lease on a later public peek page prevents admission; synthetic pages do not hide real work', async ($, on) => {
  const f = connection(on)
  f.state.paginate = true
  f.state.items = [item('available'), item('test', { synthetic: true }), item('held-later', { lease: { holder: 'session-a', expiresAt: '2026-10-04T12:15:00Z' } })]
  expect((await $.prompt.submit(prompt())).context).toBeUndefined()
  expect(f.calls.filter(c => c.tool === 'lease_mcp_wakeup')).toEqual([])
  f.state.items = [item('test-1', { synthetic: true }), item('test-2', { synthetic: true }), item('real-later')]
  expect((await $.prompt.submit(prompt())).context?.[0]).toContain('real-later')
})

test('overlapping explicit handling commands cannot lease twice for one session', async ($, on) => {
  const f = connection(on)
  const results = await Promise.all([$.command.run(cmd('inbox', 'handle')), $.command.run(cmd('inbox', 'handle'))])
  expect(results.filter(r => r.context?.length).length).toBe(1)
  expect(f.calls.filter(c => c.tool === 'lease_mcp_wakeup').length).toBe(1)
})

test('read-only inbox reports the session lease and budget without changing either', async ($, on) => {
  const f = connection(on)
  await $.prompt.submit(prompt())
  const before = f.calls.length
  const r = JSON.parse((await $.command.run(cmd('inbox'))).text!)
  expect(r.status).toMatchObject({ knownLeaseId: 'lease-signal-1', budget: { count: 1, paused: false } })
  expect(f.calls.slice(before).map(c => c.tool)).toEqual(['list_agent_roles', 'peek_mcp_pending'])
  await $.command.run(cmd('inbox', 'release'))
  const released = JSON.parse((await $.command.run(cmd('inbox'))).text!)
  expect(released.status).toMatchObject({ knownLeaseId: null, budget: { count: 1, paused: true } })
})

test('an observed unbinding invalidates standing authority even if the old binding returns', async ($, on) => {
  const f = connection(on)
  await $.command.run(cmd('join', '{"role":"reviewer","mandate":"Review only; do not merge."}'))
  f.state.roles[0]!.bindings = []
  await $.command.run(cmd('inbox'))
  f.state.roles[0]!.bindings = ['/work/repo']
  expect((await $.prompt.submit(prompt())).context).toBeUndefined()
  expect(f.calls.filter(c => c.tool === 'lease_mcp_wakeup')).toEqual([])
  await $.command.run(cmd('join', '{"role":"reviewer"}'))
  expect(f.questions.length).toBe(2)
  expect(f.questions[1]).toContain('Review only; do not merge.')
  expect((await $.prompt.submit(prompt())).context?.[0]).toContain('Review only; do not merge.')
})

test('join shows the effective cap when an invalid setting falls back to 3', { options: { autoContinue: true, autoContinueCap: 0 } }, async ($, on) => {
  const f = connection(on)
  await $.command.run(cmd('join', '{"role":"reviewer"}'))
  expect(f.questions[0]).toContain('Automatic Stop continuation: true; cap: 3.')
  f.state.items = ['first', 'second', 'third', 'fourth'].map(id => item(id))
  await $.prompt.submit(prompt())
  await $.command.run(cmd('inbox', 'ack'))
  for (const id of ['second', 'third']) {
    expect((await $.classic.Stop({ stop_hook_active: true })).block).toContain(`Review ${id}`)
    await $.command.run(cmd('inbox', 'ack'))
  }
  expect(await $.classic.Stop({ stop_hook_active: true })).toEqual({})
  expect(f.calls.filter(c => c.tool === 'lease_mcp_wakeup').map(c => c.args.signalId)).toEqual(['first', 'second', 'third'])
})

const refusals = [
  ['auth', 'needs sign-in'],
  ['unapproved', 'waiting for approval'],
  ['disabled', 'is disabled'],
  ['policy', 'policy blocks'],
  ['failed', 'not connected'],
] as const
for (const [reason, says] of refusals) {
  test(`a server that cannot connect (${reason}) says why, calls nothing, and writes no configuration`, { options: { autoContinue: true } }, async ($, on) => {
    const f = connection(on)
    f.state.connect = { isConnected: false, reason, message: 'PRIVATE_TEXT from the host' }
    const join = await $.command.run(cmd('join', JSON.stringify({ role: 'reviewer', mandate: null })))
    expect(join.text).toContain(says)
    expect(join.text).not.toContain('PRIVATE_TEXT')
    expect(f.questions).toEqual([])
    const r = await $.prompt.submit(prompt())
    expect(r.text).toBe('Continue my approved review')
    expect(r.context).toBeUndefined()
    expect(f.warnings.join(' ')).toContain(says)
    expect(f.warnings.join(' ')).not.toContain('PRIVATE_TEXT')
    expect(f.calls).toEqual([])
    expect(f.saved.size).toBe(1)
  })
}

test('a server still connecting at the deadline reports not connected, never an unknown outcome', { options: { autoContinue: true } }, async ($, on) => {
  const f = connection(on)
  f.state.hangConnect = true
  const pending = $.prompt.submit(prompt())
  await f.started
  await f.clock.advance(4001)
  const r = await pending
  expect(r.context).toBeUndefined()
  expect(f.warnings.join(' ')).toContain('not connected')
  expect(f.warnings.join(' ')).not.toContain('outcome is unknown')
  expect(f.calls).toEqual([])
})

test('a refused call names the tool without repeating the server text', { options: { autoContinue: true } }, async ($, on) => {
  const f = connection(on)
  f.state.error = 'refusal PRIVATE_TEXT'
  const r = await $.command.run(cmd('inbox'))
  expect(r.text).toContain('refused list_agent_roles')
  expect(r.text).not.toContain('PRIVATE_TEXT')
})

test('Doorbell running under another server name is called by that name, and its lease tools are still observed', { options: { autoContinue: true } }, async ($, on) => {
  const f = connection(on)
  f.state.connect = { isConnected: true, server: 'agent-doorbell' }
  expect((await $.prompt.submit(prompt())).context?.[0]).toContain('signal-1')
  expect(new Set(f.state.servers)).toEqual(new Set(['agent-doorbell']))
  f.state.items = [item('next')]
  await $.tool.call({ tool: 'mcp__agent-doorbell__ack_mcp_wakeup', leaseId: 'lease-signal-1' })
  expect((await $.classic.Stop({ stop_hook_active: false })).block).toContain('next')
})

test('the permission hook approves none of its tools for a call another origin raised', async ($, on) => {
  connection(on)
  // A test's $.tool.call raises classic.PreToolUse beneath the plugin's hooks:
  // an approval answers it there, and this spy beneath never sees the call.
  const reached: string[] = []
  on('classic.PreToolUse', ($, e) => { reached.push(e.tool); return {} })
  const tools = ['mcp__plugin_doorbell_doorbell__list_agent_roles', 'mcp__plugin_doorbell_doorbell__publish_mcp_message', 'mcp__plugin_doorbell_doorbell__get_notifier']
  for (const tool of tools) await $.tool.call({ tool } as never)
  expect(reached).toEqual(tools)
})
