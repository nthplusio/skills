#!/usr/bin/env node
// Runs the real skills.sh CLI against this checkout and asserts it finds every
// skill the repository contains.
//
// WHY THIS EXISTS ALONGSIDE validate-skills.mjs: the validator encodes the
// builder's rules, and encoded rules drift. This script does not encode
// anything — it invokes the builder and reads what it actually did, so it
// cannot fall out of step by construction. It is the backstop for the failure
// this repository already shipped once: a skill the validator called valid and
// the builder silently dropped, leaving the published pack a skill short while
// CI stayed green.
//
// The trade is that this reaches the network and runs `skills@latest`, so an
// upstream change can fail the build without anything here changing. That is
// deliberate — upstream changing the rules IS the thing worth being told about
// — but it is why this runs as its own CI job, separate from the hermetic
// validator, so the two failures are never confused for one another.
//
// Usage: node scripts/check-builder-agrees.mjs

import { spawnSync } from 'node:child_process'
import { basename } from 'node:path'
import { skillPaths } from './lib/discover-skills.mjs'

const ROOT = process.cwd()
const expected = skillPaths(ROOT).map((p) => basename(p)).sort()

if (expected.length === 0) {
  console.error('✗ no skills found in this checkout — a pack needs at least one')
  process.exit(1)
}

// Read BOTH streams. The CLI prints its skill list on stdout but writes the
// "⚠ Skipped …" warning — the one line that says WHY a skill was dropped — to
// stderr, so capturing stdout alone reports the failure without the reason.
const run = spawnSync('npx', ['-y', 'skills@latest', 'add', ROOT, '--list', '--yes'], {
  encoding: 'utf8',
  stdio: ['ignore', 'pipe', 'pipe'],
  timeout: 5 * 60 * 1000,
})

if (run.error) {
  console.error(`✗ could not run the skills CLI: ${run.error.message}`)
  process.exit(1)
}

const output = `${run.stdout ?? ''}\n${run.stderr ?? ''}`
if (!output.trim()) {
  console.error('✗ the skills CLI produced no output')
  process.exit(1)
}

// The CLI writes a spinner and colour; strip both before matching.
const plain = output
  .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')
  .replace(/\r/g, '\n')

// Anything the builder refused. This is the line that went unnoticed before.
const skipped = [...plain.matchAll(/Skipped\s+(\S+)\s+—\s+([^\n]+)/g)].map((m) => ({
  file: m[1],
  reason: m[2].trim(),
}))

const found = [...plain.matchAll(/^\s*│\s{2,}([a-z0-9][a-z0-9-]*)\s*$/gm)]
  .map((m) => m[1])
  .sort()

const countMatch = /Found (\d+) skills?/.exec(plain)
const reportedCount = countMatch ? Number(countMatch[1]) : null

if (reportedCount === null) {
  console.error('✗ could not read a "Found N skills" line from the CLI output.')
  console.error('  The CLI output format may have changed. Raw output follows:\n')
  console.error(plain.trim())
  process.exit(1)
}

const missing = expected.filter((s) => !found.includes(s))
const extra = found.filter((s) => !expected.includes(s))

for (const { file, reason } of skipped) {
  console.error(`✗ the builder skipped ${file}\n    ${reason}`)
}
for (const s of missing) console.error(`✗ "${s}" exists in this repo but the builder did not find it`)
for (const s of extra) console.error(`✗ the builder found "${s}", which is not a skill directory here`)

if (reportedCount !== expected.length) {
  console.error(
    `✗ the builder reported ${reportedCount} skill(s); this repository contains ${expected.length}`,
  )
}

if (skipped.length || missing.length || extra.length || reportedCount !== expected.length) {
  console.error(
    `\nThe pack builder and this repository disagree. A skill in that gap is dropped\n` +
      `from the published pack without an error, so fix the skill rather than this check.`,
  )
  process.exit(1)
}

console.log(`✓ the builder found all ${expected.length} skill(s): ${found.join(', ')}`)
