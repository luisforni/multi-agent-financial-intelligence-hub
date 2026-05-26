import { useEffect, useState } from 'react'
import { RefreshCw, TrendingUp, TrendingDown } from 'lucide-react'
import { api } from '../lib/api'
import type { AlpacaAccount } from '../lib/api'

export function AlpacaPanel() {
  const [account, setAccount] = useState<AlpacaAccount | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getAlpacaAccount()
      setAccount(data)
      setLastUpdated(new Date())
    } catch (e: any) {
      setError(e.message ?? 'Error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  if (error) {
    return (
      <div className="px-3 py-4 text-center">
        <p className="text-[11px] text-sell">Alpaca no disponible</p>
        <p className="text-[10px] text-muted mt-1">{error.includes('503') ? 'Configura ALPACA_MODE en .env' : error}</p>
      </div>
    )
  }

  const pnlPos = account ? account.pnl_today >= 0 : true

  return (
    <div className="flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-3 h-[28px] border-b border-border">
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] font-semibold text-[#d1d4dc]">Alpaca</span>
          {account && (
            <span className={`text-[9px] px-1 py-px font-bold uppercase ${
              account.mode === 'paper' ? 'bg-accent/20 text-accent' : 'bg-sell/20 text-sell'
            }`}>
              {account.mode}
            </span>
          )}
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="text-muted hover:text-[#d1d4dc] transition-colors disabled:opacity-40"
          title="Actualizar"
        >
          <RefreshCw size={10} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {!account && loading && (
        <div className="px-3 py-4 text-center text-[11px] text-muted">Cargando...</div>
      )}

      {account && (
        <>
          {/* Key metrics */}
          <div className="grid grid-cols-2 border-b border-border">
            {[
              ['Portfolio', `$${account.portfolio_value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`],
              ['Efectivo', `$${account.cash.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`],
            ].map(([label, val], i) => (
              <div key={label} className={`px-2 py-2 ${i === 0 ? 'border-r border-border' : ''}`}>
                <p className="text-[10px] text-muted">{label}</p>
                <p className="text-[12px] font-bold font-mono text-[#d1d4dc]">{val}</p>
              </div>
            ))}
          </div>

          {/* P&L hoy */}
          <div className="px-3 py-2 border-b border-border flex items-center justify-between">
            <span className="text-[10px] text-muted">P&L hoy</span>
            <span className={`flex items-center gap-0.5 font-mono text-[12px] font-bold ${pnlPos ? 'text-buy' : 'text-sell'}`}>
              {pnlPos ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
              {account.pnl_today >= 0 ? '+' : ''}${account.pnl_today.toFixed(2)}
            </span>
          </div>

          {/* Posiciones abiertas en Alpaca */}
          {account.positions.length > 0 && (
            <div>
              <div className="flex items-center justify-between px-3 h-[26px] border-b border-border">
                <span className="text-[10px] text-muted font-medium">Posiciones Alpaca</span>
                <span className="text-[10px] bg-accent/20 text-accent px-1 rounded-sm">{account.positions.length}</span>
              </div>
              {account.positions.map(p => {
                const pos = p.unrealized_pnl >= 0
                return (
                  <div key={p.ticker} className="px-3 py-1.5 flex items-center justify-between border-b border-border/40 hover:bg-panel2/30">
                    <div>
                      <div className="flex items-center gap-1">
                        <span className="font-bold text-[11px] font-mono text-[#d1d4dc]">{p.ticker}</span>
                        <span className={`text-[9px] font-bold px-1 py-px ${p.side === 'long' ? 'bg-buy/20 text-buy' : 'bg-sell/20 text-sell'}`}>
                          {p.side.toUpperCase()}
                        </span>
                      </div>
                      <div className="text-[10px] text-muted">{p.qty} acc · ${p.entry_price.toFixed(2)}</div>
                    </div>
                    <div className="text-right">
                      <div className={`font-mono text-[11px] font-bold ${pos ? 'text-buy' : 'text-sell'}`}>
                        {pos ? '+' : ''}${p.unrealized_pnl.toFixed(2)}
                      </div>
                      <div className="text-[10px] text-muted">{pos ? '+' : ''}{p.unrealized_pnl_pct.toFixed(1)}%</div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {account.positions.length === 0 && (
            <p className="text-[11px] text-muted text-center py-3">Sin posiciones en Alpaca</p>
          )}

          {lastUpdated && (
            <p className="text-[9px] text-muted text-center py-1">
              Actualizado {lastUpdated.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </p>
          )}
        </>
      )}
    </div>
  )
}
