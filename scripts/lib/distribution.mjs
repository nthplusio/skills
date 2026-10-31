import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, lstatSync, mkdirSync, readFileSync, rmSync, writeFileSync, chmodSync } from 'node:fs'
import { basename, dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { parse, stringify } from 'yaml'
import { discoverSkillDirs } from './discover-skills.mjs'
import { knownNeed } from './needs.mjs'

export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
export const BUNDLES = ['coding-agent', 'conversation']
const schema = 'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json'
const strictKeys = new Set(['name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools'])
const json = (value) => JSON.stringify(value, null, 2) + '\n'
const readJson = (path) => JSON.parse(readFileSync(path, 'utf8'))
const assert = (condition, message) => { if (!condition) throw new Error(message) }

export function frontmatter(text) {
  const match = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/.exec(text)
  assert(match, 'Missing YAML frontmatter')
  const data = parse(match[1])
  assert(data && typeof data === 'object' && !Array.isArray(data), 'Invalid frontmatter mapping')
  return { data, body: text.slice(match[0].length) }
}

export function safePath(root, path, allowMissing = false) {
  assert(typeof path === 'string' && path && !path.includes('\\') && !path.includes('\0'), `Invalid path: ${path}`)
  assert(!path.startsWith('/') && path.split('/').every((p) => p && p !== '.' && p !== '..'), `Unsafe path: ${path}`)
  let current = root
  for (const part of path.split('/')) {
    current = join(current, part)
    const entry = lstatSync(current, { throwIfNoEntry: false })
    assert(entry || allowMissing, `Missing path: ${path}`)
    assert(!entry?.isSymbolicLink(), `Symlink forbidden: ${path}`)
  }
  return current
}

export function loadCatalog(root = ROOT) {
  const catalog = readJson(join(root, 'distribution/catalog.json'))
  assert(catalog.schemaVersion === 1 && Array.isArray(catalog.skills), 'Invalid catalog version or skills')
  assert(catalog.support?.status === 'unverified-in-target-clients' && catalog.support.evidence, 'Support evidence must disclose target-client limits')
  const version = readJson(join(root, 'package.json')).version
  assert(typeof version === 'string' && /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/.test(version), 'Invalid package version for archive filename')
  const entries = catalog.skills.map((entry) => {
    const dir = safePath(root, entry.path)
    assert(lstatSync(dir).isDirectory(), `Not a skill directory: ${entry.path}`)
    const { data } = frontmatter(readFileSync(safePath(root, `${entry.path}/SKILL.md`), 'utf8'))
    assert(data.name === basename(dir) && typeof data.description === 'string' && data.description.trim(), `Invalid identity: ${entry.path}`)
    assert(['manual-only', 'task-intent', 'context-helper'].includes(entry.activation), `Invalid activation: ${data.name}`)
    assert((data['disable-model-invocation'] === true) === (entry.activation === 'manual-only'), `Activation policy loss: ${data.name}`)
    for (const field of ['bundles', 'required', 'optional']) {
      assert(Array.isArray(entry[field]) && entry[field].every((s) => typeof s === 'string') && new Set(entry[field]).size === entry[field].length, `Invalid ${field}: ${data.name}`)
    }
    assert(entry.bundles.every((b) => BUNDLES.includes(b)), `Unknown bundle: ${data.name}`)
    assert(entry.modes && Object.keys(entry.modes).length, `Missing modes: ${data.name}`)
    for (const [mode, caps] of Object.entries(entry.modes)) {
      assert(Array.isArray(caps.needs) && caps.needs.every((n) => typeof n === 'string' && knownNeed(n)), `Unknown capability: ${data.name}/${mode}`)
      assert(Array.isArray(caps.runtime) && caps.runtime.length && caps.runtime.every((r) => typeof r === 'string' && r.trim()), `Missing runtime requirements: ${data.name}/${mode}`)
    }
    return { ...entry, name: data.name, description: data.description, data }
  })
  assert(new Set(entries.map((e) => e.name)).size === entries.length, 'Duplicate catalog skill')
  const discovered = discoverSkillDirs(root).map((p) => relative(root, p)).sort()
  assert(json(entries.map((e) => e.path).sort()) === json(discovered), 'Catalog must cover exactly every public canonical skill')
  for (const entry of entries) {
    for (const dep of [...entry.required, ...entry.optional]) {
      assert(entries.some((e) => e.name === dep) && dep !== entry.name, `Missing or self companion: ${entry.name} -> ${dep}`)
    }
    assert(entry.required.every((d) => !entry.optional.includes(d)), `Companion both required and optional: ${entry.name}`)
  }
  return { ...catalog, entries, version }
}

export function closure(catalog, names) {
  const found = new Map()
  const active = new Set()
  function visit(name) {
    assert(!active.has(name), `Required companion cycle: ${name}`)
    if (found.has(name)) return
    const entry = catalog.entries.find((e) => e.name === name)
    assert(entry, `Missing required companion: ${name}`)
    active.add(name)
    for (const dep of entry.required) visit(dep)
    active.delete(name)
    found.set(name, entry)
  }
  names.forEach(visit)
  return [...found.values()].sort((a, b) => a.name.localeCompare(b.name))
}

export function bundleEntries(catalog, bundle) {
  assert(BUNDLES.includes(bundle), `Unknown bundle: ${bundle}`)
  const entries = closure(catalog, catalog.entries.filter((e) => e.bundles.includes(bundle)).map((e) => e.name))
  assert(entries.length, `Empty bundle: ${bundle}`)
  assert(entries.every((e) => e.bundles.includes(bundle)), `Required companion not reviewed for ${bundle}`)
  if (bundle === 'conversation') entries.forEach(assertStandalone)
  return entries
}

export function assertStandalone(entry) {
  assert(entry.activation !== 'manual-only', `Strict target cannot enforce manual-only policy: ${entry.name}`)
  assert(entry.required.length === 0, `Standalone target cannot load required companions: ${entry.name}`)
  assert(entry.bundles.includes('conversation'), `Not reviewed as conversational candidate: ${entry.name}`)
}

function identity(catalog, bundle) {
  return { name: `nthplusio-${bundle}`, version: catalog.version, description: `${bundle === 'conversation' ? 'Conversational' : 'Coding-agent'} skill candidates; target-client behavior unverified.`, license: 'MIT' }
}

export function metadataFiles(root, catalog) {
  const files = new Map()
  const readme = readFileSync(join(root, 'README.md'), 'utf8')
  const section = /## What's in here\n[\s\S]*?(?=\n## Claude Code plugins)/
  assert(section.test(readme), 'Missing README skill index section')
  const rows = catalog.entries.map((entry) => `| [\`${entry.name}\`](${entry.path}/SKILL.md) | ${entry.description.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('|', '\\|').replaceAll('\n', ' ')} |`)
  files.set('README.md', readme.replace(section, () => `## What's in here\n\n<!-- Generated from SKILL.md by distribution:sync. -->\n\n| Skill | Description |\n| --- | --- |\n${rows.join('\n')}\n`))
  for (const entry of catalog.entries) {
    files.set(`${entry.path}/agents/openai.yaml`, stringify({ interface: { display_name: entry.name }, policy: { allow_implicit_invocation: entry.activation !== 'manual-only' } }))
  }
  const skills = bundleEntries(catalog, 'coding-agent').map((e) => `./${e.path}`)
  const manifest = { ...identity(catalog, 'coding-agent'), skills }
  files.set('.claude-plugin/plugin.json', json(manifest))
  const marketplace = readJson(join(root, '.claude-plugin/marketplace.json'))
  const native = marketplace.plugins.filter((p) => p.name !== manifest.name)
  files.set('.claude-plugin/marketplace.json', json({ ...marketplace, plugins: [...native, { name: manifest.name, source: './', description: manifest.description, skills }] }))
  files.set('.agents/plugins/marketplace.json', json({ name: 'nthplusio-skills', interface: { displayName: 'nthplusio coding-agent candidates' }, plugins: [{ name: manifest.name, source: { source: 'local', path: './' }, policy: { installation: 'AVAILABLE', authentication: 'ON_INSTALL' }, category: 'Productivity' }] }))
  return files
}

export function syncMetadata(root = ROOT, check = false) {
  const catalog = loadCatalog(root)
  for (const [path, text] of metadataFiles(root, catalog)) {
    const destination = safePath(root, path, true)
    if (check) assert(existsSync(destination) && readFileSync(destination, 'utf8') === text, `Generated metadata drift: ${path}; run npm run distribution:sync`)
    else {
      mkdirSync(dirname(destination), { recursive: true })
      writeFileSync(destination, text)
    }
  }
  BUNDLES.forEach((bundle) => bundleEntries(catalog, bundle))
  return catalog
}

function trackedFiles(root) {
  return execFileSync('git', ['ls-files', '-z'], { cwd: root, encoding: 'utf8' }).split('\0').filter(Boolean)
}

function write(path, value) {
  mkdirSync(dirname(path), { recursive: true })
  writeFileSync(path, value)
  chmodSync(path, 0o644)
}

function copySkill(root, destination, entry, tracked, strict = false) {
  if (strict) assertStandalone(entry)
  const files = tracked.filter((p) => p.startsWith(`${entry.path}/`))
  assert(files.includes(`${entry.path}/SKILL.md`) && files.includes(`${entry.path}/agents/openai.yaml`), `Stage source and generated metadata before building: ${entry.name}`)
  for (const path of files) {
    const source = safePath(root, path)
    const owned = path.slice(entry.path.length + 1)
    assert(!/(^|\/)(\.env(?:\..*)?|credentials(?:\..*)?|id_rsa|id_ed25519|remembering-my-voice|\.config)(\/|$)|^profile\.md$|\.agents\/voice/i.test(owned), `Private resource path forbidden: ${path}`)
    assert(lstatSync(source).isFile(), `Not a regular resource: ${path}`)
    let bytes = readFileSync(source)
    if (strict && owned === 'SKILL.md') {
      const { data, body } = frontmatter(bytes.toString())
      assert(Object.keys(data).every((key) => strictKeys.has(key)), `Strict frontmatter would lose policy: ${entry.name}`)
      assert(Object.values(data.metadata ?? {}).every((v) => typeof v === 'string'), `Strict metadata must contain strings: ${entry.name}`)
      bytes = `---\n${stringify(data)}---\n${body}`
    }
    const target = join(destination, owned)
    write(target, bytes)
    chmodSync(target, lstatSync(source).mode & 0o111 ? 0o755 : 0o644)
  }
  if (!files.includes(`${entry.path}/LICENSE`)) write(join(destination, 'LICENSE'), readFileSync(safePath(root, 'LICENSE')))
}

export function build(root = ROOT) {
  const catalog = syncMetadata(root, true)
  const tracked = trackedFiles(root)
  const dist = join(root, 'dist')
  if (existsSync(dist)) {
    assert(!lstatSync(dist).isSymbolicLink() && existsSync(join(dist, '.distribution-owned')), 'Refusing to replace unmanaged dist directory')
    rmSync(dist, { recursive: true })
  }
  mkdirSync(dist)
  write(join(dist, '.distribution-owned'), 'Generated by scripts/build-distribution.mjs\n')
  const archives = []
  const zip = (folder, name) => {
    const output = join(dist, name)
    execFileSync('python3', [join(ROOT, 'scripts/zip-distribution.py'), folder, output])
    archives.push(name)
  }
  for (const bundle of BUNDLES) {
    const entries = bundleEntries(catalog, bundle)
    const manifest = identity(catalog, bundle)
    const folder = join(dist, 'plugins', manifest.name)
    for (const entry of entries) copySkill(root, join(folder, 'skills', entry.name), entry, tracked)
    write(join(folder, 'plugin.json'), json({ $schema: schema, ...manifest }))
    write(join(folder, '.claude-plugin/plugin.json'), json({ ...manifest, skills: ['./skills/'] }))
    write(join(folder, 'LICENSE'), readFileSync(safePath(root, 'LICENSE')))
    write(join(folder, 'README.md'), `# ${manifest.name}\n\nLocal candidate export, not a published release or client acceptance result.\n\n${catalog.support[bundle]}\n\n${entries.map((e) => `- **${e.name}**: ${e.description}\n  Activation: ${e.activation}. Modes: ${JSON.stringify(e.modes)}`).join('\n')}\n`)
    zip(folder, `${manifest.name}-${catalog.version}.zip`)
  }
  for (const entry of bundleEntries(catalog, 'conversation')) {
    const folder = join(dist, 'standalone', entry.name)
    copySkill(root, folder, entry, tracked, true)
    zip(folder, `${entry.name}-${catalog.version}.zip`)
  }
  const checksums = archives.map((name) => `${createHash('sha256').update(readFileSync(join(dist, name))).digest('hex')}  ${name}`).sort().join('\n') + '\n'
  write(join(dist, 'SHA256SUMS'), checksums)
  return { dist, archives, skills: catalog.entries.length }
}
