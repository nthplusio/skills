#!/usr/bin/env node
import { resolve } from 'node:path'
import { requestFor, scenarios, validateResult } from './lib/agent-evaluation.mjs'

try {
  const args = process.argv.slice(2)
  if (args.length === 1 && args[0] === '--list') {
    console.log(JSON.stringify({ status: 'not-executed', scenarios: scenarios().map((s) => s.id) }, null, 2))
  } else {
    if (args[0] !== '--case' || !args[1] || ![2, 4].includes(args.length) || (args.length === 4 && args[2] !== '--results')) throw new Error('Usage: --list | --case ID [--results /absolute/result.json]')
    const request = requestFor(args[1])
    if (args.length === 2) {
      console.log(JSON.stringify(request, null, 2))
      console.error('NOT EXECUTED: no agent runner/results supplied. Use distribution/agent-evaluation.md adapter contract.')
      process.exitCode = 2
    } else {
      const report = validateResult(request, resolve(args[3]))
      console.log(JSON.stringify(report, null, 2))
      process.exitCode = report.verdict === 'pass' ? 0 : report.verdict === 'fail' ? 1 : 2
    }
  }
} catch (error) {
  console.error(error.message)
  process.exitCode = 1
}
