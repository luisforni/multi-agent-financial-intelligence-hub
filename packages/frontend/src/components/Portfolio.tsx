import { useTranslation } from 'react-i18next'
import { TrendingUp, TrendingDown, X, DollarSign } from 'lucide-react'
import type { OpenPosition, ClosedTrade, PortfolioSummary } from '../types'

interface Props {
  positions: OpenPosition[]
  closedTrades: ClosedTrade[]
  summary: PortfolioSummary
  onClose: (ticker: string) => void
}

function PnlBadge({ value, pct }: { value: number | null; pct: number | null }) {
  if (value === null) return <span className="text-gray-500">—</span>
  const pos = value >= 0
  return (
    <span className={`flex items-center gap-0.5 font-mono text-xs ${pos ? 'text-buy' : 'text-sell'}`}>
      {pos ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
      ${Math.abs(value).toFixed(2)}
      {pct !== null && <span className="text-gray-400 ml-0.5">({pct > 0 ? '+' : ''}{pct.toFixed(1)}%)</span>}
    </span>
  )
}

function DirectionBadge({ direction }: { direction: 'LONG' | 'SHORT' }) {
  return (
    <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${direction === 'LONG' ? 'bg-buy/20 text-buy' : 'bg-sell/20 text-sell'}`}>
      {direction}
    </span>
  )
}

function ExitReasonBadge({ reason }: { reason: string }) {
  const { t } = useTranslation()
  const key = `portfolio.exit.${reason}` as const
  const label = t(key, { defaultValue: reason })
  const icons: Record<string, string> = {
    stop_loss: '🛑',
    take_profit: '🎯',
    signal_reversal: '↩',
    manual: '✋',
    max_hold: '⏱',
  }
  return <span className="text-xs text-gray-400">{icons[reason] ?? ''} {label}</span>
}

export function Portfolio({ positions, closedTrades, summary, onClose }: Props) {
  const { t } = useTranslation()

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="grid grid-cols-3 gap-3">
        {([
          [t('portfolio.openPnl'), summary.total_open_pnl],
          [t('portfolio.realizedPnl'), summary.total_realized_pnl],
          [t('portfolio.totalPnl'), summary.total_pnl],
        ] as [string, number][]).map(([label, val]) => {
          const color = val >= 0 ? 'text-buy' : 'text-sell'
          return (
            <div key={label} className="bg-panel border border-border rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500">{label}</p>
              <p className={`text-lg font-bold font-mono ${color}`}>
                {val >= 0 ? '+' : ''}${val.toFixed(2)}
              </p>
            </div>
          )
        })}
      </div>

      {/* Open positions */}
      <div className="bg-panel border border-border rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <h3 className="font-semibold text-white text-sm flex items-center gap-2">
            <DollarSign size={14} className="text-accent" />
            {t('portfolio.openPositions')}
            <span className="bg-accent/20 text-accent text-xs px-1.5 rounded">{positions.length}</span>
          </h3>
          <p className="text-xs text-gray-500">{t('portfolio.paperTrading')}</p>
        </div>

        {positions.length === 0 ? (
          <p className="text-sm text-gray-500 text-center py-6">{t('portfolio.noPositions')}</p>
        ) : (
          <div className="divide-y divide-border">
            {positions.map((p) => (
              <div key={p.ticker} className="px-4 py-3 flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="font-bold text-white font-mono">{p.ticker}</span>
                    <DirectionBadge direction={p.direction} />
                    <span className="text-xs text-gray-500">{p.signal}</span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-gray-400">
                    <span>{t('portfolio.entry')} ${p.entry_price.toFixed(2)}</span>
                    {p.current_price && <span>{t('portfolio.now')} ${p.current_price.toFixed(2)}</span>}
                    {p.stop_loss && <span className="text-sell">{t('portfolio.stop')} ${p.stop_loss.toFixed(2)}</span>}
                    {p.target_price && <span className="text-buy">{t('portfolio.target')} ${p.target_price.toFixed(2)}</span>}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <PnlBadge value={p.unrealized_pnl} pct={p.unrealized_pnl_pct} />
                  <p className="text-xs text-gray-500 mt-0.5">{p.quantity.toFixed(2)} {t('portfolio.shares')}</p>
                </div>
                <button
                  className="text-gray-500 hover:text-sell p-1 rounded transition-colors shrink-0"
                  onClick={() => onClose(p.ticker)}
                  title={t('portfolio.closePosition')}
                >
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Closed trades */}
      {closedTrades.length > 0 && (
        <div className="bg-panel border border-border rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-border">
            <h3 className="font-semibold text-white text-sm">{t('portfolio.tradeHistory')}</h3>
          </div>
          <div className="divide-y divide-border max-h-64 overflow-y-auto">
            {closedTrades.map((trade, i) => (
              <div key={i} className="px-4 py-2.5 flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-white font-mono text-sm">{trade.ticker}</span>
                    <DirectionBadge direction={trade.direction} />
                    <ExitReasonBadge reason={trade.exit_reason} />
                  </div>
                  <p className="text-xs text-gray-500 mt-0.5">
                    ${trade.entry_price.toFixed(2)} → ${trade.exit_price.toFixed(2)} · {new Date(trade.exit_time).toLocaleDateString()}
                  </p>
                </div>
                <PnlBadge value={trade.realized_pnl} pct={trade.realized_pnl_pct} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
