#!/usr/bin/env node
import { execFile } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { parseArgs, promisify } from 'node:util'
import { contextFor, pruneRequests } from './server.mjs'

const run = promisify(execFile)
const quote = value => `'${value.replaceAll("'", "'\\''")}'`

try {
  const { values, positionals } = parseArgs({
    options: { 'message-file': { type: 'string' }, locked: { type: 'boolean' } },
    allowPositionals: true,
  })
  const message = values['message-file'] ? await readFile(values['message-file'], 'utf8') : null
  if (message !== null && !message.includes('<skill>')) {
    throw new Error('The message file must contain a literal <skill> placeholder.')
  }
  const context = await contextFor(process.cwd())
  if (!values.locked) {
    const { stdout } = await run('flock', ['-w', '90', join(context.state, 'launch.lock'),
      process.execPath, fileURLToPath(import.meta.url), '--locked', ...process.argv.slice(2)],
    { cwd: context.cwd, encoding: 'utf8', timeout: 150000, maxBuffer: 8192 })
    process.stdout.write(stdout)
  } else {
    let info
    let healthy = false
    try {
      info = JSON.parse(await readFile(join(context.state, 'service.json'), 'utf8'))
      const response = await fetch(`http://127.0.0.1:${info.port}/health`, { signal: AbortSignal.timeout(2000) })
      const health = await response.json()
      healthy = response.ok && health.cwd === context.cwd && health.version === context.version && !!info.url
    } catch {}
    if (!healthy) {
      if (info) {
        try { await run('amp', ['orb', 'service', 'stop', context.name], { timeout: 15000 }) }
        catch (error) {
          if (!error.stderr?.includes(`Service ${context.name} is not running.`)) throw error
        }
      }
      const server = fileURLToPath(new URL('./server.mjs', import.meta.url))
      await run('amp', ['orb', 'service', 'start', context.name,
        '--command', `${quote(process.execPath)} ${quote(server)} ${quote(context.cwd)}`,
        ...(info?.port ? ['--port', String(info.port)] : []),
        '--cwd', context.cwd, '--portal', '--title', 'Skill picker',
        '--description', 'Search skills and copy an exact-source loading request.'],
      { cwd: context.cwd, timeout: 90000, maxBuffer: 32768 })
      info = JSON.parse(await readFile(join(context.state, 'service.json'), 'utf8'))
      const response = await fetch(`http://127.0.0.1:${info.port}/health`, { signal: AbortSignal.timeout(2000) })
      const health = await response.json()
      if (!response.ok || health.version !== context.version || health.cwd !== context.cwd || !info.url) {
        throw new Error('The picker service did not become ready.')
      }
    }
    await pruneRequests(context.state)
    const id = randomUUID()
    await writeFile(join(context.state, 'requests', `${id}.json`),
      JSON.stringify({ query: positionals.join(' '), message }), { mode: 0o600, flag: 'wx' })
    const url = new URL(info.url)
    url.hash = id
    process.stdout.write(`[Open skill picker](${url.href} "amp-portal")\n`)
  }
} catch (error) {
  console.error(`Unable to open the skill picker: ${error.message}`)
  process.exitCode = 1
}
