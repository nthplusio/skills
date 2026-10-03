// Pure status formatting. The renderer applies colours; nothing here draws.

import type { CacheSegment, CacheSource, StatusSegments } from '../types'

export const TOP = 200000
const GREEN = 40
const RAMP = [220, 214, 208, 173, 167]

export type StatusInput = {
  modelId: string
  tokens: number
  cap: number
  git: { repo: string; branch: string } | null
}

const div = (a: number, b: number) => Math.trunc(a / b)

// claude-opus-5-5 -> Opus 5.5, claude-haiku-4-5-20251001 -> Haiku 4.5.
// Anything that does not look like a Claude model ID comes back unchanged,
// less any " (...)" suffix.
export const modelDisplayName = (id: string): string => {
  const m = /^claude-([a-z]+)((?:-\d+)+?)(?:-\d{8})?(?:\[[^\]]*\])?$/.exec(id.trim())
  if (!m || !m[1] || !m[2]) return id.replace(/ \(.*/, '')
  const family = m[1].charAt(0).toUpperCase() + m[1].slice(1)
  return `${family} ${m[2].slice(1).split('-').join('.')}`
}

// The window in bands: the target, green, then the 5-step ramp in equal
// token ranges to the cap. The target runs to the 200k reference on a larger
// window, and over the first half of a window of 200k or less. Unknown cap:
// the 200k reference, one green band.
export type Band = { from: number; to: number; color: number }

export const bands = (cap: number): Band[] => {
  if (cap <= 0) return [{ from: 0, to: TOP, color: GREEN }]
  const target = cap > TOP ? TOP : div(cap, 2)
  const step = (i: number) => target + div((cap - target) * i, RAMP.length)
  return [
    { from: 0, to: target, color: GREEN },
    ...RAMP.map((color, i) => ({ from: step(i), to: step(i + 1), color })),
  ]
}

// The band `tokens` is in; a count on a boundary belongs to the band below.
const bandIndex = (bs: Band[], tokens: number) => {
  const i = bs.findLastIndex(b => b.from < tokens)
  return Math.max(i, 0)
}

export const meterColor = (tokens: number, cap: number): number => {
  const bs = bands(cap)
  return bs[bandIndex(bs, tokens)]?.color ?? GREEN
}

// Share of the bar each band takes, in percent: the target half of it, each
// band past it less, as the context is a worse place to be.
export const SHARES = [50, 20, 12, 8, 6, 4]

// Cells per band at `width`: each band's share rounded, at least 1 cell
// while the bar has one for every band, the rounding settled on the target.
export const bandCells = (count: number, width: number): number[] => {
  const shares = count === 1 ? [100] : SHARES.slice(0, count)
  const total = shares.reduce((a, b) => a + b, 0)
  const min = width >= count ? 1 : 0
  const cells = shares.map(p => Math.max(min, Math.round((p * width) / total)))
  cells[0] = (cells[0] ?? 0) + width - cells.reduce((a, b) => a + b, 0)
  return cells
}

// One styled stretch of the bar: used cells bright, the window ahead dim.
export type BarRun = { text: string; color: number; isDim: boolean }

// `width` cells over the whole window, each band in its own share of them,
// filled across a band in proportion to the tokens used within it. A used
// cell is ▓, one ahead ░, in its band's colour; a band's first cell is a
// divider instead, ▌ used or ▏ ahead, when the band has 2 cells or more.
// Narrower, its colour change alone marks it. Runs of one style are merged.
export const meterBar = (used: number, cap: number, width: number): BarRun[] => {
  const bs = bands(cap)
  const cells = bandCells(bs.length, width)
  const starts = cells.map((_, i) => cells.slice(0, i).reduce((a, b) => a + b, 0))
  const at = bandIndex(bs, used)
  const band = bs[at]
  const filled = !band || used >= (bs.at(-1)?.to ?? 0) ? width
    : (starts[at] ?? 0) + div((cells[at] ?? 0) * (used - band.from), Math.max(band.to - band.from, 1))
  const runs: BarRun[] = []
  bs.forEach((b, bi) => {
    const n = cells[bi] ?? 0
    for (let j = 0; j < n; j++) {
      const isUsed = (starts[bi] ?? 0) + j < filled
      const glyph = bi > 0 && j === 0 && n >= 2 ? (isUsed ? '▌' : '▏') : isUsed ? '▓' : '░'
      const last = runs.at(-1)
      if (last && last.color === b.color && last.isDim === !isUsed) last.text += glyph
      else runs.push({ text: glyph, color: b.color, isDim: !isUsed })
    }
  })
  return runs
}

