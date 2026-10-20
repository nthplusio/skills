#!/usr/bin/env node
import { execFile } from 'node:child_process'
import { createHash } from 'node:crypto'
import { mkdir, readFile, readdir, realpath, rename, rm, stat, writeFile } from 'node:fs/promises'
import { createServer } from 'node:http'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { promisify } from 'node:util'

const run = promisify(execFile)
const lifetime = 24 * 60 * 60 * 1000
const requestName = /^[a-f0-9-]{36}\.json$/

export async function contextFor(directory) {
  const cwd = await realpath(directory)
  const key = createHash('sha256').update(cwd).digest('hex').slice(0, 16)
  const files = await Promise.all(['server.mjs', 'launch.mjs', '../assets/picker.html'].map(
    path => readFile(new URL(path, import.meta.url)),
  ))
  const version = createHash('sha256').update(Buffer.concat(files)).digest('hex')
  const state = join(homedir(), '.cache/amp/picking-skills', key)
  await mkdir(join(state, 'requests'), { recursive: true, mode: 0o700 })
  return { cwd, state, version, name: `skill-picker-${key}` }
}

export async function pruneRequests(state) {
  const directory = join(state, 'requests')
  const entries = await Promise.all((await readdir(directory)).filter(name => requestName.test(name)).map(async name => {
    const path = join(directory, name)
    try { return { path, time: (await stat(path)).mtimeMs } }
    catch (error) { if (error.code !== 'ENOENT') throw error }
  }))
  const files = entries.filter(Boolean)
  files.sort((a, b) => b.time - a.time)
  await Promise.all(files.filter((file, index) => index >= 127 || Date.now() - file.time >= lifetime)
    .map(file => rm(file.path, { force: true })))
}

async function discover(cwd) {
  const { stdout } = await run('amp', ['skills', 'list', '--json'], {
    cwd, encoding: 'utf8', timeout: 30000, maxBuffer: 4 * 1024 * 1024,
  })
  const inventory = JSON.parse(stdout)
  if (!Array.isArray(inventory?.skills) || !Array.isArray(inventory.errors)) {
    throw new Error('Invalid skill inventory')
  }
  const skills = inventory.skills.map(skill => {
    if (!skill || !['name', 'description', 'baseDir', 'source'].every(
      key => typeof skill[key] === 'string' && skill[key].trim(),
    )) throw new Error('Incomplete skill metadata')
    return {
      name: skill.name, description: skill.description, source: skill.source,
      directory: fileURLToPath(skill.baseDir),
    }
  }).sort((a, b) => a.name.localeCompare(b.name) || a.directory.localeCompare(b.directory))
  return { skills, warnings: inventory.errors.length }
}

async function serve() {
  const context = await contextFor(process.argv[2] || process.cwd())
  const html = await readFile(new URL('../assets/picker.html', import.meta.url))
  let pending
  const server = createServer(async (req, res) => {
    res.setHeader('Cache-Control', 'no-store')
    res.setHeader('X-Content-Type-Options', 'nosniff')
    res.setHeader('Referrer-Policy', 'no-referrer')
    res.setHeader('x-amp-review-widget', 'off')
    const send = (status, data) => {
      res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' })
      res.end(JSON.stringify(data))
    }
    const origin = process.env.PUBLIC_URL || `http://${req.headers.host}`
    if (req.url.startsWith('/api/') && (req.headers['sec-fetch-site'] === 'cross-site' ||
      (req.headers.origin && req.headers.origin !== new URL(origin).origin))) {
      return send(403, { error: 'Open the picker from its own portal.' })
    }
    if (req.method !== 'GET') return send(405, { error: 'Method not allowed.' })
    if (req.url === '/health') return send(200, { version: context.version, cwd: context.cwd })
    if (req.url === '/' || req.url === '/index.html') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' })
      return res.end(html)
    }
    if (req.url === '/api/skills') {
      try {
        pending ??= discover(context.cwd).finally(() => { pending = undefined })
        return send(200, await pending)
      } catch {
        return send(502, { error: 'Unable to read Amp’s skill inventory. Check amp skills list --json in this project, then click Refresh.' })
      }
    }
    const id = /^\/api\/requests\/([a-f0-9-]{36})$/.exec(req.url)?.[1]
    if (id) {
      const path = join(context.state, 'requests', `${id}.json`)
      try {
        if (Date.now() - (await stat(path)).mtimeMs >= lifetime) {
          await rm(path, { force: true })
          return send(410, { error: 'This saved request expired. Submit your message again to open a new picker.' })
        }
        return send(200, JSON.parse(await readFile(path, 'utf8')))
      } catch {
        return send(404, { error: 'This saved request is unavailable. Submit your message again to open a new picker.' })
      }
    }
    return send(404, { error: 'Not found.' })
  })
  server.listen(Number(process.env.PORT), '127.0.0.1', async () => {
    const info = {
      port: server.address().port, url: process.env.PUBLIC_URL,
      version: context.version, cwd: context.cwd,
    }
    const path = join(context.state, 'service.json')
    await writeFile(path + '.tmp', JSON.stringify(info), { mode: 0o600 })
    await rename(path + '.tmp', path)
    console.log('Skill picker ready.')
  })
  await pruneRequests(context.state)
  setInterval(() => pruneRequests(context.state).catch(() => {}), 60 * 60 * 1000).unref()
}

if (process.argv[1] && await realpath(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await serve()
}
