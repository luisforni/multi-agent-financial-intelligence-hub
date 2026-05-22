import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Trash2, Zap, Loader2, X } from 'lucide-react'
import type { Analysis } from '../types'
import { api } from '../lib/api'

const SIGNAL_DOT: Record<string, string> = {
  STRONG_BUY: 'bg-buy',
  BUY: 'bg-buy/60',
  HOLD: 'bg-hold',
  SELL: 'bg-sell/60',
  STRONG_SELL: 'bg-sell',
}

interface Props {
  tickers: string[]
  analyzing: Set<string>
  selectedTicker: string | null
  analyses?: Analysis[]
  onAdd: (ticker: string) => void
  onRemove: (ticker: string) => void
  onAnalyze: (ticker: string) => void
  onSelect: (ticker: string) => void
  onCancel: (ticker: string) => void
}

export function Watchlist({ tickers, analyzing, selectedTicker, analyses = [], onAdd, onRemove, onAnalyze, onSelect, onCancel }: Props) {
  const { t } = useTranslation()
  const [input, setInput] = useState('')
  const [error, setError] = useState('')

  async function handleAdd() {
    const ticker = input.trim().toUpperCase()
    if (!ticker) return
    if (!/^[A-Z]{1,10}$/.test(ticker)) { setError(t('watchlist.invalidTicker')); return }
    setError('')
    setInput('')
    try {
      await api.addTicker(ticker)
      onAdd(ticker)
    } catch (e) {
      setError(String(e))
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="h-[32px] shrink-0 border-b border-border flex items-center px-3">
        <span className="text-[11px] font-semibold text-[#d1d4dc] uppercase tracking-wide">{t('watchlist.title')}</span>
      </div>

      <div className="shrink-0 p-2 border-b border-border">
        <div className="flex gap-1">
          <input
            className="flex-1 min-w-0 h-[22px] px-2 text-[11px] rounded-sm"
            placeholder={t('watchlist.placeholder')}
            value={input}
            onChange={(e) => setInput(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
            maxLength={10}
          />
          <button
            className="flex items-center justify-center bg-accent hover:bg-accent/80 text-white text-[11px] px-2 h-[22px] rounded-sm transition-colors shrink-0"
            onClick={handleAdd}
          >
            <Plus size={11} />
          </button>
        </div>
        {error && <p className="text-[10px] text-sell mt-1 truncate">{error}</p>}
      </div>

      <div className="flex-1 overflow-y-auto">
        {tickers.length === 0 && (
          <p className="text-[11px] text-muted text-center py-4 px-2 leading-tight">{t('watchlist.noTickers')}</p>
        )}
        {tickers.map((ticker) => {
          const isAnalyzing = analyzing.has(ticker)
          const isSelected = selectedTicker === ticker
          const analysis = analyses.find(a => a.ticker === ticker)
          const dotClass = analysis ? (SIGNAL_DOT[analysis.signal] ?? 'bg-muted') : ''

          return (
            <div
              key={ticker}
              className={`flex items-center gap-1.5 px-2 h-[28px] cursor-pointer transition-colors border-l-2 select-none ${
                isSelected
                  ? 'bg-accent/10 border-l-accent'
                  : 'border-l-transparent hover:bg-panel2'
              }`}
              onClick={() => onSelect(ticker)}
            >
              {isAnalyzing
                ? <Loader2 size={8} className="animate-spin text-accent shrink-0" />
                : <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotClass || 'bg-transparent border border-border'}`} />
              }
              <span className={`font-mono font-bold text-[12px] flex-1 min-w-0 truncate ${isSelected ? 'text-accent' : 'text-[#d1d4dc]'}`}>
                {ticker}
              </span>
              <button
                className="text-muted hover:text-accent p-0.5 transition-colors shrink-0"
                onClick={(e) => { e.stopPropagation(); isAnalyzing ? onCancel(ticker) : onAnalyze(ticker) }}
                title={isAnalyzing ? t('watchlist.cancel') : t('watchlist.analyze')}
              >
                {isAnalyzing ? <X size={11} /> : <Zap size={11} />}
              </button>
              <button
                className="text-muted hover:text-sell p-0.5 transition-colors shrink-0"
                onClick={(e) => { e.stopPropagation(); api.removeTicker(ticker).then(() => onRemove(ticker)) }}
                title={t('watchlist.remove')}
              >
                <Trash2 size={11} />
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
