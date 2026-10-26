import assert from 'node:assert/strict'
import { Database } from 'bun:sqlite'
import { mkdtempSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { execFileSync } from 'node:child_process'
import { registerQuestionnaire } from '../adapters/amp.js'

const root = mkdtempSync(join(tmpdir(), 'questionnaire-adapter-'))
const database = join(root, 'review.sqlite')
const script = new URL('../scripts/questionnaire.py', import.meta.url).pathname
const example = new URL('../assets/example.json', import.meta.url).pathname
let dispose
try {
  execFileSync('python3', ['-B', script, '--db', database, 'publish', example])
  const db = new Database(database)
  const ids = [crypto.randomUUID(), crypto.randomUUID()]
  for (const id of ids) {
    db.query('INSERT INTO feedback (id, question, name, kind, message, created_at) VALUES (?, ?, ?, ?, ?, ?)').run(id, 'export-format', 'Example', 'answer', 'CSV', '2026-01-01T00:00:00Z')
    db.query('INSERT INTO delivery (feedback_id) VALUES (?)').run(id)
  }
  const reviewInstructions = join(root, 'reviewer.md')
  writeFileSync(reviewInstructions, 'Review only this example.')
  let handler
  let loseAppendResult = true
  const messages = []
  const amp = {
    onDispose: fn => { dispose = fn },
    createWebhook: async options => { handler = options.handler; return { url: 'https://example.invalid/private-capability' } },
    threads: { get: () => ({
      messages: async ({ offset, limit }) => messages.slice(offset, offset + limit),
      appendUserMessage: async message => {
        messages.push({ content: [{ type: 'text', text: message.content }] })
        if (loseAppendResult) { loseAppendResult = false; throw new Error('Lost append acknowledgment') }
      },
    }) },
  }
  const webhookFile = join(root, 'webhook-url')
  await registerQuestionnaire(amp, { database, thread: 'example-reviewer', key: 'example', webhookFile, reviewInstructions })
  const event = id => ({ body: new TextEncoder().encode(JSON.stringify({ feedback_id: id })) })
  const context = { signal: new AbortController().signal }
  await assert.rejects(handler(event(ids[0]), context), /Lost append/)
  assert.equal(db.query('SELECT receipt FROM delivery WHERE feedback_id = ?').get(ids[0]).receipt, null)
  await Promise.all([handler(event(ids[0]), context), handler(event(ids[0]), context)])
  assert.equal(messages.length, 1)
  assert.ok(db.query('SELECT receipt FROM delivery WHERE feedback_id = ?').get(ids[0]).receipt)
  const cancelled = new AbortController()
  cancelled.abort()
  await assert.rejects(handler(event(ids[1]), { signal: cancelled.signal }))
  assert.equal(messages.length, 1)
  await handler(event(ids[1]), context)
  assert.equal(messages.length, 2)
  assert.equal(statSync(webhookFile).mode & 0o777, 0o600)
  db.close()
  console.log('PASS: duplicate delivery, uncertain append recovery, cancellation, and private URL permissions')
} finally {
  dispose?.()
  rmSync(root, { recursive: true, force: true })
}
