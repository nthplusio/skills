// Runs a real Claude Code command against a disposable, public-MCP wire fixture.
// This checks the client connection, not Doorbell's backend or production OAuth.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { createServer } from 'node:http'
import { tmpdir } from 'node:os'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const plugin = resolve(dirname(fileURLToPath(import.meta.url)), '..')
// Doorbell declares doorbell-grant as a dependency and does not load without it.
const grant = resolve(plugin, '..', 'doorbell-grant')
const temp = await mkdtemp(`${tmpdir()}/doorbell-mcp-`)
const calls = []
const server = createServer(async (req, res) => {
  if (req.method !== 'POST') { res.writeHead(405).end(); return }
  let body = ''
  for await (const part of req) body += part
  const rpc = JSON.parse(body)
  if (rpc.id === undefined) { res.writeHead(202).end(); return }
  let result
  if (rpc.method === 'initialize') result = { protocolVersion: '2025-03-26', capabilities: { tools: {} }, serverInfo: { name: 'doorbell-public-fixture', version: '1' } }
  else if (rpc.method === 'tools/list') result = { tools: ['list_agent_roles', 'peek_mcp_pending'].map(name => ({ name, description: 'Disposable fixture', inputSchema: { type: 'object', properties: {} } })) }
  else if (rpc.method === 'tools/call') {
    calls.push(rpc.params)
    const value = rpc.params.name === 'list_agent_roles'
      ? { roles: [{ name: 'fixture-reviewer', inboxId: 'fixture-inbox', notifierId: 'fixture-notifier', active: true, bindings: [temp] }] }
      : { destinationId: 'fixture-inbox', items: [{ signalId: 'fixture-signal', synthetic: false, expired: false, wakeup: { body: { events: [] } }, lease: { holder: 'fixture-other-session', expiresAt: '2099-01-01T00:00:00Z' } }] }
    result = { content: [{ type: 'text', text: JSON.stringify(value) }], isError: false }
  } else { res.writeHead(400).end(); return }
  res.writeHead(200, { 'Content-Type': 'application/json' }).end(JSON.stringify({ jsonrpc: '2.0', id: rpc.id, result }))
})

await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
try {
  const port = server.address().port
  const settings = resolve(temp, 'settings.json')
  await writeFile(settings, JSON.stringify({ pluginConfigs: { 'doorbell@inline': { options: { mcpUrl: `http://127.0.0.1:${port}/mcp` } } } }))
  const child = spawn('claude', ['-p', '/doorbell:inbox', '--plugin-dir', grant, '--plugin-dir', plugin, '--settings', settings], {
    cwd: temp,
    env: { ...process.env, CLAUDE_CONFIG_DIR: resolve(temp, 'config'), ANTHROPIC_API_KEY: '', ANTHROPIC_AUTH_TOKEN: '', CLAUDE_CODE_OAUTH_TOKEN: '' },
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  let output = ''
  let errors = ''
  child.stdout.on('data', data => { output += data })
  child.stderr.on('data', data => { errors += data })
  const deadline = setTimeout(() => child.kill(), 30000)
  const exit = await new Promise((resolve, reject) => { child.on('error', reject); child.on('close', resolve) })
  clearTimeout(deadline)
  assert.equal(exit, 0, `Claude exited ${exit}: ${errors}`)
  assert.match(output, /fixture-reviewer/)
  assert.match(output, /fixture-other-session/)
  // Claude Code adds transport _meta (progress and tool-use IDs), not tool
  // arguments. Compare the public operation and input contract separately.
  assert.deepEqual(calls.map(({ name, arguments: args }) => ({ name, arguments: args })), [
    { name: 'list_agent_roles', arguments: {} },
    { name: 'peek_mcp_pending', arguments: { destinationId: 'fixture-inbox', includeLeased: true } },
  ])
  console.log('PASS: /doorbell:inbox resolved its namespace and configurable URL through Claude Code\'s connected public MCP; exactly two read-only calls, no lease or model call.')
} finally {
  server.closeAllConnections()
  await new Promise(resolve => server.close(resolve))
  await rm(temp, { recursive: true, force: true })
}
