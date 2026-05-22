interface Props {
  label: string
  value: number | null
}

export function ScoreBar({ label, value }: Props) {
  const pct = value ?? 0
  const color = pct >= 65 ? 'bg-buy' : pct >= 40 ? 'bg-hold' : 'bg-sell'
  return (
    <div className="space-y-px">
      <div className="flex justify-between text-[11px] text-muted">
        <span>{label}</span>
        <span className="font-mono">{value != null ? Math.round(value) : '—'}</span>
      </div>
      <div className="h-1 bg-panel2 overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
