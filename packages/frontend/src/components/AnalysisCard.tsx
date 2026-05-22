import { useState, useEffect, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronUp, TrendingUp, TrendingDown, BarChart2, Clock, RefreshCw } from 'lucide-react'
import type { Analysis, Candle } from '../types'
import { api } from '../lib/api'
import { SignalBadge } from './SignalBadge'
import { ScoreBar } from './ScoreBar'
import { CandleChart } from './CandleChart'

const CHART_REFRESH_MS = 5 * 60 * 1000  // 5 minutes

interface Props {
  analysis: Analysis
  defaultExpanded?: boolean
}

export function AnalysisCard({ analysis: a, defaultExpanded = false }: Props) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(defaultExpanded)
  const [candles, setCandles] = useState<Candle[]>([])
  const [chartUpdatedAt, setChartUpdatedAt] = useState<Date | null>(null)
  const [chartAge, setChartAge] = useState('')
  const refreshTimer = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchCandles = useCallback(() => {
    api.getCandles(a.ticker).then((r) => {
      setCandles(r.candles)
      setChartUpdatedAt(new Date())
    }).catch(() => {})
  }, [a.ticker])

  // Fetch on first expand, then auto-refresh every 5 minutes while expanded
  useEffect(() => {
    if (!expanded) {
      if (refreshTimer.current) clearInterval(refreshTimer.current)
      return
    }
    fetchCandles()
    refreshTimer.current = setInterval(fetchCandles, CHART_REFRESH_MS)
    return () => {
      if (refreshTimer.current) clearInterval(refreshTimer.current)
    }
  }, [expanded, fetchCandles])

  // Human-readable "updated X ago" ticker
  useEffect(() => {
    if (!chartUpdatedAt) return
    const tick = () => {
      const sec = Math.floor((Date.now() - chartUpdatedAt.getTime()) / 1000)
      if (sec < 60) setChartAge(`${sec}s ago`)
      else setChartAge(`${Math.floor(sec / 60)}m ago`)
    }
    tick()
    const id = setInterval(tick, 15_000)
    return () => clearInterval(id)
  }, [chartUpdatedAt])

  const priceChange = a.current_price && a.targets.base
    ? ((a.targets.base - a.current_price) / a.current_price) * 100
    : null

  return (
    <div className="bg-panel border border-border rounded-xl overflow-hidden">
      {/* Header */}
      <button
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/5 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3 min-w-0">
          <div className="text-left min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-bold text-white">{a.ticker}</span>
              <SignalBadge signal={a.signal} />
              {a.chart.chart_signal && a.chart.chart_signal !== 'HOLD' && (
                <span className="text-xs text-gray-400 border border-border rounded px-1.5 py-0.5">
                  {t('analysis.chart')}: {a.chart.chart_signal}
                </span>
              )}
            </div>
            <p className="text-xs text-gray-400 truncate">{a.company_name}</p>
          </div>
        </div>
        <div className="flex items-center gap-4 shrink-0 ml-4">
          {a.current_price && (
            <span className="text-sm font-mono text-white">${a.current_price.toFixed(2)}</span>
          )}
          {priceChange !== null && (
            <span className={`text-xs font-mono flex items-center gap-0.5 ${priceChange >= 0 ? 'text-buy' : 'text-sell'}`}>
              {priceChange >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
              {Math.abs(priceChange).toFixed(1)}%
            </span>
          )}
          <span className="text-xs text-gray-500">
            {t('analysis.confidence', { value: Math.round((a.confidence ?? 0) * 100) })}
          </span>
          {expanded ? <ChevronUp size={16} className="text-gray-400" /> : <ChevronDown size={16} className="text-gray-400" />}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-border px-4 pb-4 space-y-4">
          {/* Chart */}
          {candles.length > 0 ? (
            <div className="mt-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-gray-500">{t('analysis.chartTitle')}</span>
                <div className="flex items-center gap-2 text-xs text-gray-500">
                  {chartAge && <span>{t('analysis.chartUpdated', { age: chartAge })}</span>}
                  <button
                    onClick={(e) => { e.stopPropagation(); fetchCandles() }}
                    className="hover:text-white transition-colors"
                    title={t('analysis.refreshChart')}
                  >
                    <RefreshCw size={11} />
                  </button>
                </div>
              </div>
              <CandleChart
                candles={candles}
                supportLevels={a.chart.support_levels}
                resistanceLevels={a.chart.resistance_levels}
              />
            </div>
          ) : (
            <div className="mt-3 h-16 flex items-center justify-center text-gray-500 text-sm">
              <BarChart2 size={14} className="mr-1" /> {t('analysis.loadingChart')}
            </div>
          )}

          {/* Scores */}
          <div className="grid grid-cols-2 gap-2">
            <ScoreBar label={t('analysis.scores.technical')} value={a.scores.technical} />
            <ScoreBar label={t('analysis.scores.fundamental')} value={a.scores.fundamental} />
            <ScoreBar label={t('analysis.scores.sentiment')} value={a.scores.sentiment} />
            <ScoreBar label={t('analysis.scores.riskAdjusted')} value={a.scores.risk_adjusted} />
          </div>

          {/* Price targets */}
          <div className="grid grid-cols-4 gap-2 text-center">
            {([
              [t('analysis.targets.bull'), a.targets.bull, 'text-buy'],
              [t('analysis.targets.base'), a.targets.base, 'text-white'],
              [t('analysis.targets.bear'), a.targets.bear, 'text-sell'],
              [t('analysis.targets.stop'), a.targets.stop_loss, 'text-red-400'],
            ] as [string, number | null, string][]).map(([label, val, cls]) => (
              <div key={label} className="bg-surface rounded p-2">
                <p className="text-xs text-gray-500">{label}</p>
                <p className={`text-sm font-mono font-bold ${cls}`}>
                  {val != null ? `$${val.toFixed(2)}` : '—'}
                </p>
              </div>
            ))}
          </div>

          {/* Executive summary */}
          {a.analysis.executive_summary && (
            <p className="text-sm text-gray-300 leading-relaxed">{a.analysis.executive_summary}</p>
          )}

          {/* Chart summary */}
          {a.chart.chart_summary && (
            <div className="bg-surface rounded p-3 border border-border">
              <p className="text-xs font-semibold text-gray-400 mb-1 uppercase tracking-wide">{t('analysis.chartTitle')}</p>
              <p className="text-sm text-gray-300">{a.chart.chart_summary}</p>
              {a.chart.patterns.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {a.chart.patterns.map((p) => (
                    <span key={p} className="text-xs bg-border px-1.5 py-0.5 rounded text-gray-400">{p}</span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Bull / Bear case */}
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-buy/10 border border-buy/20 rounded p-3">
              <p className="text-xs font-semibold text-buy mb-1">{t('analysis.bullCase')}</p>
              <p className="text-xs text-gray-300">{a.analysis.bull_case || '—'}</p>
            </div>
            <div className="bg-sell/10 border border-sell/20 rounded p-3">
              <p className="text-xs font-semibold text-sell mb-1">{t('analysis.bearCase')}</p>
              <p className="text-xs text-gray-300">{a.analysis.bear_case || '—'}</p>
            </div>
          </div>

          {/* Key risks / catalysts */}
          {(a.analysis.key_risks.length > 0 || a.analysis.key_catalysts.length > 0) && (
            <div className="grid grid-cols-2 gap-3">
              {a.analysis.key_risks.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-gray-400 mb-1">{t('analysis.keyRisks')}</p>
                  <ul className="space-y-0.5">
                    {a.analysis.key_risks.map((r, i) => (
                      <li key={i} className="text-xs text-gray-400 flex gap-1">
                        <span className="text-sell shrink-0">•</span>{r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {a.analysis.key_catalysts.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-gray-400 mb-1">{t('analysis.catalysts')}</p>
                  <ul className="space-y-0.5">
                    {a.analysis.key_catalysts.map((c, i) => (
                      <li key={i} className="text-xs text-gray-400 flex gap-1">
                        <span className="text-buy shrink-0">•</span>{c}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Footer */}
          <div className="flex items-center gap-2 text-xs text-gray-500 pt-1">
            <Clock size={10} />
            <span>{new Date(a.meta.timestamp).toLocaleString()}</span>
            {a.meta.analysis_duration_seconds && (
              <span>· {t('analysis.duration', { value: a.meta.analysis_duration_seconds })}</span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
