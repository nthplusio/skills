import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { ROOT } from '../lib/distribution.mjs'
import { SKILL, readPins } from '../check-upstream-pins.mjs'

const skill = readFileSync(join(ROOT, SKILL), 'utf8')
const { cli, skillVersion } = readPins(skill)
const replaceOnce = (from, to) => {
  const at = skill.lastIndexOf(from)
  assert(at > 0, `fixture text not found: ${from}`)
  return skill.slice(0, at) + to + skill.slice(at + from.length)
}

test('modern-web-guidance pins one exact CLI release and one skill version', () => {
  assert.match(cli, /^\d+\.\d+\.\d+$/)
  assert.match(skillVersion, /^\d{4}_\d{2}_\d{2}-/)
})

test('a pin that drifts in one command is rejected', () => {
  assert.throws(() => readPins(replaceOnce(`@${cli} legacy-scan`, '@9.9.9 legacy-scan')), /different CLI pin values/)
  assert.throws(() => readPins(replaceOnce(`--skill-version ${skillVersion}`, '--skill-version 2099_01_01-abcdef12')), /different --skill-version values/)
  assert.throws(() => readPins(skill.replaceAll(`@${cli}`, '@latest')), /`latest` is not an exact release/)
})

test('a command without a pin or a skill version is rejected', () => {
  assert.throws(() => readPins(replaceOnce(` --skill-version ${skillVersion}`, '')), /without --skill-version/)
  assert.throws(() => readPins(replaceOnce(`npx -y modern-web-guidance@${cli} search`, 'npx -y modern-web-guidance search')), /without a version/)
})
