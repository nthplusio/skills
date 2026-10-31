import test from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { parse } from 'yaml'
import { ROOT, build, loadCatalog, syncMetadata, closure, bundleEntries, assertStandalone } from '../lib/distribution.mjs'
import { discoverSkillDirs } from '../lib/discover-skills.mjs'

const readJson = (p) => JSON.parse(readFileSync(p, 'utf8'))
const hash = (value) => createHash('sha256').update(value).digest('hex')
function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), 'distribution test with spaces '))
  t.after(() => rmSync(root, { recursive: true, force: true }))
  for (const path of ['skills', 'distribution', '.claude-plugin', 'package.json', 'LICENSE', '.gitignore', 'README.md']) cpSync(join(ROOT, path), join(root, path), { recursive: true })
  execFileSync('git', ['init', '-q', root])
  syncMetadata(root)
  execFileSync('git', ['add', '.'], { cwd: root })
  return root
}
function changeCatalog(root, change) {
  const path = join(root, 'distribution/catalog.json')
  const catalog = readJson(path)
  change(catalog)
  writeFileSync(path, JSON.stringify(catalog))
}
function inspectZip(path) {
  return JSON.parse(execFileSync('python3', ['-c', `import hashlib,json,sys,zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
 print(json.dumps({i.filename: {"sha256": hashlib.sha256(z.read(i)).hexdigest(), "mode": i.external_attr >> 16, "text": z.read(i).decode() if i.filename.endswith(("SKILL.md", "README.md", "openai.yaml", "plugin.json", "LICENSE")) else None} for i in z.infolist()}))`, path], { encoding: 'utf8', maxBuffer: 8 * 1024 * 1024 }))
}

test('catalog covers 20 sources, five host-enforced policies and nine explain-to requirements', () => {
  const catalog = loadCatalog()
  assert.equal(catalog.entries.length, 20)
  assert.equal(catalog.entries.filter((e) => e.activation === 'manual-only').length, 5)
  assert.equal(catalog.entries.filter((e) => e.required.includes('explain-to')).length, 9)
  assert.deepEqual(closure(catalog, ['pr-teacher']).map((e) => e.name), ['explain-to', 'pr-teacher'])
  assert.deepEqual(closure(catalog, ['designing-questionnaires']).map((e) => e.name), ['designing-questionnaires'])
  assert.deepEqual(closure(catalog, ['explain-to']).map((e) => e.name), ['explain-to'])
})

