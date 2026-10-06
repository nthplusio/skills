// What the inbox view draws: never message text, only routing facts.
export type InboxThreadState = 'leased-here' | 'waiting' | 'held-elsewhere' | 'delivered'
export type InboxThread = {
  thread: string
  state: InboxThreadState
  // The other role in the thread, and whether its latest message was sent to it.
  peer: string
  outgoing: boolean
  kind: string
  // When its latest message was accepted; absent for a waiting message whose receipt was not read.
  at?: string
  expiresAt?: string
}
export type InboxView =
  | { state: 'connecting' }
  | { state: 'unbound' }
  | { state: 'unavailable'; reason: string }
  | { state: 'ready'; role: string; waiting: number; leasedHere: { expiresAt: string } | null; heldElsewhere: number; threads: InboxThread[] }

declare module 'claude-code' {
  interface PluginState {
    doorbell: { view: InboxView }
  }
}
