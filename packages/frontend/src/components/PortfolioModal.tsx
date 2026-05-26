import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'
import type { OpenPosition, ClosedTrade, PortfolioSummary } from '../types'

interface Props {
  positions: OpenPosition[]
  closedTrades: ClosedTrade[]
  summary: PortfolioSummary
  onClose: (ticker: string) => void
  onDismiss: () => void
}

type Tab = 'open' | 'closed'

const EXIT_ICONS: Record<string, string> = {
  stop_loss: '🛑',
  take_profit: '🎯',
  signal_reversal: '↩',
  manual: '✋',
  max_hold: '⏱',
}

function fmt(dt: string) {
  const d = new Date(dt)
  return d.toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit' }) +
    ' ' + d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })
}

function PnlCell({ value, pct }: { value: number | null; pct: number | null }) {
  if (value === null || Math.abs(value ?? 0) < 0.01)
    return <span className="text-muted font-mono">$0.00</span>
  const pos = value >= 0
  return (
    <span className={`font-mono font-bold ${pos ? 'text-buy' : 'text-sell'}`}>
      {pos ? '+' : '-'}${Math.abs(value).toFixed(2)}
      {pct !== null && (
        <span className="font-normal text-[11px] ml-1 opacity-70">
          ({pos ? '+' : ''}{pct.toFixed(1)}%)
        </span>
      )}
    </span>
  )
}

function rowBg(pnl: number | null) {
  if (pnl === null || Math.abs(pnl) < 0.01) return ''
  return pnl > 0 ? 'bg-buy/5 border-l-2 border-l-buy' : 'bg-sell/5 border-l-2 border-l-sell'
}