test('build real archives with all tracked resources, licenses, policy and reproducible bytes', (t) => {
  const root = fixture(t)
  const before = discoverSkillDirs(root)
  const result = build(root)
  assert.equal(result.archives.length, 6)
  const catalog = loadCatalog(root)
  const tracked = execFileSync('git', ['ls-files', '-z', 'skills'], { cwd: root, encoding: 'utf8' }).split('\0').filter(Boolean)
  for (const name of result.archives) {
    const entries = inspectZip(join(result.dist, name))
    const paths = Object.keys(entries)
    const prefix = paths[0].split('/')[0]
    assert(paths.every((p) => p.startsWith(`${prefix}/`) && !p.split('/').includes('..') && (entries[p].mode & 0o170000) === 0o100000))
    assert(entries[`${prefix}/LICENSE`])
    const plugin = name.startsWith('nthplusio-')
    const sourceNames = plugin ? paths.filter((p) => /^.*\/skills\/[^/]+\/SKILL.md$/.test(p)).map((p) => p.split('/')[2]) : [prefix]
    assert.equal(sourceNames.length, plugin ? (name.includes('conversation') ? 4 : 18) : 1)
    assert(!sourceNames.includes('picking-skills') && !sourceNames.includes('pstack-sync'))
    if (plugin) {
      const portable = JSON.parse(entries[`${prefix}/plugin.json`].text)
      assert.deepEqual(Object.keys(portable).sort(), ['$schema', 'description', 'license', 'name', 'version'])
      assert.equal(portable.$schema, 'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json')
      assert.equal(portable.version, catalog.version)
      assert.equal(JSON.parse(entries[`${prefix}/.claude-plugin/plugin.json`].text).version, catalog.version)
      const readme = entries[`${prefix}/README.md`].text
      const documented = [...readme.matchAll(/^- \*\*([^*]+)\*\*:[\s\S]*?^  Activation: ([a-z-]+)\. Modes: (.+)$/gm)]
        .map(([, name, activation, modes]) => ({ name, activation, modes: JSON.parse(modes) }))
      const reviewed = bundleEntries(catalog, name.includes('conversation') ? 'conversation' : 'coding-agent')
        .map(({ name, activation, modes }) => ({ name, activation, modes }))
      assert.deepEqual(documented, reviewed, `${name} README must preserve every reviewed mode prerequisite`)
    }
    for (const skillName of sourceNames) {
      const entry = catalog.entries.find((e) => e.name === skillName)
      const exported = plugin ? `${prefix}/skills/${skillName}` : prefix
      for (const file of tracked.filter((p) => p.startsWith(`${entry.path}/`))) {
        const owned = file.slice(entry.path.length + 1)
        assert(entries[`${exported}/${owned}`], `Missing owned resource ${file}`)
        if (plugin || owned !== 'SKILL.md') assert.equal(entries[`${exported}/${owned}`].sha256, hash(readFileSync(join(root, file))))
      }
      assert(entries[`${exported}/LICENSE`])
      const sidecar = parse(entries[`${exported}/agents/openai.yaml`].text)
      assert.equal(sidecar.policy.allow_implicit_invocation, entry.activation !== 'manual-only')
      if (!plugin) {
        assertStandalone(entry)
        const text = entries[`${exported}/SKILL.md`].text
        const keys = Object.keys(parse(text.split('---\n')[1]))
        assert(keys.every((key) => ['name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools'].includes(key)))
      }
    }
  }
  const checksums = readFileSync(join(result.dist, 'SHA256SUMS'), 'utf8')
  build(root)
  assert.equal(readFileSync(join(result.dist, 'SHA256SUMS'), 'utf8'), checksums)
  assert.deepEqual(discoverSkillDirs(root), before)
})

test('generated metadata excludes native mods and preserves native Claude entries', (t) => {
  const root = fixture(t)
  const native = readJson(join(root, '.claude-plugin/marketplace.json')).plugins.filter((p) => p.name !== 'nthplusio-coding-agent')
  syncMetadata(root)
  assert.deepEqual(readJson(join(root, '.claude-plugin/marketplace.json')).plugins.filter((p) => p.name !== 'nthplusio-coding-agent'), native)
  const openai = readJson(join(root, '.agents/plugins/marketplace.json'))
  assert.deepEqual(openai.plugins.map((p) => p.name), ['nthplusio-coding-agent'])
  assert.deepEqual(openai.plugins[0].source, { source: 'local', path: './' })
  assert.deepEqual(openai.plugins[0].policy, { installation: 'AVAILABLE', authentication: 'ON_INSTALL' })
  const claude = readJson(join(root, '.claude-plugin/marketplace.json')).plugins.at(-1)
  assert.equal(claude.skills.length, 18)
})

test('missing companions, cycles and unreviewed closure fail rather than silently dropping dependencies', (t) => {
  const root = fixture(t)
  changeCatalog(root, (c) => c.skills.find((e) => e.path.endsWith('/pr-teacher')).required.push('absent'))
  assert.throws(() => loadCatalog(root), /Missing or self companion/)
  const catalog = loadCatalog()
  catalog.entries.find((e) => e.name === 'explain-to').bundles = []
  assert.throws(() => bundleEntries(catalog, 'coding-agent'), /not reviewed/)
  catalog.entries.find((e) => e.name === 'explain-to').required = ['pr-teacher']
  assert.throws(() => closure(catalog, ['pr-teacher']), /cycle/)
})

