interface Props {
  label: string
  value: number | null
}

export function ScoreBar({ label, value }: Props) {
  const pct = value ?? 0
  const color = pct >= 65 ? 'bg-buy' : pct >= 40 ? 'bg-hold' : 'bg-sell'
  return (
    <div className="space-y-0.5">
      <div className="flex justify-between text-xs text-gray-400">
        <span>{label}</span>
        <span className="font-mono">{value != null ? Math.round(value) : '—'}</span>
      </div>
      <div className="h-1.5 rounded bg-border overflow-hidden">
        <div className={`h-full rounded ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
