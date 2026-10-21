import type { PluginAPI } from '@ampcode/plugin'
import { execFile } from 'node:child_process'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { promisify } from 'node:util'

export const description = 'Opens the searchable skill picker from the command palette or submitted /skills and <skill> requests.'

const run = promisify(execFile)
type PickerRequest = { kind: 'browse'; query: string } | { kind: 'message'; text: string }

export default function (amp: PluginAPI) {
  const cwd = amp.system.workspaceRoot
    ? amp.helpers.filePathFromURI(amp.system.workspaceRoot)
    : process.cwd()

  async function launchPicker(request: PickerRequest) {
    const { stdout: metadata } = await run('amp', ['skills', 'list', '--json'], {
      cwd, encoding: 'utf8', timeout: 30000, maxBuffer: 4 * 1024 * 1024,
    })
    const inventory: unknown = JSON.parse(metadata)
    let launcher: string | undefined
    if (inventory && typeof inventory === 'object' && 'skills' in inventory && Array.isArray(inventory.skills)) {
      for (const entry of inventory.skills) {
        const skill: unknown = entry
        if (skill && typeof skill === 'object' && 'name' in skill && skill.name === 'picking-skills' &&
          'baseDir' in skill && typeof skill.baseDir === 'string') {
          launcher = join(fileURLToPath(skill.baseDir), 'scripts/launch.mjs')
          break
        }
      }
    }
    if (!launcher) throw new Error('Install the picking-skills package from the skill library and reload skills.')

    let temporary: string | undefined
    try {
      const args = [launcher]
      if (request.kind === 'message') {
        temporary = await mkdtemp(join(tmpdir(), 'amp-skill-picker-'))
        const path = join(temporary, 'message.txt')
        await writeFile(path, request.text, { mode: 0o600 })
        args.push('--message-file', path)
      }
      args.push('--', request.kind === 'browse' ? request.query : '')
      const { stdout } = await run('node', args, {
        cwd, encoding: 'utf8', timeout: 180000, maxBuffer: 32768,
      })
      const match = /^\[Open skill picker\]\((https:\/\/[^\s)]+) "amp-portal"\)\s*$/.exec(stdout)
      if (!match) throw new Error('The picker launcher did not return an HTTPS portal link.')
      return { url: new URL(match[1]).href, link: stdout.trim() }
    } finally {
      if (temporary) await rm(temporary, { recursive: true, force: true })
    }
  }

  amp.registerCommand('skills.open-picker', {
    title: 'Open picker',
    category: 'Skills',
    description: 'Search installed skills and copy an exact-source loading instruction.',
  }, async ctx => {
    try {
      const { url, link } = await launchPicker({ kind: 'browse', query: '' })
      try {
        await ctx.ui.confirm({
          title: 'Skill picker',
          message: 'Open the picker, search by name or description, and copy your selection. Close this dialog with Done, then paste into Amp and send when ready.',
          fields: [{ name: 'picker', type: 'link', label: 'Open skill picker', value: url }],
          confirmButtonText: 'Done',
          requireHuman: true,
          skipIfUnwatched: true,
        })
      } catch (error) {
        if (!(error instanceof Error) || !amp.helpers.isPluginUINotAvailableError(error)) throw error
        await ctx.ui.notify(link)
      }
    } catch (error) {
      await ctx.ui.notify(`Unable to open the skill picker: ${error instanceof Error ? error.message : String(error)}`)
    }
  })

  amp.on('agent.start', async event => {
    const command = /^\/skills(?:\s+([\s\S]*))?$/i.exec(event.message.trim())
    let request: PickerRequest
    if (event.message.includes('<skill>')) {
      request = { kind: 'message', text: event.message }
    } else if (command) {
      request = { kind: 'browse', query: command[1]?.trim() ?? '' }
    } else {
      return {}
    }

    try {
      const { url } = await launchPicker(request)
      return { message: { content: [
        'The skill-picker plugin has already prepared this request. Reply with the live picker inline using the Markdown image below exactly, outside a code fence, then wait for the user to choose a skill and paste and send the completed request. Keep the original task pending. Reuse this request; do not launch another picker or choose a skill for the user.',
        `![Skill picker](${url} "amp-portal")`,
      ].join('\n\n') } }
    } catch (error) {
      return { message: { content: `The skill picker could not open: ${error instanceof Error ? error.message : String(error)}\nReport this error and wait for the user. Keep the original task pending; do not choose or assume a skill.` } }
    }
  })
}
