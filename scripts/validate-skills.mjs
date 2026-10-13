#!/usr/bin/env node
// Validates every SKILL.md in this pack against the rules the skills.sh pack
// builder enforces silently. The builder skips invalid skills and omits binary
// or oversized files without failing, so a broken pack installs "successfully"
// with skills missing. This script turns that silence into a non-zero exit.
// It also applies the Agent Skills specification, which other clients enforce,
// and checks that each skill still works once installed as a lone directory.
//
// It parses frontmatter with `yaml` — the same parser the builder uses — because
// a reimplementation drifts. A hand-rolled reader here once accepted a
// description containing ": ", which YAML reads as a nested mapping: this script
// reported 3 valid skills while the builder shipped 2, silently dropping one.
// If the builder ever changes parser, change this import to match it.
//
// Usage: npm install && node scripts/validate-skills.mjs

import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { parse as parseYaml } from 'yaml'
import { CONTAINER, discoverPluginSkillDirs, discoverSkillDirs, skillPaths } from './lib/discover-skills.mjs'
import { dirname, join, relative, basename, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = process.cwd()
const MAX_FILE_BYTES = 2 * 1024 * 1024
// Limits from the Agent Skills specification (agentskills.io/specification).
const MAX_NAME = 64
const MAX_DESCRIPTION = 1024
const MAX_COMPATIBILITY = 500
const MAX_SKILL_LINES = 500
const REFERENCE_TOC_LINES = 300
// The specification's fields, plus `disable-model-invocation`, which Claude
// Code reads and the skills CLI passes through.
const FRONTMATTER_KEYS = new Set([
  'name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools',
  'disable-model-invocation',
])
// `metadata.needs` names harness capabilities a skill reads from discovery.json.
// Each item is a dotted path into one harness entry of harness-discovery's
// template, so the vocabulary has exactly one home.
const DISCOVERY_TEMPLATE = resolve(dirname(fileURLToPath(import.meta.url)),
  '../skills/scoussens-skills/harness-discovery/assets/discovery.template.json')
let needsVocabulary
function knownNeed(path) {
  if (needsVocabulary === undefined) {
    const template = JSON.parse(readFileSync(DISCOVERY_TEMPLATE, 'utf8'))
    needsVocabulary = Object.values(template.harnesses)[0]
  }
  let node = needsVocabulary
  for (const part of path.split('.')) {
    if (node === null || typeof node !== 'object' || Array.isArray(node) || !(part in node)) return false
    node = node[part]
  }
  return true
}
function checkNeeds(rel, value) {
  for (const item of value.split(',')) {
    const need = item.trim()
    if (!need) err(rel, 'metadata.needs has an empty item; write a comma-separated list of discovery paths')
    else if (!knownNeed(need)) err(rel, `metadata.needs names \`${need}\`, which is not a path in the discovery template (${relative(ROOT, DISCOVERY_TEMPLATE)})`)
  }
}

const errors = []
const warnings = []

const err = (file, msg) => errors.push({ file, msg })
const warn = (file, msg) => warnings.push({ file, msg })

/** Read the `---` block and parse it with the builder's parser.
 *  Returns { data } on success, or { error } with the parser's own message so
 *  the report matches what the pack builder prints when it skips a skill. */
function parseFrontmatter(text) {
  const match = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/.exec(text)
  if (!match) return { error: 'no YAML frontmatter; the pack builder skips this skill' }

  let data
  try {
    data = parseYaml(match[1])
  } catch (e) {
    // The parser's message carries line/column; keep it rather than paraphrasing.
    return { error: `YAML parse error: ${e.message.split('\n')[0].trim()}` }
  }

  if (data === null || typeof data !== 'object' || Array.isArray(data)) {
    return { error: 'frontmatter is not a key/value mapping' }
  }
  return { data }
}

/** Frontmatter values must be plain strings. Real YAML happily returns a number
 *  for `name: 2024` or a Date for a bare timestamp, and a downstream regex test
 *  on a non-string throws rather than reporting a useful error. */
function asString(value) {
  return typeof value === 'string' ? value : null
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

/** The skills CLI installs one skill directory, so a relative link that leaves
 *  it resolves in this checkout and breaks after install. */
function checkLinks(skillDir) {
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (entry.name.startsWith('.')) continue
      const full = join(dir, entry.name)
      if (entry.isDirectory()) {
        walk(full)
        continue
      }
      if (!entry.name.endsWith('.md')) continue
      const rel = relative(ROOT, full)
      const text = readFileSync(full, 'utf8')
      const prose = text.replace(/```[\s\S]*?```/g, '').replace(/`[^`\n]*`/g, '')
      for (const [, href] of prose.matchAll(/\]\(<?([^)\s>]+)>?\)/g)) {
        if (/^[a-z][a-z0-9+.-]*:|^#/i.test(href)) continue
        let path
        try {
          path = decodeURIComponent(href.split('#')[0])
        } catch {
          err(rel, `link ${href} has malformed percent-encoding`)
          continue
        }
        const target = resolve(dirname(full), path)
        if (!existsSync(target)) err(rel, `link ${href} points to a missing file`)
        else if (target !== skillDir && !target.startsWith(skillDir + sep)) {
          err(rel, `link ${href} leaves the skill directory; the installed skill cannot follow it`)
        }
      }
      const lines = text.split('\n').length
      if (full === join(skillDir, 'SKILL.md')) {
        if (lines > MAX_SKILL_LINES) warn(rel, `${lines} lines; keep SKILL.md under ${MAX_SKILL_LINES} and move detail to references/`)
      } else if (lines > REFERENCE_TOC_LINES && !/^#+ +(contents|table of contents)\s*$/im.test(text)) {
        warn(rel, `${lines} lines without a "Contents" heading; add a table of contents to files over ${REFERENCE_TOC_LINES} lines`)
      }
    }
  }
  walk(skillDir)
}

/** evals/evals.json follows skill-creator's schema. Eval `files` are paths from
 *  the repository root, so one checkout can run every skill's evals. */
function checkEvals(skillDir, name) {
  const path = join(skillDir, 'evals', 'evals.json')
  if (!existsSync(path)) return
  const rel = relative(ROOT, path)
  let data
  try {
    data = JSON.parse(readFileSync(path, 'utf8'))
  } catch (e) {
    err(rel, `invalid JSON: ${e.message}`)
    return
  }
  if (data === null || typeof data !== 'object' || Array.isArray(data)) {
    err(rel, 'must be a JSON object')
    return
  }
  if (data.skill_name !== name) err(rel, `skill_name "${data.skill_name}" does not match the skill name "${name}"`)
  if (!Array.isArray(data.evals) || data.evals.length === 0) {
    err(rel, '`evals` must be a non-empty array')
    return
  }
  const seen = new Set()
  for (const ev of data.evals) {
    if (ev === null || typeof ev !== 'object' || Array.isArray(ev)) {
      err(rel, 'every entry in `evals` must be an object')
      continue
    }
    const label = `eval ${ev.id}`
    if (!Number.isInteger(ev.id)) err(rel, `${label}: id must be an integer`)
    else if (seen.has(ev.id)) err(rel, `${label}: duplicate id`)
    seen.add(ev.id)
    for (const field of ['prompt', 'expected_output']) {
      if (typeof ev[field] !== 'string' || !ev[field].trim()) err(rel, `${label}: \`${field}\` must be a non-empty string`)
    }
    if (!Array.isArray(ev.assertions) || ev.assertions.length === 0 || !ev.assertions.every((a) => typeof a === 'string' && a.trim())) {
      err(rel, `${label}: \`assertions\` must be a non-empty list of strings`)
    }
    if (ev.files !== undefined && (!Array.isArray(ev.files) || !ev.files.every((f) => typeof f === 'string'))) {
      err(rel, `${label}: \`files\` must be a list of paths`)
      continue
    }
    for (const file of ev.files ?? []) {
      if (!existsSync(join(ROOT, file))) err(rel, `${label}: file ${file} does not exist (paths are from the repository root)`)
    }
  }
}