const k = (n: number) => `${div(n + 500, 1000)}k`

// The window's size: 1M, 1.5M, 200k.
const size = (n: number) =>
  n >= 1000000 && n % 100000 === 0 ? `${n / 1000000}M` : k(n)

export const formatStatus = ({ modelId, tokens, cap, git }: StatusInput): StatusSegments => {
  tokens = Math.max(Math.trunc(tokens), 0)
  cap = Math.max(Math.trunc(cap), 0)

  // Room is shown once past the 200k reference, or at a smaller window's cap.
  let room = ''
  if (cap > 0 && (tokens > TOP || tokens >= cap)) {
    room = tokens >= cap ? '(cap reached)' : `(${k(cap - tokens)} left)`
  }

  return {
    model: modelDisplayName(modelId),
    meter: { color: meterColor(tokens, cap), used: tokens, cap, tokens: k(tokens), total: cap > 0 ? size(cap) : '', room },
    git,
  }
}

// Prompt cache warmth. The TTL runs from the main thread's last response,
// since each cache read refreshes it; a model switch forfeits the entry.
export const TTL_MS = { '5m': 5 * 60000, '1h': 60 * 60000 } as const
const COLD = 167

// 45s, 12m, 1h, 1h 5m. Remaining time rounds up so "1m" shows until it lapses.
const duration = (ms: number, roundUp = false) => {
  const s = Math.max((roundUp ? Math.ceil : Math.floor)(ms / 1000), 0)
  if (s < 60) return `${s}s`
  const m = (roundUp ? Math.ceil : Math.floor)(s / 60)
  if (m < 60) return `${m}m`
  return m % 60 ? `${div(m, 60)}h ${m % 60}m` : `${div(m, 60)}h`
}

// Green while more than half the TTL is left, then yellow, orange below a fifth.
export const warmthColor = (left: number, ttlMs: number): number =>
  left <= 0 ? COLD : left * 2 > ttlMs ? GREEN : left * 5 > ttlMs ? 220 : 208

export const formatCache = (src: CacheSource | null, now: number, ttlMs: number): CacheSegment | null => {
  if (!src) return null
  const age = now - src.at
  const left = ttlMs - age
  const hit = src.hit === null ? '' : `hit ${src.hit}%`
  if (src.isForfeited) return { color: COLD, isWarm: false, label: 'cold (model switch)', hit }
  if (left <= 0) return { color: COLD, isWarm: false, label: `cold ${duration(age)} ago`, hit }
  return { color: warmthColor(left, ttlMs), isWarm: true, label: `warm ${duration(left, true)}`, hit }
}

// Share of a request's input the cache served, as a whole percentage.
export const hitPercent = (u: { input_tokens: number; cache_read_input_tokens: number; cache_creation_input_tokens: number }) => {
  const total = u.input_tokens + u.cache_read_input_tokens + u.cache_creation_input_tokens
  return total > 0 ? Math.round((u.cache_read_input_tokens * 100) / total) : null
}

// Terminal cells a string takes: wide East Asian characters and emoji take 2,
// combining marks, joiners and variation selectors none, everything else 1.
// Ambiguous-width symbols (◆ ▓ ░ · …) and Nerd Font icons count as 1.
const isZeroWidth = (c: number) =>
  (c >= 0x300 && c <= 0x36f) || (c >= 0x200b && c <= 0x200d) ||
  (c >= 0xfe00 && c <= 0xfe0f) || (c >= 0xe0100 && c <= 0xe01ef)

