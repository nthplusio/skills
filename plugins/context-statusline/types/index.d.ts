export type StatusMeter = {
  /** 256-colour index of the band the used context is in, for the token count. */
  color: number
  /** Tokens used and the window they count against; the bar is drawn from these at the width the layout gives it. */
  used: number
  cap: number
  /** Tokens used, in k: "450k". */
  tokens: string
  /** The window's size: "1M", "200k"; "" when unknown. */
  total: string
  /** Room before the real cap: "(550k left)", "(cap reached)" or "". */
  room: string
}

export type StatusSegments = {
  model: string
  meter: StatusMeter
  git: { repo: string; branch: string } | null
}

/** What the cache figures are computed from; kept across reloads. */
export type CacheSource = {
  /** When the main thread's last response arrived, ms since the epoch. */
  at: number
  /** Share of the last request's input the cache served, 0..100; null when unknown. */
  hit: number | null
  /** TTL the engine reported on a model switch; null until one did. */
  ttl: '5m' | '1h' | null
  /** A model switch forfeited the cache; cleared by the next response. */
  isForfeited: boolean
}

export type CacheSegment = {
  /** 256-colour index for the warmth label. */
  color: number
  isWarm: boolean
  /** "warm 57m", "cold 12m ago" or "cold (model switch)". */
  label: string
  /** "hit 97%", or "" when unknown. */
  hit: string
}

declare module 'claude-code' {
  interface PluginState {
    'context-statusline': {
      line: StatusSegments | null
      cacheSource: CacheSource | null
      cache: CacheSegment | null
    }
  }
}
