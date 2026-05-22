import type { Signal } from '../types'

const STYLES: Record<Signal, string> = {
  STRONG_BUY: 'bg-buy text-white',
  BUY: 'bg-buy/60 text-white',
  HOLD: 'bg-hold/20 text-hold',
  SELL: 'bg-sell/60 text-white',
  STRONG_SELL: 'bg-sell text-white',
}

export function SignalBadge({ signal }: { signal: Signal }) {
  return (
    <span className={`px-1.5 py-px text-[10px] font-bold tracking-wide uppercase rounded-sm ${STYLES[signal]}`}>
      {signal.replace('_', ' ')}
    </span>
  )
}
