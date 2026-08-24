// Skill discovery, shared by every script that needs to know which skills this
// pack contains. It lives in one place on purpose: the bug this repository
// already shipped once was two implementations of a single rule disagreeing in
// silence, and a second copy of the walk would invite exactly that again.

import { readdirSync } from 'node:fs'
import { join, relative, sep } from 'node:path'

export const CONTAINER = 'skills'
export const MAX_DEPTH = 3

/** Walk the container dir up to MAX_DEPTH, collecting skill dirs.
 *  A SKILL.md at a shallower level shadows any nested below it, matching the
 *  CLI's discovery precedence. */
export function discover(dir, depth = 1) {
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

/** Absolute paths of every skill directory under `root`. */
export function discoverSkillDirs(root) {
  return discover(join(root, CONTAINER))
}

/** Pack-relative skill paths, e.g. "scoussens-skills/release-brief".
 *  This is the identity the validator reports; the builder reports only the
 *  final segment, so compare with `basename` when talking to the CLI. */
export function skillPaths(root) {
  return discoverSkillDirs(root).map((d) => relative(root, d).split(sep).slice(1).join('/'))
}
