import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { TrendingUp, TrendingDown, X, DollarSign, Maximize2 } from 'lucide-react'
import type { OpenPosition, ClosedTrade, PortfolioSummary } from '../types'
import { PortfolioModal } from './PortfolioModal'

interface Props {
  positions: OpenPosition[]
  closedTrades: ClosedTrade[]
  summary: PortfolioSummary
  onClose: (ticker: string) => void
}

function PnlBadge({ value, pct }: { value: number | null; pct: number | null }) {
  if (value === null) return <span className="text-muted">—</span>
  if (Math.abs(value) < 0.01) return <span className="text-muted font-mono text-[11px]">$0.00</span>
  const pos = value >= 0
  return (
    <span className={`flex items-center gap-0.5 font-mono text-[11px] ${pos ? 'text-buy' : 'text-sell'}`}>
      {pos ? <TrendingUp size={9} /> : <TrendingDown size={9} />}
      {pos ? '+' : '-'}${Math.abs(value).toFixed(2)}
      {pct !== null && <span className="text-muted ml-0.5">({Math.abs(pct).toFixed(1)}%)</span>}
    </span>
  )
}

function DirectionBadge({ direction }: { direction: 'LONG' | 'SHORT' }) {
  return (
    <span className={`text-[10px] font-bold px-1 py-px ${direction === 'LONG' ? 'bg-buy/20 text-buy' : 'bg-sell/20 text-sell'}`}>
      {direction}
    </span>
  )
}

function ExitReasonBadge({ reason }: { reason: string }) {
  const { t } = useTranslation()
  const label = t(`portfolio.exit.${reason}`, { defaultValue: reason })
  const icons: Record<string, string> = {
    stop_loss: '🛑', take_profit: '🎯', signal_reversal: '↩', manual: '✋', max_hold: '⏱',
  }
  return <span className="text-[10px] text-muted">{icons[reason] ?? ''} {label}</span>
}

export function Portfolio({ positions, closedTrades, summary, onClose }: Props) {
  const { t } = useTranslation()
  const allFlat = summary.total_pnl === 0 && positions.length > 0
  const [showModal, setShowModal] = useState(false)

  return (
    <div className="flex flex-col">
      {showModal && (
        <PortfolioModal
          positions={positions}
          closedTrades={closedTrades}
          summary={summary}
          onClose={(ticker) => { onClose(ticker) }}
          onDismiss={() => setShowModal(false)}
        />
      )}
      {/* Expand button */}
      <div className="flex items-center justify-end px-3 py-1 border-b border-border">
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-1 text-[10px] text-muted hover:text-[#d1d4dc] transition-colors"
          title="Ver detalle completo"
        >
          <Maximize2 size={10} /> Ver detalle
        </button>
      </div>

      {/* Summary strip */}
      <div className="grid grid-cols-3 border-b border-border">
        {([
          [t('portfolio.openPnl'), summary.total_open_pnl],
          [t('portfolio.realizedPnl'), summary.total_realized_pnl],
          [t('portfolio.totalPnl'), summary.total_pnl],
        ] as [string, number][]).map(([label, val], i) => {
          const color = val === 0 ? 'text-muted' : val > 0 ? 'text-buy' : 'text-sell'
          return (
            <div key={label} className={`px-2 py-2 text-center ${i < 2 ? 'border-r border-border' : ''}`}>
              <p className="text-[10px] text-muted">{label}</p>
              <p className={`text-[12px] font-bold font-mono ${color}`}>
                {val > 0 ? '+' : ''}${val.toFixed(2)}
              </p>
            </div>
          )
        })}
      </div>
      {allFlat && (
        <p className="text-[10px] text-muted text-center py-1 border-b border-border bg-panel2/30">
          {t('portfolio.pricesUpdatingNote')}
        </p>
      )}

      {/* Open positions section */}
      <div className="border-b border-border">
        <div className="flex items-center justify-between px-3 h-[28px]">
          <span className="text-[11px] font-semibold text-[#d1d4dc] flex items-center gap-1">
            <DollarSign size={11} className="text-accent" />
            {t('portfolio.openPositions')}
          </span>
          {positions.length > 0 && (
            <span className="bg-accent/20 text-accent text-[10px] px-1 rounded-sm">{positions.length}</span>
          )}
        </div>

        {positions.length === 0 ? (
          <p className="text-[11px] text-muted text-center py-4">{t('portfolio.noPositions')}</p>
        ) : (
          <div>
            {positions.map((p) => (
              <div key={p.ticker} className="px-3 py-1.5 flex items-start gap-2 border-t border-border/50 hover:bg-panel2/30">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <span className="font-bold text-[12px] font-mono text-[#d1d4dc]">{p.ticker}</span>
                    <DirectionBadge direction={p.direction} />
                    <span className="text-[10px] text-muted">{p.signal}</span>
                  </div>
                  <div className="flex flex-wrap gap-x-2 text-[10px] text-muted">
                    <span>{t('portfolio.entry')} ${p.entry_price.toFixed(2)}</span>
                    {p.current_price && <span>{t('portfolio.now')} ${p.current_price.toFixed(2)}</span>}
                    {p.stop_loss && <span className="text-sell">{t('portfolio.stop')} ${p.stop_loss.toFixed(2)}</span>}
                    {p.target_price && <span className="text-buy">{t('portfolio.target')} ${p.target_price.toFixed(2)}</span>}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <PnlBadge value={p.unrealized_pnl} pct={p.unrealized_pnl_pct} />
                  <p className="text-[10px] text-muted mt-px">{p.quantity.toFixed(2)} {t('portfolio.shares')}</p>
                </div>
                <button
                  className="text-muted hover:text-sell p-0.5 transition-colors shrink-0 mt-px"
                  onClick={() => onClose(p.ticker)}
                  title={t('portfolio.closePosition')}
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Closed trades */}
      {closedTrades.length > 0 && (
        <div>
          <div className="flex items-center px-3 h-[28px] border-b border-border">
            <span className="text-[11px] font-semibold text-[#d1d4dc]">{t('portfolio.tradeHistory')}</span>
          </div>
          <div>
            {closedTrades.map((trade, i) => (
              <div key={i} className="px-3 py-1.5 flex items-center gap-2 border-b border-border/50 hover:bg-panel2/30">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="font-bold text-[12px] font-mono text-[#d1d4dc]">{trade.ticker}</span>
                    <DirectionBadge direction={trade.direction} />
                    <ExitReasonBadge reason={trade.exit_reason} />
                  </div>
                  <p className="text-[10px] text-muted mt-px">
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
