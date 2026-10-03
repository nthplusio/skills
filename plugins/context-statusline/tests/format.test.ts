import type { On, RenderElement } from 'claude-code'
import { describe, expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'

import type { CacheSegment, StatusSegments } from '../types'
import {
  BRANCH_ICON, MAX_BAR, MIN_BAR, NARROW_BAR, REPO_ICON, TTL_MS,
  bandCells, bands, cellWidth, formatCache, formatStatus, hitPercent, layout, meterBar, meterColor, modelDisplayName, truncate,
} from '../hooks/format.ts'
import type { Layout } from '../hooks/format.ts'

const GIT = { repo: 'platform', branch: 'development' }
const M = 1000000

describe('meterColor', () => {
  test('green up to the 200k reference on a larger window', async () => {
    expect([0, 85000, 200000].map(t => meterColor(t, M))).toEqual([40, 40, 40])
  })
  test('hard step into the 5-step ramp past 200k, spread to the cap; a boundary belongs below', async () => {
    expect([200001, 359999, 360000, 360001, 450000, 999999, M, 1200000].map(t => meterColor(t, M)))
      .toEqual([220, 220, 220, 214, 214, 167, 167, 167])
  })
  test('a 200k window targets its first half, then the same ramp', async () => {
    expect([0, 50000, 100000, 100001, 150000, 199999, 200000].map(t => meterColor(t, 200000)))
      .toEqual([40, 40, 40, 220, 208, 167, 167])
  })
  test('unknown cap is green', async () => {
    expect(meterColor(500000, 0)).toBe(40)
  })
})

describe('formatStatus', () => {
  test('under 200k: green, no room note', async () => {
    expect(formatStatus({ modelId: 'claude-opus-5-5', tokens: 85000, cap: M, git: GIT })).toEqual({
      model: 'Opus 5.5',
      meter: { color: 40, used: 85000, cap: M, tokens: '85k', total: '1M', room: '' },
      git: GIT,
    })
  })
  test('exactly 200k is still green and shows no room note', async () => {
    expect(formatStatus({ modelId: 'claude-opus-5-5', tokens: 200000, cap: M, git: null }).meter)
      .toEqual({ color: 40, used: 200000, cap: M, tokens: '200k', total: '1M', room: '' })
  })
  test('between 200k and the cap shows room left', async () => {
    expect(formatStatus({ modelId: 'claude-opus-5-5', tokens: 450000, cap: M, git: null }).meter)
      .toEqual({ color: 214, used: 450000, cap: M, tokens: '450k', total: '1M', room: '(550k left)' })
  })
  test('at and over the cap', async () => {
    expect(formatStatus({ modelId: 'x', tokens: M, cap: M, git: null }).meter.room).toBe('(cap reached)')
    expect(formatStatus({ modelId: 'x', tokens: 1010000, cap: M, git: null }).meter.room).toBe('(cap reached)')
  })
  test('a 200k window reports reaching its cap', async () => {
    expect(formatStatus({ modelId: 'x', tokens: 200000, cap: 200000, git: null }).meter)
      .toEqual({ color: 167, used: 200000, cap: 200000, tokens: '200k', total: '200k', room: '(cap reached)' })
  })
  test('unknown cap: green, no room note', async () => {
    expect(formatStatus({ modelId: 'x', tokens: 250000, cap: 0, git: null }).meter)
      .toEqual({ color: 40, used: 250000, cap: 0, tokens: '250k', total: '', room: '' })
  })
})

describe('modelDisplayName', () => {
  test('maps Claude model IDs', async () => {
    expect(['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-fable-5-1', 'claude-haiku-4-5-20251001', 'claude-opus-5-5[1m]']
      .map(modelDisplayName)).toEqual(['Opus 5.5', 'Sonnet 5.5', 'Fable 5.1', 'Haiku 4.5', 'Opus 5.5'])
  })
  test('falls back to the raw value, less a parenthetical', async () => {
    expect(modelDisplayName('gpt-oss')).toBe('gpt-oss')
    expect(modelDisplayName('Opus 5.5 (1M context)')).toBe('Opus 5.5')
  })
})

describe('bands', () => {
  test('green to 200k, then the 5-step ramp in equal token ranges to a larger cap', async () => {
    expect(bands(M)).toEqual([
      { from: 0, to: 200000, color: 40 }, { from: 200000, to: 360000, color: 220 }, { from: 360000, to: 520000, color: 214 },
      { from: 520000, to: 680000, color: 208 }, { from: 680000, to: 840000, color: 173 }, { from: 840000, to: M, color: 167 },
    ])
  })
  test('a 200k window targets its first half; unknown cap is the 200k reference, green', async () => {
    expect(bands(200000).map(b => b.from)).toEqual([0, 100000, 120000, 140000, 160000, 180000])
    expect(bands(0)).toEqual([{ from: 0, to: 200000, color: 40 }])
  })
  test('the target takes half the bar, each band past it less, each at least a cell', async () => {
    expect([10, 20, 30, 40].map(w => bandCells(6, w))).toEqual([[4, 2, 1, 1, 1, 1], [10, 4, 2, 2, 1, 1], [15, 6, 4, 2, 2, 1], [20, 8, 5, 3, 2, 2]])
    for (let w = 6; w <= 40; w++) {
      const cells = bandCells(6, w)
      expect({ w, sum: cells.reduce((a, b) => a + b, 0), everyBand: Math.min(...cells) >= 1, tapered: cells.slice(1).every((n, i) => n <= (cells[i] ?? 0)) }).toEqual({ w, sum: w, everyBand: true, tapered: true })
    }
  })
})

const barText = (runs: { text: string }[]) => runs.map(r => r.text).join('')

describe('meterBar', () => {
  test('spans the whole window in tapered bands: used bright, ahead dim, a divider where each band starts', async () => {
    expect(meterBar(450000, M, 20)).toEqual([
      { text: '▓▓▓▓▓▓▓▓▓▓', color: 40, isDim: false },
      { text: '▌▓▓▓', color: 220, isDim: false },
      { text: '▌', color: 214, isDim: false },
      { text: '░', color: 214, isDim: true },
      { text: '▏░', color: 208, isDim: true },
      { text: '░', color: 173, isDim: true },
      { text: '░', color: 167, isDim: true },
    ])
  })
  test('fills a band in proportion to the tokens within it', async () => {
    expect([0, 100000, 200000, 280000].map(t => barText(meterBar(t, M, 30)))).toEqual([
      '░░░░░░░░░░░░░░░▏░░░░░▏░░░▏░▏░░',
      '▓▓▓▓▓▓▓░░░░░░░░▏░░░░░▏░░░▏░▏░░',
      '▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▏░░░░░▏░░░▏░▏░░',
      '▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▌▓▓░░░▏░░░▏░▏░░',
    ])
  })
  test('is exactly as wide as asked, at every width the layout gives it', async () => {
    for (const cap of [M, 200000, 0]) {
      for (let w = NARROW_BAR; w <= MAX_BAR; w++) expect({ cap, w, cells: cellWidth(barText(meterBar(120000, cap, w))) }).toEqual({ cap, w, cells: w })
    }
  })
  test('a band under 2 cells wide is marked by its colour alone, never a divider', async () => {
    expect(barText(meterBar(120000, 200000, 10))).toBe('▓▓▓▓▌▓░░░░')
    expect(meterBar(120000, 200000, 10).map(r => r.color)).toEqual([40, 220, 214, 208, 173, 167])
    expect(barText(meterBar(120000, 200000, 20))).toBe('▓▓▓▓▓▓▓▓▓▓▌▓▓▓▏░▏░░░')
  })
  test('empty, full and past the cap', async () => {
    expect(meterBar(0, M, 20).every(r => r.isDim)).toBe(true)
    expect(meterBar(M, M, 20).every(r => !r.isDim)).toBe(true)
    expect(meterBar(1200000, M, 20).every(r => !r.isDim)).toBe(true)
  })
  test('unknown cap: the 200k reference, one green band and no dividers', async () => {
    expect(meterBar(85000, 0, 10)).toEqual([
      { text: '▓▓▓▓', color: 40, isDim: false },
      { text: '░░░░░░', color: 40, isDim: true },
    ])
  })
})

describe('cellWidth and truncate', () => {
  test('wide characters take 2 cells, combining marks none, ambiguous symbols and icons 1', async () => {
    expect(['abc', '◆ ▓░▌▏·…', '機能', '👍', 'é', `${REPO_ICON}${BRANCH_ICON}`].map(cellWidth)).toEqual([3, 8, 4, 2, 1, 2])
  })
  test('cuts to the cells given, the ellipsis at the end or the start', async () => {
    expect(truncate('platform-services', 10)).toBe('platform-…')
    expect(truncate('sethcoussens/ui-676', 10, 'start')).toBe('…ns/ui-676')
    expect(truncate('機能ブランチ', 6)).toBe('機能…')
    expect(truncate('short', 10)).toBe('short')
  })
})

const H = TTL_MS['1h']
const MIN = 60000
const SRC = { at: 0, hit: 97, ttl: null, isForfeited: false }

describe('formatCache', () => {
  test('nothing before the first response', async () => {
    expect(formatCache(null, 0, H)).toBeNull()
  })
  test('warm counts down, rounding up, and colours by the share left', async () => {
    expect(formatCache(SRC, 3 * MIN, H)).toEqual({ color: 40, isWarm: true, label: 'warm 57m', hit: 'hit 97%' })
    expect(formatCache(SRC, 40 * MIN, H)?.color).toBe(220)
    expect(formatCache(SRC, 50 * MIN, H)?.color).toBe(208)
    expect(formatCache(SRC, H - 30000, H)?.label).toBe('warm 30s')
    expect(formatCache(SRC, 30000, TTL_MS['5m'])?.label).toBe('warm 5m')
  })
  test('cold once the TTL has run out, with how long ago it was used', async () => {
    expect(formatCache(SRC, H, H)).toEqual({ color: 167, isWarm: false, label: 'cold 1h ago', hit: 'hit 97%' })
    expect(formatCache(SRC, 72 * MIN, H)?.label).toBe('cold 1h 12m ago')
    expect(formatCache(SRC, 12 * MIN, TTL_MS['5m'])?.label).toBe('cold 12m ago')
  })
  test('a model switch forfeits the cache; an unknown hit rate is left out', async () => {
    expect(formatCache({ ...SRC, isForfeited: true }, MIN, H)?.label).toBe('cold (model switch)')
    expect(formatCache({ ...SRC, hit: null }, MIN, H)?.hit).toBe('')
  })
})

describe('hitPercent', () => {
  test('cache reads over all input', async () => {
    expect(hitPercent({ input_tokens: 10, cache_read_input_tokens: 970, cache_creation_input_tokens: 20 })).toBe(97)
    expect(hitPercent({ input_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 })).toBeNull()
  })
})

// The card's segments as the renderer joins them, measured independently of
// the layout's own count.
const segments = (l: Layout) => [
  l.model,
  l.meter.label + l.meter.tokens + barText(l.meter.bar) + l.meter.total + l.meter.room,
  ...(l.cache ? [l.cache.label + l.cache.warmth + l.cache.hit] : []),
  ...(l.git ? [l.git.repoIcon + l.git.repo + l.git.branchIcon + l.git.branch] : []),
]
const measured = (l: Layout) => 4 + segments(l).reduce((w, t) => w + cellWidth(t), 0) + 3 * (segments(l).length - 1)
const barCells = (l: Layout) => cellWidth(barText(l.meter.bar))

// Which optional parts a layout shows.
const parts = (l: Layout) => new Set([
  ...(l.git?.repo ? ['repo'] : []),
  ...(l.git ? ['branch'] : []),
  ...(l.cache?.hit ? ['hit'] : []),
  ...(l.meter.room ? ['room'] : []),
  ...(l.cache ? ['cache'] : []),
  ...(l.meter.label ? ['ctxLabel'] : []),
  ...(l.meter.bar.length ? ['bar'] : []),
])

describe('layout', () => {
  const s = formatStatus({ modelId: 'claude-opus-5-5', tokens: 450000, cap: M, git: GIT })
  const c = formatCache(SRC, 3 * MIN, H)
  const at = (columns: number, status: StatusSegments = s, cache: CacheSegment | null = c) => layout(status, cache, columns)

  test('a wide terminal shows everything and stretches the bar to its most', async () => {
    const l = at(200)
    expect([...parts(l)]).toEqual(['repo', 'branch', 'hit', 'room', 'cache', 'ctxLabel', 'bar'])
    expect(barCells(l)).toBe(MAX_BAR)
    expect(l.git).toEqual({ repoIcon: `${REPO_ICON} `, repo: 'platform  ', branchIcon: `${BRANCH_ICON} `, branch: 'development' })
  })
  test('the bar shrinks to its least before anything else gives way', async () => {
    expect(parts(at(116)).has('repo')).toBe(true)
    expect(barCells(at(116))).toBe(MIN_BAR)
    expect(parts(at(115)).has('repo')).toBe(false)
  })
  test('then the repo, the hit rate, the branch, the room note, the cache, in that order', async () => {
    expect([...parts(at(115))]).toEqual(['branch', 'hit', 'room', 'cache', 'ctxLabel', 'bar'])
    expect([...parts(at(103))]).toEqual(['branch', 'room', 'cache', 'ctxLabel', 'bar'])
    expect([...parts(at(93))]).toEqual(['room', 'cache', 'ctxLabel', 'bar'])
    expect([...parts(at(77))]).toEqual(['cache', 'ctxLabel', 'bar'])
    expect([...parts(at(65))]).toEqual(['ctxLabel', 'bar'])
  })
  test('the narrowest cards: a 10-cell bar, then no label, then no bar, then the model trimmed', async () => {
    expect(barCells(at(49))).toBe(MIN_BAR)
    expect(barCells(at(39))).toBe(NARROW_BAR)
    expect(at(39).meter.label).toBe('ctx ')
    expect(at(38).meter.label).toBe('')
    expect(at(33).meter).toMatchObject({ label: '', bar: [], tokens: '450k', total: '' })
    expect(at(20).model).toBe('◆ Opus 5…')
  })
  test('a long branch is trimmed from the start, a long repo from the end, before either goes', async () => {
    const long = formatStatus({ modelId: 'claude-opus-5-5', tokens: 450000, cap: M, git: { repo: 'intellilake-platform-services', branch: 'sethcoussens/ui-676-long-feature-branch' } })
    const repoTrimmed = at(155, long)
    expect(repoTrimmed.git?.repo).toMatch(/^intellilake-.*…  $/)
    expect(repoTrimmed.git?.branch).toBe('sethcoussens/ui-676-long-feature-branch')
    const branchTrimmed = at(115, long)
    expect(branchTrimmed.git?.repo).toBe('')
    expect(branchTrimmed.git?.branch).toMatch(/^….*feature-branch$/)
  })
})

describe('layout across every width', () => {
  const status = (tokens: number, cap: number, git: { repo: string; branch: string } | null) =>
    formatStatus({ modelId: 'claude-opus-5-5', tokens, cap, git })
  const STATES: [string, StatusSegments, CacheSegment | null][] = [
    ['everything', status(450000, M, GIT), formatCache(SRC, 3 * MIN, H)],
    ['long names', status(450000, M, { repo: 'intellilake-platform-services', branch: 'sethcoussens/ui-676-long-feature-branch' }), formatCache(SRC, 3 * MIN, H)],
    ['wide characters', status(450000, M, { repo: '倉庫', branch: '機能/ブランチ-テスト' }), formatCache(SRC, 3 * MIN, H)],
    ['cold cache, 200k window', status(120000, 200000, GIT), formatCache(SRC, 72 * MIN, H)],
    ['at the cap', status(M, M, GIT), formatCache({ ...SRC, isForfeited: true }, MIN, H)],
    ['no git, no cache', status(85000, M, null), null],
    ['unknown cap', status(85000, 0, null), formatCache({ ...SRC, hit: null }, MIN, H)],
  ]

  for (const [name, s, c] of STATES) {
    test(`${name}: fits, measures what it draws, and never shows less, or a shorter bar, on a wider terminal`, async () => {
      let prev: Layout | null = null
      for (let columns = 20; columns <= 200; columns++) {
        const l = layout(s, c, columns)
        const at = `${name} @ ${columns}`
        expect({ at, fits: l.width <= columns }).toEqual({ at, fits: true })
        expect({ at, width: measured(l) }).toEqual({ at, width: l.width })
        expect({ at, model: l.model.startsWith('◆ '), tokens: l.meter.tokens.trim() }).toEqual({ at, model: true, tokens: s.meter.tokens })
        const bar = barCells(l)
        expect({ at, bar: bar === 0 || (bar >= NARROW_BAR && bar <= MAX_BAR) }).toEqual({ at, bar: true })
        if (bar > 0 && bar < MIN_BAR) expect({ at, alone: l.cache === null && l.git === null && l.meter.room === '' }).toEqual({ at, alone: true })
        if (prev) {
          const lost = [...parts(prev)].filter(p => !parts(l).has(p))
          expect({ at, lost, wider: l.width >= prev.width, bar: barCells(l) >= barCells(prev) }).toEqual({ at, lost: [], wider: true, bar: true })
        }
        prev = l
      }
    })
  }
})

const wire = (on: On, tokens: number, repo: boolean) => {
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  on('session.usage', () => ({ value: { startedAt: 0, rateLimits: [], context: { tokens, window: M } } }))
  on('session.model', () => ({ value: 'claude-opus-5-5' }))
  on('session.cwd', () => ({ value: '/work/platform' }))
  on('session.repo', () => ({ value: repo ? { root: '/work/platform', remote: null, internal: false, name: null } : null }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: 'sethcoussens/ui-676\n', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return h(Text, null, 'engine') as RenderElement
  })
}

const mountBand = async ($: Engine, bodyColumns: number) => {
  const props = { hasSurvey: false, isWorking: false, maxRows: 10, bodyColumns, view: {} }
  for (let i = 0; i < 50; i++) {
    const ui = await $.ui.mount({ plugin: 'context-statusline', surface: 'terminal', component: 'AbovePrompt', props } as never)
    if (await ui.find({ type: 'Text', text: /^ctx / })) return ui
    await ui.unmount()
  }
  throw new Error('card never drew')
}

const BAR_450K = '▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▌▓▓▓▓▓▓▓▌▓░░░▏░░▏░▏░'

test('draws a rounded card above the prompt, its segments held at their width', async ($, on) => {
  wire(on, 450000, true)
  await $.session.start({ cwd: '/work/platform', surface: 'terminal', isInteractive: true })
  const ui = await mountBand($, 120)
  const card = await ui.drawn()
  expect(card).toMatchObject({ type: 'Box', props: { borderStyle: 'round', flexDirection: 'row', justifyContent: 'space-between', width: 120 } })
  expect((await ui.find({ type: 'Text', text: /^◆ / }))?.text).toBe('◆ Opus 5.5')
  expect((await ui.find({ type: 'Text', text: /^ctx / }))?.text).toBe(`ctx 450k ${BAR_450K} 1M (550k left)`)
  expect((await ui.find({ type: 'Text', text: // }))?.text).toBe(`${REPO_ICON} platform  ${BRANCH_ICON} ui-676`)
  expect(await ui.find({ type: 'Text', text: /^cache / })).toBeUndefined()
  const boxes = (await ui.findAll({ type: 'Box' })).filter(b => b.props.flexShrink !== undefined)
  expect(boxes.map(b => b.props.flexShrink)).toEqual([0, 0, 1])
  const coloured = (await ui.findAll({ type: 'Text' })).filter(t => typeof t.props.color === 'string')
  expect(coloured.map(t => [t.props.color, t.props.dimColor ?? false, t.text])).toEqual([
    ['ansi256(214)', false, '450k '],
    ['ansi256(40)', false, '▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓'],
    ['ansi256(220)', false, '▌▓▓▓▓▓▓▓'],
    ['ansi256(214)', false, '▌▓'],
    ['ansi256(214)', true, '░░░'],
    ['ansi256(208)', true, '▏░░'],
    ['ansi256(173)', true, '▏░'],
    ['ansi256(167)', true, '▏░'],
  ])
  await ui.unmount()
})

test('narrow terminal: the bar shrinks, and outside a repo there is no git segment', async ($, on) => {
  wire(on, 85000, false)
  await $.session.start({ cwd: '/tmp', surface: 'terminal', isInteractive: true })
  const ui = await mountBand($, 40)
  expect(await ui.find({ type: 'Text', text: // })).toBeUndefined()
  expect((await ui.find({ type: 'Text', text: /^ctx / }))?.text).toBe('ctx 85k ▓▓░░░░▏░░░░░ 1M')
  await ui.unmount()
})

test('counts the cache down from the last main-thread response', async ($, on) => {
  const clock = mock.clock(on, { now: 1000000 })
  wire(on, 450000, false)
  on('turn.step', async function* () {
    return { turnId: 't', index: 0, answer: 'ok', toolUses: [], stopReason: 'end_turn', usage: { model: 'claude-opus-5-5', input_tokens: 10, output_tokens: 5, cache_read_input_tokens: 970, cache_creation_input_tokens: 20 } }
  } as never)
  await $.session.start({ cwd: '/tmp', surface: 'terminal', isInteractive: true })
  const step = $.turn.step({ turnId: 't', index: 0, model: 'claude-opus-5-5', messageCount: 1 })
  for await (const _ of step) { /* drain */ }
  const ui = await mountBand($, 160)
  expect((await ui.find({ type: 'Text', text: /^cache / }))?.text).toBe('cache warm 1h · hit 97%')
  await clock.advance(61 * MIN)
  expect((await ui.find({ type: 'Text', text: /^cache / }))?.text).toBe('cache cold 1h 1m ago · hit 97%')
  await ui.unmount()
})
