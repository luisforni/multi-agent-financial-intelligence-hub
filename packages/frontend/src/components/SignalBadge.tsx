import type { Signal } from '../types'

const COLORS: Record<Signal, string> = {
  STRONG_BUY: 'bg-buy text-white',
  BUY: 'bg-buy/70 text-white',
  HOLD: 'bg-hold text-black',
  SELL: 'bg-sell/70 text-white',
  STRONG_SELL: 'bg-sell text-white',
}

export function SignalBadge({ signal }: { signal: Signal }) {
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-bold ${COLORS[signal]}`}>
      {signal.replace('_', ' ')}
    </span>
  )
}
