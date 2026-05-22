import { useState, useEffect, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Zap, Loader2, X, BarChart2, RefreshCw } from 'lucide-react'
import type { Candle } from '../types'
import { api } from '../lib/api'
import { CandleChart } from './CandleChart'

const CHART_REFRESH_MS = 5 * 60 * 1000

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
  const [chartAge, setChartAge] = useState('')
  const updatedAt = useRef<Date | null>(null)

  const fetchCandles = useCallback(() => {
    api.getCandles(ticker).then((r) => {
      setCandles(r.candles)
      updatedAt.current = new Date()
    }).catch(() => {
      setError(true)
    }).finally(() => {
      setLoading(false)
    })
  }, [ticker])

  useEffect(() => {
    setLoading(true)
    setError(false)
    setCandles([])
    fetchCandles()
    const id = setInterval(fetchCandles, CHART_REFRESH_MS)
    return () => clearInterval(id)
  }, [fetchCandles])

  useEffect(() => {
    const tick = () => {
      if (!updatedAt.current) return
      const sec = Math.floor((Date.now() - updatedAt.current.getTime()) / 1000)
      setChartAge(sec < 60 ? `${sec}s` : `${Math.floor(sec / 60)}m`)
    }
    const id = setInterval(tick, 15_000)
    return () => clearInterval(id)
  }, [])

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
          <>
            <div className="flex items-center justify-end gap-2 mb-1 text-xs text-gray-500">
              {chartAge && <span>{t('analysis.chartUpdated', { age: chartAge })}</span>}
              <button onClick={fetchCandles} className="hover:text-white transition-colors" title={t('analysis.refreshChart')}>
                <RefreshCw size={11} />
              </button>
            </div>
            <CandleChart candles={candles} />
          </>
        )}
      </div>
    </div>
  )
}