export function PortfolioModal({ positions, closedTrades, summary, onClose, onDismiss }: Props) {
  const { t } = useTranslation()
  const [tab, setTab] = useState<Tab>('open')

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
      onClick={onDismiss}
    >
      <div
        className="bg-surface border border-border w-[90vw] max-w-5xl max-h-[85vh] flex flex-col overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 h-[40px] border-b border-border shrink-0">
          <div className="flex items-center gap-4">
            <span className="text-[12px] font-bold text-[#d1d4dc] uppercase tracking-wide">Portfolio</span>
            <div className="flex gap-3 text-[11px] font-mono">
              <span className={summary.total_open_pnl >= 0 ? 'text-buy' : 'text-sell'}>
                Abierto {summary.total_open_pnl >= 0 ? '+' : ''}${summary.total_open_pnl.toFixed(2)}
              </span>
              <span className={summary.total_realized_pnl >= 0 ? 'text-buy' : 'text-sell'}>
                Realizado {summary.total_realized_pnl >= 0 ? '+' : ''}${summary.total_realized_pnl.toFixed(2)}
              </span>
              <span className={`font-bold ${summary.total_pnl >= 0 ? 'text-buy' : 'text-sell'}`}>
                Total {summary.total_pnl >= 0 ? '+' : ''}${summary.total_pnl.toFixed(2)}
              </span>
            </div>
          </div>
          <button onClick={onDismiss} className="text-muted hover:text-[#d1d4dc] transition-colors">
            <X size={14} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-border shrink-0">
          {([['open', `Posiciones abiertas (${positions.length})`], ['closed', `Trades cerrados (${closedTrades.length})`]] as [Tab, string][]).map(([id, label]) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`px-4 h-[32px] text-[11px] font-medium border-b-2 transition-colors ${
                tab === id ? 'border-accent text-[#d1d4dc]' : 'border-transparent text-muted hover:text-[#d1d4dc]'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Table */}
        <div className="flex-1 overflow-y-auto">
          {tab === 'open' && (
            <table className="w-full text-[11px]">
              <thead className="sticky top-0 bg-panel border-b border-border">
                <tr className="text-muted">
                  <th className="text-left px-3 py-2 font-medium">Ticker</th>
                  <th className="text-left px-3 py-2 font-medium">Dir.</th>
                  <th className="text-left px-3 py-2 font-medium">Señal</th>
                  <th className="text-left px-3 py-2 font-medium">Apertura</th>
                  <th className="text-right px-3 py-2 font-medium">Entrada</th>
                  <th className="text-right px-3 py-2 font-medium">Actual</th>
                  <th className="text-right px-3 py-2 font-medium">Stop</th>
                  <th className="text-right px-3 py-2 font-medium">Target</th>
                  <th className="text-right px-3 py-2 font-medium">P&L</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {positions.length === 0 && (
                  <tr><td colSpan={10} className="text-center py-8 text-muted">{t('portfolio.noPositions')}</td></tr>
                )}
                {positions.map(p => (
                  <tr key={p.ticker} className={`border-b border-border/30 hover:bg-panel2/40 ${rowBg(p.unrealized_pnl)}`}>
                    <td className="px-3 py-2">
                      <div className="font-bold font-mono text-[#d1d4dc]">{p.ticker}</div>
                      <div className="text-[10px] text-muted truncate max-w-[100px]">{p.company_name}</div>
                    </td>
                    <td className="px-3 py-2">
                      <span className={`text-[10px] font-bold px-1.5 py-px ${p.direction === 'LONG' ? 'bg-buy/20 text-buy' : 'bg-sell/20 text-sell'}`}>
                        {p.direction}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-muted">{p.signal}</td>
                    <td className="px-3 py-2 text-muted tabular-nums">{fmt(p.entry_time)}</td>
                    <td className="px-3 py-2 text-right font-mono text-[#d1d4dc]">${p.entry_price.toFixed(2)}</td>
                    <td className="px-3 py-2 text-right font-mono">
                      {p.current_price
                        ? <span className="text-[#d1d4dc]">${p.current_price.toFixed(2)}</span>
                        : <span className="text-muted">—</span>
                      }
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-sell">
                      {p.stop_loss ? `$${p.stop_loss.toFixed(2)}` : <span className="text-muted">—</span>}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-buy">
                      {p.target_price ? `$${p.target_price.toFixed(2)}` : <span className="text-muted">—</span>}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <PnlCell value={p.unrealized_pnl} pct={p.unrealized_pnl_pct} />
                    </td>
                    <td className="px-3 py-2">
                      <button
                        onClick={() => onClose(p.ticker)}
                        className="text-muted hover:text-sell transition-colors text-[10px] border border-border px-1.5 py-px hover:border-sell/50"
                        title={t('portfolio.closePosition')}
                      >
                        {t('portfolio.closePosition')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {tab === 'closed' && (
            <table className="w-full text-[11px]">
              <thead className="sticky top-0 bg-panel border-b border-border">
                <tr className="text-muted">
                  <th className="text-left px-3 py-2 font-medium">Ticker</th>
                  <th className="text-left px-3 py-2 font-medium">Dir.</th>
                  <th className="text-left px-3 py-2 font-medium">Apertura</th>
                  <th className="text-left px-3 py-2 font-medium">Cierre</th>
                  <th className="text-right px-3 py-2 font-medium">Entrada</th>
                  <th className="text-right px-3 py-2 font-medium">Salida</th>
                  <th className="text-left px-3 py-2 font-medium">Motivo</th>
                  <th className="text-right px-3 py-2 font-medium">P&L</th>
                </tr>
              </thead>
              <tbody>
                {closedTrades.length === 0 && (
                  <tr><td colSpan={8} className="text-center py-8 text-muted">Sin trades cerrados</td></tr>
                )}
                {[...closedTrades].reverse().map((trade, i) => (
                  <tr key={i} className={`border-b border-border/30 hover:bg-panel2/40 ${rowBg(trade.realized_pnl)}`}>
                    <td className="px-3 py-2">
                      <div className="font-bold font-mono text-[#d1d4dc]">{trade.ticker}</div>
                      <div className="text-[10px] text-muted truncate max-w-[100px]">{trade.company_name}</div>
                    </td>
                    <td className="px-3 py-2">
                      <span className={`text-[10px] font-bold px-1.5 py-px ${trade.direction === 'LONG' ? 'bg-buy/20 text-buy' : 'bg-sell/20 text-sell'}`}>
                        {trade.direction}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-muted tabular-nums">{fmt(trade.entry_time)}</td>
                    <td className="px-3 py-2 text-muted tabular-nums">{fmt(trade.exit_time)}</td>
                    <td className="px-3 py-2 text-right font-mono text-[#d1d4dc]">${trade.entry_price.toFixed(2)}</td>
                    <td className="px-3 py-2 text-right font-mono text-[#d1d4dc]">${trade.exit_price.toFixed(2)}</td>
                    <td className="px-3 py-2">
                      <span className="text-muted">
                        {EXIT_ICONS[trade.exit_reason] ?? ''} {t(`portfolio.exit.${trade.exit_reason}`, { defaultValue: trade.exit_reason })}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <PnlCell value={trade.realized_pnl} pct={trade.realized_pnl_pct} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer stats */}
        <div className="border-t border-border px-4 h-[32px] flex items-center gap-6 text-[10px] text-muted shrink-0">
          {tab === 'open' && (
            <>
              <span>{positions.length} posiciones abiertas</span>
              <span className={summary.total_open_pnl >= 0 ? 'text-buy' : 'text-sell'}>
                P&L Abierto: {summary.total_open_pnl >= 0 ? '+' : ''}${summary.total_open_pnl.toFixed(2)}
              </span>
              <span>
                {positions.filter(p => (p.unrealized_pnl ?? 0) > 0.01).length} en ganancia ·{' '}
                {positions.filter(p => (p.unrealized_pnl ?? 0) < -0.01).length} en pérdida
              </span>
            </>
          )}
          {tab === 'closed' && (
            <>
              <span>{closedTrades.length} trades</span>
              <span className={summary.total_realized_pnl >= 0 ? 'text-buy' : 'text-sell'}>
                P&L Realizado: {summary.total_realized_pnl >= 0 ? '+' : ''}${summary.total_realized_pnl.toFixed(2)}
              </span>
              <span>
                {closedTrades.filter(t => t.realized_pnl > 0.01).length} ganadores ·{' '}
                {closedTrades.filter(t => t.realized_pnl < -0.01).length} perdedores ·{' '}
                {closedTrades.filter(t => Math.abs(t.realized_pnl) <= 0.01).length} neutros
              </span>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
