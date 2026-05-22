import { useState, useEffect, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronUp, TrendingUp, TrendingDown, BarChart2, Clock, RefreshCw } from 'lucide-react'
import type { Analysis, Candle } from '../types'
import { api } from '../lib/api'
import { SignalBadge } from './SignalBadge'
import { ScoreBar } from './ScoreBar'
import { CandleChart } from './CandleChart'

const CHART_REFRESH_MS = 5 * 60 * 1000

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
    <div className="border border-border overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-3 py-2 hover:bg-panel2/50 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2 min-w-0">
          <div className="text-left min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="font-bold text-[13px] font-mono text-[#d1d4dc]">{a.ticker}</span>
              <SignalBadge signal={a.signal} />
              {a.chart.chart_signal && a.chart.chart_signal !== 'HOLD' && (
                <span className="text-[10px] text-muted border border-border px-1 py-px">
                  {t('analysis.chart')}: {a.chart.chart_signal}
                </span>
              )}
            </div>
            <p className="text-[11px] text-muted truncate mt-px">{a.company_name}</p>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0 ml-3">
          {a.current_price && (
            <span className="text-[12px] font-mono text-[#d1d4dc]">${a.current_price.toFixed(2)}</span>
          )}
          {priceChange !== null && (
            <span className={`text-[11px] font-mono flex items-center gap-0.5 ${priceChange >= 0 ? 'text-buy' : 'text-sell'}`}>
              {priceChange >= 0 ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
              {Math.abs(priceChange).toFixed(1)}%
            </span>
          )}
          <span className="text-[11px] text-muted">
            {t('analysis.confidence', { value: Math.round((a.confidence ?? 0) * 100) })}
          </span>
          {expanded ? <ChevronUp size={14} className="text-muted" /> : <ChevronDown size={14} className="text-muted" />}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-border px-3 pb-3 space-y-3">
          {candles.length > 0 ? (
            <div className="mt-2">
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] text-muted uppercase tracking-wide">{t('analysis.chartTitle')}</span>
                <div className="flex items-center gap-1.5 text-[10px] text-muted">
                  {chartAge && <span>{t('analysis.chartUpdated', { age: chartAge })}</span>}
                  <button
                    onClick={(e) => { e.stopPropagation(); fetchCandles() }}
                    className="hover:text-[#d1d4dc] transition-colors"
                    title={t('analysis.refreshChart')}
                  >
                    <RefreshCw size={10} />
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
            <div className="mt-2 h-12 flex items-center justify-center text-muted text-[11px]">
              <BarChart2 size={12} className="mr-1" /> {t('analysis.loadingChart')}
            </div>
          )}

          <div className="grid grid-cols-2 gap-2">
            <ScoreBar label={t('analysis.scores.technical')} value={a.scores.technical} />
            <ScoreBar label={t('analysis.scores.fundamental')} value={a.scores.fundamental} />
            <ScoreBar label={t('analysis.scores.sentiment')} value={a.scores.sentiment} />
            <ScoreBar label={t('analysis.scores.riskAdjusted')} value={a.scores.risk_adjusted} />
          </div>

          <div className="grid grid-cols-4 gap-1.5 text-center">
            {([
              [t('analysis.targets.bull'), a.targets.bull, 'text-buy'],
              [t('analysis.targets.base'), a.targets.base, 'text-[#d1d4dc]'],
              [t('analysis.targets.bear'), a.targets.bear, 'text-sell'],
              [t('analysis.targets.stop'), a.targets.stop_loss, 'text-sell'],
            ] as [string, number | null, string][]).map(([label, val, cls]) => (
              <div key={label} className="bg-surface border border-border p-1.5">
                <p className="text-[10px] text-muted">{label}</p>
                <p className={`text-[11px] font-mono font-bold ${cls}`}>
                  {val != null ? `$${val.toFixed(2)}` : '—'}
                </p>
              </div>
            ))}
          </div>

          {a.analysis.executive_summary && (
            <p className="text-[11px] text-[#d1d4dc]/80 leading-relaxed">{a.analysis.executive_summary}</p>
          )}

          {a.chart.chart_summary && (
            <div className="bg-surface border border-border p-2">
              <p className="text-[10px] font-semibold text-muted mb-1 uppercase tracking-wide">{t('analysis.chartTitle')}</p>
              <p className="text-[11px] text-[#d1d4dc]/80">{a.chart.chart_summary}</p>
              {a.chart.patterns.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1.5">
                  {a.chart.patterns.map((p) => (
                    <span key={p} className="text-[10px] bg-panel2 border border-border px-1.5 py-px text-muted">{p}</span>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="grid grid-cols-2 gap-2">
            <div className="bg-buy/5 border border-buy/20 p-2">
              <p className="text-[10px] font-semibold text-buy mb-1">{t('analysis.bullCase')}</p>
              <p className="text-[10px] text-[#d1d4dc]/70">{a.analysis.bull_case || '—'}</p>
            </div>
            <div className="bg-sell/5 border border-sell/20 p-2">
              <p className="text-[10px] font-semibold text-sell mb-1">{t('analysis.bearCase')}</p>
              <p className="text-[10px] text-[#d1d4dc]/70">{a.analysis.bear_case || '—'}</p>
            </div>
          </div>

          {(a.analysis.key_risks.length > 0 || a.analysis.key_catalysts.length > 0) && (
            <div className="grid grid-cols-2 gap-2">
              {a.analysis.key_risks.length > 0 && (
                <div>
                  <p className="text-[10px] font-semibold text-muted mb-1">{t('analysis.keyRisks')}</p>
                  <ul className="space-y-0.5">
                    {a.analysis.key_risks.map((r, i) => (
                      <li key={i} className="text-[10px] text-muted flex gap-1">
                        <span className="text-sell shrink-0">•</span>{r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {a.analysis.key_catalysts.length > 0 && (
                <div>
                  <p className="text-[10px] font-semibold text-muted mb-1">{t('analysis.catalysts')}</p>
                  <ul className="space-y-0.5">
                    {a.analysis.key_catalysts.map((c, i) => (
                      <li key={i} className="text-[10px] text-muted flex gap-1">
                        <span className="text-buy shrink-0">•</span>{c}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          <div className="flex items-center gap-1.5 text-[10px] text-muted pt-0.5">
            <Clock size={9} />
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
