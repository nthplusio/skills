#!/usr/bin/env node
// Validates every SKILL.md in this pack against the rules the skills.sh pack
// builder enforces silently. The builder skips invalid skills and omits binary
// or oversized files without failing, so a broken pack installs "successfully"
// with skills missing. This script turns that silence into a non-zero exit.
//
// Usage: node scripts/validate-skills.mjs

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, basename, sep } from 'node:path'

const ROOT = process.cwd()
const CONTAINER = 'skills'
const MAX_DEPTH = 3
const MAX_FILE_BYTES = 2 * 1024 * 1024

const errors = []
const warnings = []

const err = (file, msg) => errors.push({ file, msg })
const warn = (file, msg) => warnings.push({ file, msg })

/** Walk the container dir up to MAX_DEPTH, collecting skill dirs.
 *  A SKILL.md at a shallower level shadows any nested below it, matching the
 *  CLI's discovery precedence. */
function discover(dir, depth = 1) {
  let entries
  try {
    entries = readdirSync(dir, { withFileTypes: true })
  } catch {
    return []
  }
  if (entries.some((e) => e.isFile() && e.name === 'SKILL.md')) return [dir]
  if (depth >= MAX_DEPTH) return []
  return entries
    .filter((e) => e.isDirectory() && !e.name.startsWith('.'))
    .flatMap((e) => discover(join(dir, e.name), depth + 1))
}

/** Minimal YAML frontmatter reader: top-level scalars and block scalars only.
 *  Deliberately not a full YAML parser — skills only need `name` and
 *  `description`, and a hand-rolled reader keeps this script dependency-free. */
function parseFrontmatter(text) {
  const match = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/.exec(text)
  if (!match) return null

  const out = {}
  const lines = match[1].split(/\r?\n/)
  let key = null
  let buffer = []

  const flush = () => {
    if (key) out[key] = buffer.join(' ').trim()
    key = null
    buffer = []
  }

  for (const line of lines) {
    const kv = /^([A-Za-z0-9_.-]+):\s*(.*)$/.exec(line)
    if (kv && !/^\s/.test(line)) {
      flush()
      const [, k, rawValue] = kv
      const value = rawValue.trim()
      if (value === '' || /^[|>][-+]?$/.test(value)) {
        key = k // block scalar or nested block; collect continuation lines
      } else {
        out[k] = value.replace(/^["'](.*)["']$/, '$1')
      }
    } else if (key && /^\s+\S/.test(line)) {
      buffer.push(line.trim())
    } else if (line.trim() === '') {
      // blank line inside a block scalar; keep collecting
    } else {
      flush()
    }
  }
  flush()
  return out
}

function isBinary(path) {
  const fd = readFileSync(path)
  return fd.subarray(0, 8000).includes(0)
}

/** Reject anything the pack builder would drop on the floor. */
function checkAssets(skillDir) {
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (entry.name.startsWith('.')) continue
      const full = join(dir, entry.name)
      const rel = relative(ROOT, full)
      if (entry.isDirectory()) {
        walk(full)
        continue
      }
      const { size } = statSync(full)
      if (size > MAX_FILE_BYTES) {
        err(rel, `${(size / 1024 / 1024).toFixed(2)} MB exceeds the 2 MB limit; the pack builder omits it`)
      } else if (isBinary(full)) {
        err(rel, 'binary file; the pack builder omits it')
      }
    }
  }
  walk(skillDir)
}

// TODO(you): implement the description-quality policy for this pack.
//
// WHY THIS IS YOURS TO DECIDE: `description` is the only text an agent reads
// before choosing whether to load a skill. A weak description means the skill
// silently never fires — the worst failure mode in a pack, because nothing
// errors. But quality is a judgement call, and where you set the bar is a real
// trade-off:
//
//   Strict  — e.g. require a "Use when" clause, a minimum length, and more than
//             N trigger terms. Catches lazy descriptions, but will reject
//             legitimately terse skills and nag you on every commit.
//   Lenient — e.g. warn only on obviously empty or generic text. Never gets in
//             your way, but lets weak descriptions ship.
//
// Return an array of { level: 'error' | 'warn', msg: string }. Returning [] is
// valid and simply disables the policy — the hard requirements above still run.
//
// See docs/writing-good-descriptions.md for the
// checklist this could encode.
function checkDescriptionQuality(description, name) {
  return []
}

function validateSkill(skillDir) {
  const rel = relative(ROOT, join(skillDir, 'SKILL.md'))
  const dirName = basename(skillDir)
  const text = readFileSync(join(skillDir, 'SKILL.md'), 'utf8')

  // Run asset checks first: a frontmatter failure below returns early, and
  // we still want oversized/binary files reported in the same pass.
  checkAssets(skillDir)

  const fm = parseFrontmatter(text)
  if (!fm) {
    err(rel, 'no YAML frontmatter; the pack builder skips this skill')
    return
  }

  if (!fm.name) {
    err(rel, 'missing required frontmatter field `name`')
  } else {
    if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(fm.name)) {
      err(rel, `name "${fm.name}" must be lowercase alphanumeric with single hyphens`)
    }
    if (fm.name !== dirName) {
      err(rel, `name "${fm.name}" does not match its directory "${dirName}"`)
    }
  }

  if (!fm.description) {
    err(rel, 'missing required frontmatter field `description`')
  } else {
    for (const { level, msg } of checkDescriptionQuality(fm.description, fm.name) ?? []) {
      ;(level === 'error' ? err : warn)(rel, msg)
    }
  }

  const body = text.slice(text.indexOf('---', 3) + 3).trim()
  if (!body) warn(rel, 'frontmatter only, no instructions in the body')
}

const skillDirs = discover(join(ROOT, CONTAINER))

if (skillDirs.length === 0) {
  console.error(`✗ no skills found under ${CONTAINER}/ — a pack needs at least one`)
  process.exit(1)
}

for (const dir of skillDirs) validateSkill(dir)

for (const { file, msg } of warnings) console.warn(`! ${file}: ${msg}`)
for (const { file, msg } of errors) console.error(`✗ ${file}: ${msg}`)

const names = skillDirs.map((d) => relative(ROOT, d).split(sep).slice(1).join('/'))
if (errors.length > 0) {
  console.error(`\n${errors.length} error(s) across ${skillDirs.length} skill(s).`)
  process.exit(1)
}
console.log(`✓ ${skillDirs.length} skill(s) valid: ${names.join(', ')}`)
