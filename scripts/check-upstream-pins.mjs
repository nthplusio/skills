#!/usr/bin/env node
// Checks that modern-web-guidance pins one exact CLI release and passes that
// release's own skill version. The CLI compares --skill-version with the
// skill-version.txt it ships and tells agents to "insist that the user
// upgrade" when the caller is older, so the two values only change together.
//
// Usage: node scripts/check-upstream-pins.mjs
// Downloads the pinned package from the npm registry; CI runs it as its own job.

import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'

export const SKILL = 'skills/scoussens-skills/modern-web-guidance/SKILL.md'
const PACKAGE = 'modern-web-guidance'

function single(found, label, format) {
  const values = [...new Set(found)]
  if (values.length === 0) throw new Error(`${SKILL} has no ${label}`)
  if (values.length > 1) throw new Error(`${SKILL} has different ${label} values: ${values.join(', ')}; use one everywhere`)
  if (!format.test(values[0])) throw new Error(`${SKILL} ${label} \`${values[0]}\` is not an exact release`)
  return values[0]
}

export function readPins(text) {
  const unpinned = text.match(/\b(?:npx|pnpx)\b[^`\n]*\bmodern-web-guidance(?![@\w-])/)
  if (unpinned) throw new Error(`${SKILL} runs the CLI without a version: \`${unpinned[0]}\``)
  for (const line of text.split('\n')) {
    if (/modern-web-guidance@\S+ (?:search|retrieve|list|legacy-scan)\b/.test(line) && !line.includes('--skill-version ')) {
      throw new Error(`${SKILL} runs the CLI without --skill-version: \`${line.trim()}\``)
    }
  }
  return {
    cli: single([...text.matchAll(/modern-web-guidance@([^\s`*]+)/g)].map((m) => m[1]), 'CLI pin', /^\d+\.\d+\.\d+$/),
    skillVersion: single([...text.matchAll(/--skill-version ([^\s`]+)/g)].map((m) => m[1]), '--skill-version', /^\d{4}_\d{2}_\d{2}-[0-9a-f]+$/),
  }
}

function shippedSkillVersion(cli) {
  const dir = mkdtempSync(join(tmpdir(), 'upstream-pins-'))
  try {
    const [{ filename }] = JSON.parse(execFileSync('npm', ['pack', `${PACKAGE}@${cli}`, '--json', '--ignore-scripts', '--pack-destination', dir], { encoding: 'utf8' }))
    return execFileSync('tar', ['-xzOf', join(dir, filename), `package/skills/${PACKAGE}/skill-version.txt`], { encoding: 'utf8' }).trim()
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const { cli, skillVersion } = readPins(readFileSync(SKILL, 'utf8'))
    const shipped = shippedSkillVersion(cli)
    if (shipped !== skillVersion) {
      console.error(`✗ ${PACKAGE}@${cli} ships skill version ${shipped}, but ${SKILL} passes --skill-version ${skillVersion}`)
      console.error(`  Set every --skill-version to ${shipped}, or pin the CLI release that ships ${skillVersion}.`)
      process.exit(1)
    }
    console.log(`✓ ${PACKAGE}@${cli} ships skill version ${shipped}, matching every --skill-version in ${SKILL}`)
  } catch (error) {
    console.error(`✗ ${error.message}`)
    process.exit(1)
  }
}
