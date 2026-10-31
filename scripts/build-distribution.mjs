#!/usr/bin/env node
import { build, syncMetadata } from './lib/distribution.mjs'

try {
  const command = process.argv[2] ?? 'build'
  if (command === 'sync' || command === 'check') {
    const catalog = syncMetadata(undefined, command === 'check')
    console.log(`${command}: ${catalog.entries.length} catalog entries; source metadata consistent`)
  } else if (command === 'build') {
    const result = build()
    console.log(`${result.skills} public skills reviewed; ${result.archives.length} candidate archives in ${result.dist}`)
  } else throw new Error(`Unknown command: ${command}`)
} catch (error) {
  console.error(error.message)
  process.exitCode = 1
}