const isWide = (c: number) =>
  (c >= 0x1100 && c <= 0x115f) || (c >= 0x2e80 && c <= 0x303e) || (c >= 0x3041 && c <= 0x33ff) ||
  (c >= 0x3400 && c <= 0x4dbf) || (c >= 0x4e00 && c <= 0x9fff) || (c >= 0xa000 && c <= 0xa4cf) ||
  (c >= 0xac00 && c <= 0xd7a3) || (c >= 0xf900 && c <= 0xfaff) || (c >= 0xfe30 && c <= 0xfe4f) ||
  (c >= 0xff00 && c <= 0xff60) || (c >= 0xffe0 && c <= 0xffe6) || (c >= 0x1f300 && c <= 0x1f64f) ||
  (c >= 0x1f900 && c <= 0x1f9ff) || (c >= 0x20000 && c <= 0x3fffd)

export const cellWidth = (s: string): number => {
  let w = 0
  for (const ch of s) {
    const c = ch.codePointAt(0) ?? 0
    w += isZeroWidth(c) ? 0 : isWide(c) ? 2 : 1
  }
  return w
}

// Cuts `s` to at most `max` cells, an ellipsis marking the cut at its end or
// its start ("…ui-676": a branch's tail says the most).
export const truncate = (s: string, max: number, from: 'end' | 'start' = 'end'): string => {
  if (cellWidth(s) <= max) return s
  if (max < 1) return ''
  const chars = [...s]
  if (from === 'start') chars.reverse()
  const kept: string[] = []
  let w = 1
  for (const ch of chars) {
    const cw = cellWidth(ch)
    if (w + cw > max) break
    kept.push(ch)
    w += cw
  }
  return from === 'start' ? `…${kept.reverse().join('')}` : `${kept.join('')}…`
}

// The card as drawn: every string here is drawn verbatim, and `width` is
// measured from these same strings, so the fit cannot drift from the paint.
export type Layout = {
  model: string
  meter: { label: string; tokens: string; bar: BarRun[]; total: string; room: string; color: number }
  cache: { label: string; warmth: string; hit: string; color: number } | null
  git: { repoIcon: string; repo: string; branchIcon: string; branch: string } | null
  width: number
}

export const REPO_ICON = '\uf07c'
export const BRANCH_ICON = '\ue0a0'
// Cells a trimmed repo or branch name keeps before it is dropped instead,
// and a trimmed model name before nothing narrower is left.
export const MIN_NAME = 12
export const MIN_MODEL = 4
// The bar's width: the least it shrinks to before other parts give way, the
// least once only the model and meter are left, and the most it stretches to.
// Under 2 cells a band the dividers crowd out the fill.
export const MIN_BAR = 20
export const NARROW_BAR = 10
export const MAX_BAR = 40
// The card's frame and padding, and the least room between two segments.
const CHROME = 4
const GAP = 3

type Level = 'full' | 'trim' | 'off'
type Step = {
  repo: Level; branch: Level; model: 'full' | 'trim'
  hit: boolean; room: boolean; cache: boolean; ctxLabel: boolean; bar: boolean
  /** The bar's width at this step, and the most spare room stretches it to. */
  barWidth: number
  barGrowTo: number
}
type Names = { repo: string; branch: string; model: string }

const ALL: Step = { repo: 'full', branch: 'full', model: 'full', hit: true, room: true, cache: true, ctxLabel: true, bar: true, barWidth: MIN_BAR, barGrowTo: MAX_BAR }