test('strict target refuses manual-only and required-companion workflows', () => {
  const catalog = loadCatalog()
  assert.throws(() => assertStandalone(catalog.entries.find((e) => e.name === 'pr-teacher')), /manual-only/)
  assert.throws(() => assertStandalone(catalog.entries.find((e) => e.name === 'dashboard')), /required companions/)
})

test('changing activation or generated host policy fails validation', (t) => {
  const root = fixture(t)
  const sidecar = join(root, 'skills/scoussens-skills/pr-detail/agents/openai.yaml')
  writeFileSync(sidecar, 'policy:\n  allow_implicit_invocation: true\n')
  assert.throws(() => syncMetadata(root, true), /metadata drift/)
  changeCatalog(root, (c) => c.skills.find((e) => e.path.endsWith('/pr-detail')).activation = 'task-intent')
  assert.throws(() => loadCatalog(root), /Activation policy loss/)
})

test('unknown mode capabilities fail against shared needs vocabulary', (t) => {
  const root = fixture(t)
  changeCatalog(root, (c) => c.skills[0].modes.conversation.needs.push('fake.install'))
  assert.throws(() => loadCatalog(root), /Unknown capability/)
})

for (const path of ['../outside', '/tmp/outside', 'skills/../outside', 'skills\\outside']) {
  test(`reject unsafe catalog path ${path}`, (t) => {
    const root = fixture(t)
    changeCatalog(root, (c) => c.skills[0].path = path)
    assert.throws(() => loadCatalog(root), /[Ii]nvalid path|Unsafe path/)
  })
}

test('tracked unsafe symlink and missing owned resource block build', (t) => {
  const root = fixture(t)
  const file = join(root, 'skills/scoussens-skills/speak-clearly/references/unsafe')
  symlinkSync('/etc/passwd', file)
  execFileSync('git', ['add', '.'], { cwd: root })
  assert.throws(() => build(root), /Symlink forbidden/)
  rmSync(file)
  assert.throws(() => build(root), /Missing path/)
})

test('symlinked canonical directory is rejected', (t) => {
  const root = fixture(t)
  const dir = join(root, 'skills/scoussens-skills/agent-handoff')
  rmSync(dir, { recursive: true })
  symlinkSync(join(ROOT, 'skills/scoussens-skills/agent-handoff'), dir)
  assert.throws(() => loadCatalog(root), /Symlink forbidden/)
})

test('metadata generation refuses a symlink destination without changing its target', (t) => {
  const root = fixture(t)
  const sidecar = join(root, 'skills/scoussens-skills/speak-clearly/agents/openai.yaml')
  const sentinel = join(root, 'sentinel')
  writeFileSync(sentinel, 'unchanged')
  rmSync(sidecar)
  symlinkSync(sentinel, sidecar)
  assert.throws(() => syncMetadata(root), /Symlink forbidden/)
  assert.equal(readFileSync(sentinel, 'utf8'), 'unchanged')
})

test('untracked private files are excluded and tracked credentials are rejected', (t) => {
  const root = fixture(t)
  const secret = join(root, 'skills/scoussens-skills/speak-clearly/.env')
  writeFileSync(secret, 'SYNTHETIC_TEST_VALUE=not-a-real-secret\n')
  const result = build(root)
  assert(!Object.keys(inspectZip(join(result.dist, `speak-clearly-${loadCatalog(root).version}.zip`))).some((p) => p.endsWith('.env')))
  execFileSync('git', ['add', secret], { cwd: root })
  assert.throws(() => build(root), /Private resource path/)
})

test('builder refuses to replace an unmanaged output directory', (t) => {
  const root = fixture(t)
  mkdirSync(join(root, 'dist'))
  writeFileSync(join(root, 'dist/keep'), 'user file')
  assert.throws(() => build(root), /unmanaged dist/)
  assert.equal(readFileSync(join(root, 'dist/keep'), 'utf8'), 'user file')
})
