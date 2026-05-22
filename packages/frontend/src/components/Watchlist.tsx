import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Trash2, Zap, Loader2, X } from 'lucide-react'
import { api } from '../lib/api'

interface Props {
  tickers: string[]
  analyzing: Set<string>
  selectedTicker: string | null
  onAdd: (ticker: string) => void
  onRemove: (ticker: string) => void
  onAnalyze: (ticker: string) => void
  onSelect: (ticker: string) => void
  onCancel: (ticker: string) => void
}

export function Watchlist({ tickers, analyzing, selectedTicker, onAdd, onRemove, onAnalyze, onSelect, onCancel }: Props) {
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
    <div className="bg-panel border border-border rounded-xl p-4 flex flex-col gap-3">
      <h2 className="font-semibold text-white shrink-0">{t('watchlist.title')}</h2>

      <div className="flex gap-2 shrink-0">
        <input
          className="flex-1 min-w-0 bg-surface border border-border rounded-lg px-3 py-1.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-accent"
          placeholder={t('watchlist.placeholder')}
          value={input}
          onChange={(e) => setInput(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
          maxLength={10}
        />
        <button
          className="flex items-center gap-1 bg-accent hover:bg-accent/80 text-white text-sm px-3 py-1.5 rounded-lg transition-colors shrink-0"
          onClick={handleAdd}
        >
          <Plus size={14} /> {t('watchlist.add')}
        </button>
      </div>
      {error && <p className="text-xs text-sell shrink-0">{error}</p>}

      {tickers.length === 0 && (
        <p className="text-sm text-gray-500 text-center py-2">{t('watchlist.noTickers')}</p>
      )}

      <ul className="overflow-y-auto max-h-64 space-y-1 pr-0.5">
        {tickers.map((ticker) => {
          const isAnalyzing = analyzing.has(ticker)
          const isSelected = selectedTicker === ticker
          return (
            <li
              key={ticker}
              className={`flex items-center justify-between rounded-lg px-3 py-2 cursor-pointer transition-colors ${
                isSelected ? 'bg-accent/20 border border-accent/40' : 'bg-surface hover:bg-white/5'
              }`}
              onClick={() => onSelect(ticker)}
            >
              <div className="flex items-center gap-2 min-w-0">
                {isAnalyzing && <Loader2 size={10} className="animate-spin text-accent shrink-0" />}
                <span className={`font-mono font-bold text-sm ${isSelected ? 'text-accent' : 'text-white'}`}>{ticker}</span>
              </div>
              <div className="flex items-center gap-0.5 shrink-0">
                <button
                  className="text-xs text-gray-500 hover:text-accent px-1.5 py-1 rounded transition-colors disabled:opacity-30"
                  onClick={(e) => { e.stopPropagation(); isAnalyzing ? onCancel(ticker) : onAnalyze(ticker) }}
                  title={isAnalyzing ? t('watchlist.cancel') : t('watchlist.analyze')}
                >
                  {isAnalyzing ? <X size={12} /> : <Zap size={12} />}
                </button>
                <button
                  className="text-gray-500 hover:text-sell p-1 rounded transition-colors"
                  onClick={(e) => { e.stopPropagation(); api.removeTicker(ticker).then(() => onRemove(ticker)) }}
                  title={t('watchlist.remove')}
                >
                  <Trash2 size={12} />
                </button>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
