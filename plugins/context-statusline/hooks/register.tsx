import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { CacheSegment } from '../types'
import { TTL_MS, formatCache, formatStatus, hitPercent, layout } from './format.ts'

const line = atom({ plugin: 'context-statusline', key: 'line' } as const, null)
const cacheSource = atom({ plugin: 'context-statusline', key: 'cacheSource' } as const, null)
const cache = atom({ plugin: 'context-statusline', key: 'cache' } as const, null)

// How often the countdown is recomputed. A write only lands when the text changed.
const TICK_MS = 15000

const basename = (path: string) => path.trim().replace(/\/+$/, '').split('/').pop() ?? ''

// No session call gives the branch, so it comes from git in the working directory.
const branchOf = async ($: EngineInterface, cwd: string) => {
  const r = await $.process.run(['git', '--no-optional-locks', '-C', cwd, 'rev-parse', '--abbrev-ref', 'HEAD'])
  return r.exitCode === 0 ? basename(r.stdout) : ''
}

const refresh = async ($: EngineInterface) => {
  try {
    const [usage, modelId, cwd, repo] = await Promise.all([
      $.session.usage(),
      $.session.model(),
      $.session.cwd(),
      $.session.repo(),
    ])
    const branch = repo ? await branchOf($, cwd).catch(() => '') : ''
    const segments = formatStatus({
      modelId,
      tokens: usage.context.tokens ?? 0,
      cap: usage.context.window ?? 0,
      git: repo ? { repo: basename(repo.root), branch } : null,
    })
    await update($, line, () => segments)
  } catch {
    // Keep the last card if a figure is unavailable.
  }
}

const sameCache = (a: CacheSegment | null, b: CacheSegment | null) =>
  a === b || (!!a && !!b && a.label === b.label && a.hit === b.hit && a.color === b.color)

// The countdown as it reads now; written only when the text changed.
const recomputeCache = async ($: EngineInterface, configuredTtl: '5m' | '1h') => {
  try {
    const [src, now] = await Promise.all([read($, cacheSource), $.clock.now()])
    const next = formatCache(src, now, TTL_MS[src?.ttl ?? configuredTtl])
    const prev = await read($, cache)
    if (!sameCache(prev, next)) await update($, cache, () => next)
  } catch {
    // Keep the last reading if the clock or state is unavailable.
  }
}

export const register: Register = (on, options) => {
  // The engine reports the TTL only on a model switch; until then, the setting.
  const configuredTtl = options.cacheTtl === '5m' ? '5m' : '1h'

  // Module variables start over on reload, and so do the timers: one per load.
  let ticking = false

  on('session.start', async ($, e, next) => {
    const result = await next(e)
    void refresh($)
    void recomputeCache($, configuredTtl)
    if (!ticking) {
      ticking = true
      $.clock.every(TICK_MS, () => void recomputeCache($, configuredTtl))
    }
    return result
  })

  // The TTL clock starts at the main thread's last response. Subagents cache
  // their own prefixes, so their steps are left out.
  on('turn.step', async function* ($, e, next) {
    const r = yield* next(e)
    if (!e.agentId && r.usage) {
      const at = await $.clock.now()
      const hit = hitPercent(r.usage)
      await update($, cacheSource, src => ({ at, hit, ttl: src?.ttl ?? null, isForfeited: false }))
      await recomputeCache($, configuredTtl)
    }
    return r
  })

  // A resumed transcript's cache may still be warm; /clear and compaction
  // start a new prefix, so there is nothing to show until the next response.
  on('classic.SessionStart', async ($, e, next) => {
    const result = await next(e)
    if (e.seconds_since_last_response !== undefined) {
      const at = (await $.clock.now()) - e.seconds_since_last_response * 1000
      await update($, cacheSource, src => ({ at, hit: null, ttl: src?.ttl ?? null, isForfeited: false }))
    } else if (e.source === 'clear' || e.source === 'compact') {
      await update($, cacheSource, () => null)
    }
    await recomputeCache($, configuredTtl)
    return result
  })

  on('classic.PostModelSwitch', async ($, e, next) => {
    const result = await next(e)
    await update($, cacheSource, src =>
      src ? { ...src, ttl: e.cache_ttl, isForfeited: e.from_model !== e.to_model } : null)
    await recomputeCache($, configuredTtl)
    return result
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    void refresh($)
    return result
  })

  on('tool.call', async ($, e, next) => {
    const result = await next(e)
    void refresh($)
    return result
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const s = await read($, line)
    // A card stored by an older version of this module lacks the raw figures.
    if (s === null || typeof s.meter.used !== 'number' || e.props.hasSurvey || e.props.maxRows < 1) return next(e)
    const c = await read($, cache)

    const { Box, Text } = $.ui.resolve(e)
    const columns = e.props.bodyColumns
    const framed = e.props.maxRows >= 3
    // Every string drawn comes from the layout, which measured them to fit.
    const l = layout(s, c, framed ? columns : columns + 4)

    // Segments keep their width; should the measure ever be off, the git
    // segment shrinks and truncates instead of the card wrapping.
    return (
      <Box
        width={columns}
        borderStyle={framed ? 'round' : undefined}
        borderDimColor
        paddingX={framed ? 1 : 0}
        flexDirection="row"
        justifyContent="space-between"
      >
        <Box flexShrink={0}>
          <Text bold>{l.model}</Text>
        </Box>
        <Box flexShrink={0}>
          <Text wrap="truncate-end">
            {l.meter.label ? <Text dimColor>{l.meter.label}</Text> : null}
            <Text color={`ansi256(${l.meter.color})`}>{l.meter.tokens}</Text>
            {l.meter.bar.map(r => <Text color={`ansi256(${r.color})`} dimColor={r.isDim}>{r.text}</Text>)}
            {l.meter.total ? <Text dimColor>{l.meter.total}</Text> : null}
            {l.meter.room ? <Text dimColor>{l.meter.room}</Text> : null}
          </Text>
        </Box>
        {l.cache ? (
          <Box flexShrink={0}>
            <Text wrap="truncate-end">
              <Text dimColor>{l.cache.label}</Text>
              <Text color={`ansi256(${l.cache.color})`}>{l.cache.warmth}</Text>
              {l.cache.hit ? <Text dimColor>{l.cache.hit}</Text> : null}
            </Text>
          </Box>
        ) : null}
        {l.git ? (
          <Box flexShrink={1} minWidth={0}>
            <Text wrap="truncate-start">
              {l.git.repoIcon ? <Text dimColor>{l.git.repoIcon}</Text> : null}
              {l.git.repo ? <Text>{l.git.repo}</Text> : null}
              <Text dimColor>{l.git.branchIcon}</Text>
              <Text>{l.git.branch}</Text>
            </Text>
          </Box>
        ) : null}
      </Box>
    )
  })
}
