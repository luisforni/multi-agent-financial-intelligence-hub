import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, Download } from 'lucide-react'
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

function rowStyle(pnl: number | null, maxAbs: number): React.CSSProperties {
  if (pnl === null || Math.abs(pnl) < 0.01 || maxAbs === 0) return {}
  const intensity = Math.min(0.22, 0.05 + (Math.abs(pnl) / maxAbs) * 0.17)
  const color = pnl > 0 ? `rgba(38,166,154,${intensity})` : `rgba(239,83,80,${intensity})`
  const border = pnl > 0 ? '#26a69a' : '#ef5350'
  return { backgroundColor: color, borderLeft: `2px solid ${border}` }
}

function downloadCSV(filename: string, rows: string[][], headers: string[]) {
  const escape = (v: string) => `"${v.replace(/"/g, '""')}"`
  const lines = [headers.map(escape).join(','), ...rows.map(r => r.map(escape).join(','))]
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function PortfolioModal({ positions, closedTrades, summary, onClose, onDismiss }: Props) {
  const { t } = useTranslation()
  const [tab, setTab] = useState<Tab>('open')

  function handleDownload() {
    const ts = new Date().toISOString().slice(0, 10)
    if (tab === 'open') {
      const headers = ['Ticker', 'Empresa', 'Dirección', 'Señal', 'Apertura', 'Entrada $', 'Actual $', 'Stop $', 'Target $', 'Cantidad', 'P&L $', 'P&L %']
      const rows = sortedPositions.map(p => [
        p.ticker,
        p.company_name,
        p.direction,
        p.signal,
        p.entry_time,
        p.entry_price.toFixed(2),
        p.current_price?.toFixed(2) ?? '',
        p.stop_loss?.toFixed(2) ?? '',
        p.target_price?.toFixed(2) ?? '',
        p.quantity.toFixed(4),
        (p.unrealized_pnl ?? 0).toFixed(2),
        (p.unrealized_pnl_pct ?? 0).toFixed(2),
      ])
      downloadCSV(`portfolio_abiertas_${ts}.csv`, rows, headers)
    } else {
      const headers = ['Ticker', 'Empresa', 'Dirección', 'Apertura', 'Cierre', 'Entrada $', 'Salida $', 'Cantidad', 'P&L $', 'P&L %', 'Motivo']
      const rows = sortedTrades.map(t => [
        t.ticker,
        t.company_name,
        t.direction,
        t.entry_time,
        t.exit_time,
        t.entry_price.toFixed(2),
        t.exit_price.toFixed(2),
        t.quantity.toFixed(4),
        t.realized_pnl.toFixed(2),
        t.realized_pnl_pct.toFixed(2),
        t.exit_reason,
      ])
      downloadCSV(`portfolio_historial_${ts}.csv`, rows, headers)
    }
  }

  const sortedPositions = [...positions].sort((a, b) => (b.unrealized_pnl ?? 0) - (a.unrealized_pnl ?? 0))
  const sortedTrades = [...closedTrades].sort((a, b) => {
    const group = (pnl: number) => pnl > 0.01 ? 0 : pnl < -0.01 ? 1 : 2
    const ga = group(a.realized_pnl), gb = group(b.realized_pnl)
    if (ga !== gb) return ga - gb
    return b.realized_pnl - a.realized_pnl
  })

  const maxOpenAbs = Math.max(...positions.map(p => Math.abs(p.unrealized_pnl ?? 0)), 0.01)
  const maxClosedAbs = Math.max(...closedTrades.map(t => Math.abs(t.realized_pnl)), 0.01)

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
              {summary.equity != null && summary.initial_balance != null && (
                <>
                  <span className="text-muted">|</span>
                  <span className="text-[#d1d4dc]">Equity ${summary.equity.toFixed(2)}</span>
                  {summary.growth_pct != null && (
                    <span className={summary.growth_pct >= 0 ? 'text-buy' : 'text-sell'}>
                      {summary.growth_pct >= 0 ? '+' : ''}{summary.growth_pct.toFixed(1)}%
                    </span>
                  )}
                  {summary.drawdown_pct != null && summary.drawdown_pct > 0.1 && (
                    <span className="text-sell">DD {summary.drawdown_pct.toFixed(1)}%</span>
                  )}
                  {summary.trading_paused && (
                    <span className="text-sell font-bold animate-pulse">PAUSADO</span>
                  )}
                  {summary.market_open === false && (
                    <span className="text-muted">Mercado cerrado</span>
                  )}
                </>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleDownload}
              className="flex items-center gap-1 text-muted hover:text-[#d1d4dc] transition-colors text-[10px] border border-border px-2 py-px hover:border-accent/50"
              title="Descargar CSV"
            >
              <Download size={10} /> CSV
            </button>
            <button onClick={onDismiss} className="text-muted hover:text-[#d1d4dc] transition-colors">
              <X size={14} />
            </button>
          </div>
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
                {sortedPositions.map(p => (
                  <tr key={p.ticker} className="border-b border-border/30 hover:bg-panel2/40" style={rowStyle(p.unrealized_pnl, maxOpenAbs)}>
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
                {sortedTrades.map((trade, i) => (
                  <tr key={i} className="border-b border-border/30 hover:bg-panel2/40" style={rowStyle(trade.realized_pnl, maxClosedAbs)}>
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
              <span>{positions.length} posiciones abiertas{summary.max_positions_allowed != null ? ` / ${summary.max_positions_allowed} máx` : ''}</span>
              <span className={summary.total_open_pnl >= 0 ? 'text-buy' : 'text-sell'}>
                P&L Abierto: {summary.total_open_pnl >= 0 ? '+' : ''}${summary.total_open_pnl.toFixed(2)}
              </span>
              <span>
                {positions.filter(p => (p.unrealized_pnl ?? 0) > 0.01).length} en ganancia ·{' '}
                {positions.filter(p => (p.unrealized_pnl ?? 0) < -0.01).length} en pérdida
              </span>
              {summary.initial_balance != null && (
                <span className="text-muted">Capital inicial ${summary.initial_balance.toFixed(0)}</span>
              )}
              {summary.day_trades_remaining != null && summary.day_trades_in_window != null && (
                <span className={summary.day_trades_remaining === 0 ? 'text-sell font-bold' : summary.day_trades_remaining === 1 ? 'text-yellow-400' : 'text-muted'}>
                  PDT {summary.day_trades_in_window}/{(summary.day_trades_in_window ?? 0) + summary.day_trades_remaining} · conf min {summary.pdt_min_confidence != null ? `${Math.round(summary.pdt_min_confidence * 100)}%` : '—'}
                </span>
              )}
              {summary.next_position_size != null && (
                <span className="text-muted">Próx. pos. ${summary.next_position_size.toFixed(0)}</span>
              )}
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
