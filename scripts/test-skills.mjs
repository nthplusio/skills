#!/usr/bin/env node
// Runs every skill's Python unit tests: each `evals/` directory that holds a
// `test_*.py`. Discovery comes from the same walk the validator uses, so a new
// skill's tests run in CI without anyone adding them to a list.
//
// Usage: node scripts/test-skills.mjs

import { existsSync, readdirSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { join, relative } from 'node:path'
import { discoverPluginSkillDirs, discoverSkillDirs } from './lib/discover-skills.mjs'

const ROOT = process.cwd()
const suites = [...discoverSkillDirs(ROOT), ...discoverPluginSkillDirs(ROOT)]
  .map((dir) => join(dir, 'evals'))
  .filter((dir) => existsSync(dir) && readdirSync(dir).some((f) => /^test_.*\.py$/.test(f)))

if (suites.length === 0) {
  console.error('✗ no skill test suites found')
  process.exit(1)
}

const failed = []
for (const dir of suites) {
  const rel = relative(ROOT, dir)
  console.log(`\n▶ ${rel}`)
  const run = spawnSync('python3', ['-B', '-m', 'unittest', 'discover', '-s', dir], { stdio: 'inherit' })
  if (run.status !== 0) failed.push(rel)
}

if (failed.length > 0) {
  console.error(`\n✗ ${failed.length} of ${suites.length} suite(s) failed: ${failed.join(', ')}`)
  process.exit(1)
}
console.log(`\n✓ ${suites.length} suite(s) passed`)
