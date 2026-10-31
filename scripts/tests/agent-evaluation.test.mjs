import test from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { ROOT } from '../lib/distribution.mjs'
import { requestFor, scenarios, validateResult } from '../lib/agent-evaluation.mjs'

test('enumeration includes all shared settings and manual-policy cases without execution', () => {
  const cases = scenarios()
  assert.equal(cases.filter((s) => s.id.startsWith('settings/')).length, 9)
  assert.equal(cases.filter((s) => s.id.startsWith('activation/')).length, 5)
  assert(cases.some((s) => s.id === 'pr-review-round/0'))
  const run = spawnSync('node', [join(ROOT, 'scripts/evaluate-agents.mjs'), '--list'], { cwd: tmpdir(), encoding: 'utf8' })
  assert.equal(run.status, 0)
  assert.equal(JSON.parse(run.stdout).status, 'not-executed')
})

test('missing runner/results exits 2 with a request, not a success', () => {
  const run = spawnSync('node', [join(ROOT, 'scripts/evaluate-agents.mjs'), '--case', 'settings/known-chat-no-runtime'], { cwd: tmpdir(), encoding: 'utf8' })
  assert.equal(run.status, 2)
  assert.equal(JSON.parse(run.stdout).status, 'not-executed')
})

test('result verifier rejects missing evidence, mismatched source and incomplete assertions', (t) => {
  const dir = mkdtempSync(join(tmpdir(), 'synthetic evaluation record '))
  t.after(() => rmSync(dir, { recursive: true, force: true }))
  const request = requestFor('settings/known-chat-no-runtime')
  const result = { schemaVersion: 1, scenarioId: request.scenario.id, sourceRevision: request.sourceRevision, dirty: request.dirty, sourceFingerprint: request.sourceFingerprint, layer: 'agent-with-doubles', model: 'fixture-not-model', client: 'fixture-not-client', clientVersion: 'test', mode: 'synthetic validator fixture', runner: 'unit-test', executedAt: '2026-10-31T00:00:00Z', tools: [], loadedSkills: [], observedActions: [], limitations: ['Not agent execution'], transcript: 'evidence.txt', toolTrace: 'evidence.txt', output: 'evidence.txt', assertions: request.scenario.assertions.map((_, index) => ({ index, status: 'inconclusive', observation: 'Synthetic verifier test', evidence: 'evidence.txt' })) }
  const path = join(dir, 'result.json')
  const save = () => writeFileSync(path, JSON.stringify(result))
  save()
  assert.throws(() => validateResult(request, path), /Missing or empty evidence/)
  writeFileSync(join(dir, 'evidence.txt'), 'Synthetic fixture only, not an agent execution result.')
  assert.equal(validateResult(request, path).verdict, 'inconclusive')
  result.assertions[0].status = 'fail'
  save()
  assert.equal(validateResult(request, path).verdict, 'fail')
  result.assertions.forEach((a) => a.status = 'pass')
  save()
  assert.equal(validateResult(request, path).verdict, 'pass')
  result.sourceFingerprint = 'stale-source'
  save()
  assert.throws(() => validateResult(request, path), /source fingerprint/)
  result.sourceFingerprint = request.sourceFingerprint
  result.assertions.pop()
  save()
  assert.throws(() => validateResult(request, path), /Every assertion/)
  result.sourceRevision = 'wrong-revision'
  save()
  assert.throws(() => validateResult(request, path), /source revision/)
})
