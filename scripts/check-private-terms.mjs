#!/usr/bin/env node
// Fails when a tracked file mentions something private: an employer, a client,
// a person, a private repository or tracker prefix. The patterns cannot live in
// this public repository, so they come from the PRIVATE_TERMS environment
// variable (CI reads it from a repository secret) or from the untracked
// `.private-terms` file. Each non-empty line not starting with `#` is a
// case-insensitive regular expression.
//
// Usage: node scripts/check-private-terms.mjs

import { existsSync, readFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'

const ROOT = process.cwd()
const LOCAL = '.private-terms'

const lines = [
  ...(process.env.PRIVATE_TERMS ?? '').split('\n'),
  ...(existsSync(LOCAL) ? readFileSync(LOCAL, 'utf8').split('\n') : []),
]
  .map((l) => l.trim())
  .filter((l) => l && !l.startsWith('#'))

if (lines.length === 0) {
  console.warn(`! no private terms configured; set PRIVATE_TERMS or create ${LOCAL}`)
  process.exit(0)
}

const patterns = lines.map((source, p) => {
  try {
    return new RegExp(source, 'i')
  } catch {
    console.error(`✗ private term #${p + 1} is not a valid regular expression`)
    process.exit(1)
  }
})

const files = execFileSync('git', ['ls-files', '-z'], { cwd: ROOT, encoding: 'utf8' }).split('\0').filter(Boolean)
let hits = 0
for (const file of files) {
  let text
  try {
    text = readFileSync(file)
  } catch {
    continue
  }
  if (text.subarray(0, 8000).includes(0)) continue
  text.toString('utf8').split('\n').forEach((line, i) => {
    patterns.forEach((pattern, p) => {
      if (pattern.test(line)) {
        hits++
        // Name the pattern by its position, so CI logs never echo the secret.
        console.error(`✗ ${file}:${i + 1}: matches private term #${p + 1}`)
      }
    })
  })
}

if (hits > 0) {
  console.error(`\n${hits} private reference(s) in ${files.length} tracked file(s).`)
  process.exit(1)
}
console.log(`✓ no private terms in ${files.length} tracked file(s) (${patterns.length} pattern(s))`)
