import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Zap, Loader2, X, BarChart2 } from 'lucide-react'
import type { Candle } from '../types'
import { api } from '../lib/api'
import { CandleChart } from './CandleChart'

interface Props {
  ticker: string
  analyzing: boolean
  onAnalyze: () => void
  onCancel: () => void
}

export function TickerPanel({ ticker, analyzing, onAnalyze, onCancel }: Props) {
  const { t } = useTranslation()
  const [candles, setCandles] = useState<Candle[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    setLoading(true)
    setError(false)
    setCandles([])
    api.getCandles(ticker).then((r) => {
      setCandles(r.candles)
    }).catch(() => {
      setError(true)
    }).finally(() => {
      setLoading(false)
    })
  }, [ticker])

  return (
    <div className="bg-panel border border-border rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <span className="font-bold text-white text-lg">{ticker}</span>
          {analyzing && (
            <span className="flex items-center gap-1 text-xs text-accent">
              <Loader2 size={10} className="animate-spin" /> {t('ticker.analyzing')}
            </span>
          )}
        </div>
        <button
          onClick={analyzing ? onCancel : onAnalyze}
          className={`flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg transition-colors ${
            analyzing
              ? 'bg-sell/20 text-sell hover:bg-sell/30'
              : 'bg-accent hover:bg-accent/80 text-white'
          }`}
        >
          {analyzing
            ? <><X size={12} /> {t('ticker.cancel')}</>
            : <><Zap size={12} /> {t('ticker.analyze')}</>
          }
        </button>
      </div>

      <div className="p-4">
        {loading && (
          <div className="h-64 flex items-center justify-center text-gray-500 text-sm gap-2">
            <Loader2 size={14} className="animate-spin" /> {t('ticker.loadingChart')}
          </div>
        )}
        {!loading && error && (
          <div className="h-64 flex items-center justify-center text-gray-500 text-sm gap-2">
            <BarChart2 size={14} /> {t('ticker.chartError')}
          </div>
        )}
        {!loading && candles.length > 0 && (
          <CandleChart candles={candles} />
        )}
      </div>
    </div>
  )
}