// The order parts give way in, each step keeping what the last one dropped
// dropped: the bar shrinks to MIN_BAR, then the repo, the cache hit rate and
// the branch go (repo and branch trimmed first), the room note, the cache,
// the bar down to NARROW_BAR, the meter's label, the bar, and last the model
// name, trimmed. Only the full card and the model-and-meter card stretch the
// bar, each no further than the step before it drew it, so a narrower
// terminal never draws a longer bar: room a dropped part frees goes to the
// spacing.
const STEPS: Step[] = ([
  {}, { repo: 'trim', barGrowTo: MIN_BAR }, { repo: 'off' }, { branch: 'trim' },
  { branch: 'full', hit: false }, { branch: 'trim' }, { branch: 'off' },
  { room: false }, { cache: false }, { barWidth: NARROW_BAR }, { ctxLabel: false, barGrowTo: NARROW_BAR }, { bar: false }, { model: 'trim' },
] as Partial<Step>[]).reduce<Step[]>((steps, patch) => [...steps, { ...(steps.at(-1) ?? ALL), ...patch }], [])

const compose = (s: StatusSegments, c: CacheSegment | null, st: Step, names: Names, barWidth = st.barWidth): Layout => {
  const model = `◆ ${names.model}`
  const meter = {
    label: st.ctxLabel ? 'ctx ' : '',
    tokens: st.bar ? `${s.meter.tokens} ` : s.meter.tokens,
    bar: st.bar ? meterBar(s.meter.used, s.meter.cap, barWidth) : [],
    total: st.bar && s.meter.total ? ` ${s.meter.total}` : '',
    room: st.room && s.meter.room ? ` ${s.meter.room}` : '',
    color: s.meter.color,
  }
  const cache = st.cache && c
    ? { label: 'cache ', warmth: c.label, hit: st.hit && c.hit ? ` · ${c.hit}` : '', color: c.color }
    : null
  const git = s.git && s.git.branch && st.branch !== 'off'
    ? {
        repoIcon: st.repo === 'off' ? '' : `${REPO_ICON} `,
        repo: st.repo === 'off' ? '' : `${names.repo}  `,
        branchIcon: `${BRANCH_ICON} `,
        branch: names.branch,
      }
    : null
  const segments = [
    model,
    meter.label + meter.tokens + meter.bar.map(r => r.text).join('') + meter.total + meter.room,
    ...(cache ? [cache.label + cache.warmth + cache.hit] : []),
    ...(git ? [git.repoIcon + git.repo + git.branchIcon + git.branch] : []),
  ]
  const width = CHROME + segments.reduce((w, t) => w + cellWidth(t), 0) + GAP * (segments.length - 1)
  return { model, meter, cache, git, width }
}

// The fullest card that fits in `columns` cells. A trimming step gives its
// name exactly the room left, never under its minimum, so a wider terminal
// never draws less than a narrower one. Spare room goes to the bar as far as
// the step allows; the rest is spread between segments. Below the narrowest step's width the
// narrowest is returned as it is.
export const layout = (s: StatusSegments, c: CacheSegment | null, columns: number): Layout => {
  const full: Names = { repo: s.git?.repo ?? '', branch: s.git?.branch ?? '', model: s.model }
  for (const st of STEPS) {
    const l = compose(s, c, st, full)
    // Room to spare stretches the bar; the bar is back at its least before
    // any later step trims or drops a part.
    if (l.width <= columns) return st.bar ? compose(s, c, st, full, Math.min(st.barGrowTo, st.barWidth + columns - l.width)) : l
    const key = st.repo === 'trim' ? 'repo' : st.branch === 'trim' ? 'branch' : st.model === 'trim' ? 'model' : null
    if (!key) continue
    const room = cellWidth(full[key]) - (l.width - columns)
    if (room < (key === 'model' ? MIN_MODEL : MIN_NAME)) continue
    const t = compose(s, c, st, { ...full, [key]: truncate(full[key], room, key === 'branch' ? 'start' : 'end') })
    if (t.width <= columns) return t
  }
  return compose(s, c, STEPS.at(-1) ?? ALL, { ...full, model: truncate(full.model, MIN_MODEL) })
}