function checkFrontmatterFields(rel, fm) {
  for (const key of Object.keys(fm)) {
    if (!FRONTMATTER_KEYS.has(key)) err(rel, `unknown frontmatter field \`${key}\`; allowed: ${[...FRONTMATTER_KEYS].join(', ')}`)
  }
  if (fm.compatibility !== undefined) {
    if (typeof fm.compatibility !== 'string' || !fm.compatibility.trim()) err(rel, '`compatibility` must be a non-empty string')
    else if (fm.compatibility.length > MAX_COMPATIBILITY) err(rel, `compatibility is ${fm.compatibility.length} characters; the limit is ${MAX_COMPATIBILITY}`)
  }
  if (fm.metadata !== undefined) {
    if (fm.metadata === null || typeof fm.metadata !== 'object' || Array.isArray(fm.metadata)) {
      err(rel, '`metadata` must be a key/value mapping')
    } else {
      // The skills CLI hides a skill only when `internal` is the boolean true.
      for (const [key, value] of Object.entries(fm.metadata)) {
        const ok = key === 'internal' ? typeof value === 'boolean' : typeof value === 'string'
        if (!ok) err(rel, `metadata.${key} must be a ${key === 'internal' ? 'boolean' : 'string'}; YAML parsed it as ${typeof value}`)
        else if (key === 'needs') checkNeeds(rel, value)
      }
    }
  }
  if (fm['disable-model-invocation'] !== undefined && typeof fm['disable-model-invocation'] !== 'boolean') {
    err(rel, '`disable-model-invocation` must be true or false')
  }
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

  const { data: fm, error } = parseFrontmatter(text)
  if (error) {
    err(rel, error)
    return
  }

  const name = asString(fm.name)
  if (fm.name === undefined || fm.name === null) {
    err(rel, 'missing required frontmatter field `name`')
  } else if (name === null) {
    err(rel, `name must be a string; YAML parsed it as ${typeof fm.name}`)
  } else {
    if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(name)) {
      err(rel, `name "${name}" must be lowercase alphanumeric with single hyphens`)
    }
    if (name.length > MAX_NAME) err(rel, `name is ${name.length} characters; the limit is ${MAX_NAME}`)
    if (name !== dirName) {
      err(rel, `name "${name}" does not match its directory "${dirName}"`)
    }
  }

  const description = asString(fm.description)
  if (fm.description === undefined || fm.description === null) {
    err(rel, 'missing required frontmatter field `description`')
  } else if (description === null) {
    err(rel, `description must be a string; YAML parsed it as ${typeof fm.description}`)
  } else if (description.trim() === '') {
    err(rel, 'frontmatter field `description` is empty')
  } else if (description.length > MAX_DESCRIPTION) {
    err(rel, `description is ${description.length} characters; the limit is ${MAX_DESCRIPTION}`)
  } else {
    for (const { level, msg } of checkDescriptionQuality(description, name) ?? []) {
      ;(level === 'error' ? err : warn)(rel, msg)
    }
  }

  checkFrontmatterFields(rel, fm)
  checkLinks(skillDir)
  checkEvals(skillDir, name)

  const body = text.slice(text.indexOf('---', 3) + 3).trim()
  if (!body) warn(rel, 'frontmatter only, no instructions in the body')
}

const skillDirs = discoverSkillDirs(ROOT)

if (skillDirs.length === 0) {
  console.error(`✗ no skills found under ${CONTAINER}/ — a pack needs at least one`)
  process.exit(1)
}

const pluginSkillDirs = discoverPluginSkillDirs(ROOT)
for (const dir of [...skillDirs, ...pluginSkillDirs]) validateSkill(dir)

for (const { file, msg } of warnings) console.warn(`! ${file}: ${msg}`)
for (const { file, msg } of errors) console.error(`✗ ${file}: ${msg}`)

const names = skillPaths(ROOT)
if (errors.length > 0) {
  console.error(`\n${errors.length} error(s) across ${skillDirs.length + pluginSkillDirs.length} skill(s).`)
  process.exit(1)
}
const pluginNames = pluginSkillDirs.map((d) => relative(ROOT, d))
console.log(`✓ ${skillDirs.length} skill(s) valid: ${names.join(', ')}`)
if (pluginNames.length) console.log(`✓ ${pluginNames.length} plugin skill(s) valid: ${pluginNames.join(', ')}`)
