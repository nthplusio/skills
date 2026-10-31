#!/usr/bin/env node
import assert from 'node:assert/strict'
import { execFileSync, spawnSync } from 'node:child_process'
import { cpSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { build, loadCatalog, bundleEntries } from './lib/distribution.mjs'

const sandbox = mkdtempSync(join(tmpdir(), 'skills installed with spaces '))
try {
  const { dist } = build()
  const source = join(sandbox, 'candidate source')
  const project = join(sandbox, 'foreign project')
  const home = join(sandbox, 'isolated home')
  for (const dir of [project, home]) mkdirSync(dir)
  cpSync(join(dist, 'plugins/nthplusio-coding-agent'), source, { recursive: true })
  execFileSync('git', ['init', '-q', project])
  const env = { ...process.env, HOME: home, XDG_CONFIG_HOME: join(home, '.config'), CODEX_HOME: join(home, '.codex'), CLAUDE_CONFIG_DIR: join(home, '.claude'), DISABLE_TELEMETRY: '1', npm_config_ignore_scripts: 'true' }
  const entries = bundleEntries(loadCatalog(), 'coding-agent')
  const args = ['--yes', 'skills@1.7.4', 'add', source, '--skill', ...entries.map((e) => e.name), '--agent', 'codex', 'claude-code', '--copy', '--yes']
  for (let attempt = 0; attempt < 2; attempt++) {
    const install = spawnSync('npx', args, { cwd: project, env, encoding: 'utf8', timeout: 300000 })
    assert.equal(install.status, 0, `Pinned installer failed: ${install.error?.message ?? ''}\n${install.stdout}\n${install.stderr}`)
  }
  function compareTree(expected, actual) {
    assert(!lstatSync(actual).isSymbolicLink(), `--copy produced a symlink: ${actual}`)
    assert.deepEqual(readdirSync(actual).sort(), readdirSync(expected).sort())
    for (const name of readdirSync(expected)) {
      const from = join(expected, name)
      const to = join(actual, name)
      if (lstatSync(from).isDirectory()) compareTree(from, to)
      else assert.deepEqual(readFileSync(to), readFileSync(from), `Installed bytes differ: ${to}`)
    }
  }
  for (const host of ['.agents', '.claude']) {
    const installed = join(project, host, 'skills')
    assert.deepEqual(readdirSync(installed).sort(), entries.map((e) => e.name).sort())
    for (const entry of entries) compareTree(join(source, 'skills', entry.name), join(installed, entry.name))
    const records = join(project, 'meeting records.json')
    writeFileSync(records, JSON.stringify([{ id: 'synthetic', title: 'Offset boundary', start: '2026-01-01T01:30:00+02:00', duration_ms: 600000 }]))
    const result = JSON.parse(execFileSync('python3', ['-B', join(installed, 'meeting-index/scripts/rollup.py'), records, '--offset-hours', '-5', '--json'], { cwd: home, encoding: 'utf8', env }))
    assert.equal(result.days[0].date, '2025-12-31')
    assert.equal(result.days[0].entries[0].local, '18:30')
    assert.equal(result.total_minutes, 10)
    const handoff = join(project, 'handoff fixture.md')
    writeFileSync(handoff, '| ID | Action | Blocked by | Done when |\n| --- | --- | --- | --- |\n| A1 | Draft questions | — | Questions saved |\n| A2 | Collect answers | A1 | Answers recorded |\n')
    const checker = join(installed, 'agent-handoff/scripts/check-handoff.py')
    assert.equal(spawnSync('python3', ['-B', checker, handoff], { cwd: home, env }).status, 0)
    writeFileSync(handoff, '| ID | Action | Blocked by | Done when |\n| --- | --- | --- | --- |\n| A1 | Draft questions | A2 | Questions saved |\n| A2 | Collect answers | A1 | Answers recorded |\n')
    assert.equal(spawnSync('python3', ['-B', checker, handoff], { cwd: home, env }).status, 1)
  }
  console.log(`skills@1.7.4: ${entries.length} complete skills installed twice into each of Codex and Claude Code file locations; no duplicates; all bytes preserved. Installed rollup and handoff checker passed from foreign cwd with spaces. No target agent/client was executed.`)
} finally {
  rmSync(sandbox, { recursive: true, force: true })
}
