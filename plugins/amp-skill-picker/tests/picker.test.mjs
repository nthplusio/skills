import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import { once } from 'node:events'
import { cp, mkdir, mkdtemp, readFile, rename, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { delimiter, join } from 'node:path'
import { test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'
import register from '../index.ts'

async function fixture(t) {
  const root = await mkdtemp(join(tmpdir(), 'picker-plugin-test-'))
  const project = join(root, "project 'two")
  let skill = join(root, "installed 'skill")
  const bin = join(root, 'bin')
  await mkdir(project)
  await mkdir(bin)
  await cp(fileURLToPath(new URL('../../../skills/scoussens-skills/picking-skills/', import.meta.url)), skill, { recursive: true })
  await writeFile(join(bin, 'amp'), `#!/usr/bin/env node
const { readFileSync } = require('node:fs')
if (process.argv.slice(2).join(' ') !== 'skills list --json') process.exit(9)
process.stdout.write(readFileSync('inventory.json', 'utf8'))
`, { mode: 0o755 })
  const inventory = entries => writeFile(join(project, 'inventory.json'), JSON.stringify({ skills: entries, errors: [] }))
  const install = () => inventory([
    { name: 'unrelated', baseDir: 'not a file URL' },
    { name: 'picking-skills', baseDir: pathToFileURL(skill).href },
  ])
  await install()
  const original = { HOME: process.env.HOME, PATH: process.env.PATH }
  process.env.HOME = root
  process.env.PATH = bin + delimiter + original.PATH
  const server = spawn('node', [join(skill, 'scripts/server.mjs'), project], {
    env: { ...process.env, PORT: '0', PUBLIC_URL: 'https://picker.example.test/' },
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  t.after(async () => {
    for (const [key, value] of Object.entries(original)) {
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
    if (server.exitCode === null) {
      const exited = once(server, 'exit')
      server.kill()
      await exited
    }
    await rm(root, { recursive: true, force: true })
  })
  await once(server.stdout, 'data', { signal: AbortSignal.timeout(5000) })
  const key = createHash('sha256').update(project).digest('hex').slice(0, 16)
  const state = join(root, '.cache/amp/picking-skills', key)
  const { port } = JSON.parse(await readFile(join(state, 'service.json'), 'utf8'))
  const dialogs = []
  const notifications = []
  const commands = []
  let onStart
  let unavailable = false
  const ui = {
    async confirm(options) {
      if (unavailable) throw new Error('No interactive client')
      dialogs.push(options)
      return undefined
    },
    async notify(text) { notifications.push(text) },
  }
  register({
    system: { workspaceRoot: pathToFileURL(project) },
    helpers: {
      filePathFromURI: value => fileURLToPath(value),
      isPluginUINotAvailableError: error => error.message === 'No interactive client',
    },
    registerCommand(id, options, handler) { commands.push({ options, handler }) },
    on(event, handler) {
      assert.equal(event, 'agent.start')
      onStart = handler
    },
  })
  return {
    commands, dialogs, notifications, inventory, install,
    command: () => commands[0].handler({ ui }),
    start: message => onStart({ message }, { ui }),
    unavailable: () => { unavailable = true },
    async moveSkill() {
      const destination = skill + ' revision two'
      await rename(skill, destination)
      skill = destination
      await install()
    },
    async unsafeLauncher() {
      await writeFile(join(skill, 'scripts/launch.mjs'),
        'process.stdout.write(\'[Open skill picker](javascript:alert(1) "amp-portal")\\n\')')
    },
    async saved(url) {
      const response = await fetch(`http://127.0.0.1:${port}/api/requests/${new URL(url).hash.slice(1)}`)
      assert.equal(response.status, 200)
      return response.json()
    },
  }
}

test('palette action uses the installed picker and follows relocated sources without an agent turn', async t => {
  const f = await fixture(t)
  assert.equal(f.commands.length, 1)
  assert.equal(f.commands[0].options.category, 'Skills')
  assert.equal(f.commands[0].options.title, 'Open picker')
  await f.command()
  const dialog = f.dialogs[0]
  assert.equal(dialog.requireHuman, true)
  assert.equal(dialog.fields[0].type, 'link')
  assert.deepEqual(await f.saved(dialog.fields[0].value), { query: '', message: null })
  await f.moveSkill()
  f.unavailable()
  await f.command()
  const link = f.notifications[0]
  const url = /\((https:\/\/[^\s]+) "amp-portal"\)/.exec(link)[1]
  assert.deepEqual(await f.saved(url), { query: '', message: null })
  assert.notEqual(new URL(url).hash, new URL(dialog.fields[0].value).hash)
})

test('submitted triggers return an inline picker without dialogs and preserve tasks and literal searches', async t => {
  const f = await fixture(t)
  const text = '  Use <skill> to review A.\r\nThen <skill> for B. $& 界  '
  for (const [message, expected] of [
    ['/skills', { query: '', message: null }],
    [' /skills  code review \n', { query: 'code review', message: null }],
    ['/SKILLS --message-file /etc/passwd', { query: '--message-file /etc/passwd', message: null }],
    [text, { query: '', message: text }],
  ]) {
    const result = await f.start(message)
    assert.equal(f.dialogs.length, 0, 'Submitted requests must not require dismissing a dialog')
    assert.equal(f.notifications.length, 0)
    const embed = /^!\[Skill picker\]\((https:\/\/[^\s)]+) "amp-portal"\)$/m.exec(result.message.content)
    assert.ok(embed, 'The reply must embed the picker, not navigate to another page')
    const url = embed[1]
    assert.deepEqual(await f.saved(url), expected)
    assert.match(result.message.content, /wait for the user/)
    assert.ok(!result.message.content.includes(text))
  }
  const count = f.dialogs.length
  for (const message of ['Review this change.', 'Explain /skills to me.', '/skill review', '/skills-extra']) {
    assert.deepEqual(await f.start(message), {})
  }
  assert.equal(f.dialogs.length, count)
})

test('unavailable UI keeps the link; missing packages and unsafe launcher output leave the task pending', async t => {
  const f = await fixture(t)
  f.unavailable()
  const fallback = await f.start('Use <skill> for this task.')
  assert.match(fallback.message.content, /https:\/\/picker\.example\.test\/#/)
  assert.equal(f.notifications.length, 0)
  await f.inventory([])
  const missing = await f.start('/skills')
  assert.match(missing.message.content, /Install the picking-skills package/)
  assert.match(missing.message.content, /Keep the original task pending/)
  await f.command()
  assert.match(f.notifications.at(-1), /Install the picking-skills package/)
  await f.unsafeLauncher()
  await f.install()
  const unsafe = await f.start('/skills')
  assert.match(unsafe.message.content, /did not return an HTTPS portal link/)
  assert.match(unsafe.message.content, /Keep the original task pending/)
  assert.equal(f.dialogs.length, 0)
})
