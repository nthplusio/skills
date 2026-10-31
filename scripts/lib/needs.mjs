import { readFileSync } from 'node:fs'

const template = JSON.parse(readFileSync(new URL('../../skills/scoussens-skills/harness-discovery/assets/discovery.template.json', import.meta.url), 'utf8'))
const vocabulary = Object.values(template.harnesses)[0]

export function knownNeed(path) {
  let node = vocabulary
  for (const part of path.split('.')) {
    if (node === null || typeof node !== 'object' || Array.isArray(node) || !(part in node)) return false
    node = node[part]
  }
  return true
}
