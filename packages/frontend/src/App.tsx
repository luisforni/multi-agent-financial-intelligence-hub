import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Wifi, WifiOff, BarChart2, Briefcase, XCircle, Trash2 } from 'lucide-react'
import type { Analysis, OpenPosition, ClosedTrade, PortfolioSummary, WsEvent } from './types'
import { api } from './lib/api'
import { useWebSocket } from './hooks/useWebSocket'
import { Watchlist } from './components/Watchlist'
import { ActivityFeed, type FeedItem } from './components/ActivityFeed'
import { AnalysisCard } from './components/AnalysisCard'
import { Portfolio } from './components/Portfolio'
import { TickerPanel } from './components/TickerPanel'
import { LanguageSwitcher } from './components/LanguageSwitcher'

// ── localStorage helpers ──────────────────────────────────────────────────────

function lsGet<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch { return fallback }
}
function lsSet(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)) } catch {}
}

// ── Feed helpers ──────────────────────────────────────────────────────────────

let feedSeq = 0
function makeFeedItem(type: FeedItem['type'], ticker: string, message: string): FeedItem {
  return { id: String(++feedSeq), type, ticker, message, timestamp: new Date() }
}

const EMPTY_SUMMARY: PortfolioSummary = {
  open_count: 0, closed_count: 0,
  total_open_pnl: 0, total_realized_pnl: 0, total_pnl: 0,
}

type Tab = 'analysis' | 'portfolio'

export default function App() {
  const { t } = useTranslation()
  const [tab, setTab] = useState<Tab>(() => lsGet('tab', 'analysis'))
  const [watchlist, setWatchlist] = useState<string[]>([])
  const [selectedTicker, setSelectedTicker] = useState<string | null>(() => lsGet('selectedTicker', null))
  const [analyses, setAnalyses] = useState<Analysis[]>([])
  const [analyzing, setAnalyzing] = useState<Set<string>>(new Set())
  const [feed, setFeed] = useState<FeedItem[]>(() =>
    lsGet<Omit<FeedItem, 'timestamp'>[]>('feed', []).map(f => ({ ...f, timestamp: new Date(0) }))
  )

  // Portfolio
  const [positions, setPositions] = useState<OpenPosition[]>([])
  const [closedTrades, setClosedTrades] = useState<ClosedTrade[]>([])
  const [summary, setSummary] = useState<PortfolioSummary>(EMPTY_SUMMARY)

  // Keep positions ref for the summary updater closure
  const positionsRef = useRef(positions)
  positionsRef.current = positions

  // Persist tab + selectedTicker
  useEffect(() => { lsSet('tab', tab) }, [tab])
  useEffect(() => { lsSet('selectedTicker', selectedTicker) }, [selectedTicker])

  // Persist feed (store only last 50, without timestamp since Date serializes as string)
  useEffect(() => {
    lsSet('feed', feed.slice(0, 50).map(f => ({ ...f, timestamp: f.timestamp.toISOString() })))
  }, [feed])

  const pushFeed = useCallback((item: FeedItem) => {
    setFeed((prev) => [item, ...prev].slice(0, 50))
  }, [])

  const refreshPortfolio = useCallback(() => {
    api.getPortfolio().then((r) => {
      setPositions(r.open_positions)
      setClosedTrades(r.closed_trades)
      setSummary(r.summary)
    }).catch(() => {})
  }, [])

  const handleWsEvent = useCallback((evt: WsEvent) => {
    if (evt.type === 'scanner_alert') {
      pushFeed(makeFeedItem('scanner_alert', evt.ticker,
        t('feed.scanner', { direction: evt.direction, score: evt.score.toFixed(2), signals: evt.signals.join(', ') })))
    } else if (evt.type === 'analysis_started') {
      setAnalyzing((prev) => new Set([...prev, evt.ticker]))
      pushFeed(makeFeedItem('analysis_started', evt.ticker, t('feed.analysisStarted')))
    } else if (evt.type === 'analysis_progress') {
      pushFeed(makeFeedItem('analysis_started', evt.ticker,
        `[${t(`progress.${evt.step}`)}] ${evt.message}`))
    } else if (evt.type === 'analysis_complete') {
      setAnalyzing((prev) => { const s = new Set(prev); s.delete(evt.ticker); return s })
      setAnalyses((prev) => [evt.data, ...prev.filter((a) => a.ticker !== evt.ticker)])
      pushFeed(makeFeedItem('analysis_complete', evt.ticker,
        t('analysis.confidence', { value: Math.round(evt.data.confidence * 100) }) + ` — ${evt.data.signal}`))
    } else if (evt.type === 'error') {
      setAnalyzing((prev) => { const s = new Set(prev); s.delete(evt.ticker); return s })
      pushFeed(makeFeedItem('error', evt.ticker, evt.message))
    } else if (evt.type === 'analysis_cancelled') {
      setAnalyzing((prev) => { const s = new Set(prev); s.delete(evt.ticker); return s })
      pushFeed(makeFeedItem('error', evt.ticker, t('feed.analysisCancelled')))
    } else if (evt.type === 'position_opened') {
      pushFeed(makeFeedItem('analysis_complete', evt.ticker,
        `${evt.direction} @ $${evt.entry_price.toFixed(2)}`))
      refreshPortfolio()
      setTab('portfolio')
    } else if (evt.type === 'position_closed') {
      const pnl = evt.realized_pnl
      pushFeed(makeFeedItem(pnl >= 0 ? 'analysis_complete' : 'error', evt.ticker,
        `P&L $${pnl.toFixed(2)} (${evt.realized_pnl_pct.toFixed(1)}%) [${t(`portfolio.exit.${evt.exit_reason}`, { defaultValue: evt.exit_reason })}]`))
      refreshPortfolio()
    } else if (evt.type === 'position_update') {
      setPositions((prev) => prev.map((p) =>
        p.ticker === evt.ticker
          ? { ...p, current_price: evt.current_price, unrealized_pnl: evt.unrealized_pnl, unrealized_pnl_pct: evt.unrealized_pnl_pct }
          : p
      ))
    }
  }, [pushFeed, refreshPortfolio, t])

  const wsConnected = useWebSocket(handleWsEvent)

  // Load initial state on mount
  useEffect(() => {
    api.getWatchlist().then((r) => setWatchlist(r.tickers)).catch(() => {})
    api.getRecentAnalyses().then((r) => {
      if (r.analyses.length > 0) setAnalyses(r.analyses)
    }).catch(() => {})
    api.getActiveAnalyses().then((r) => {
      if (r.active.length > 0) setAnalyzing(new Set(r.active))
    }).catch(() => {})
    refreshPortfolio()
  }, [refreshPortfolio])

  async function handleAnalyze(ticker: string) {
    if (analyzing.has(ticker)) return
    setAnalyzing((prev) => new Set([...prev, ticker]))
    pushFeed(makeFeedItem('analysis_started', ticker, 'Analysis started…'))
    try {
      const result = await api.analyze(ticker)
      setAnalyses((prev) => [result, ...prev.filter((a) => a.ticker !== ticker)])
      pushFeed(makeFeedItem('analysis_complete', ticker,
        `${result.signal} — ${Math.round(result.confidence * 100)}% conf`))
      refreshPortfolio()
    } catch (e) {
      pushFeed(makeFeedItem('error', ticker, String(e)))
    } finally {
      setAnalyzing((prev) => { const s = new Set(prev); s.delete(ticker); return s })
    }
  }

  async function handleCancel(ticker: string) {
    try {
      await api.cancelAnalysis(ticker)
    } catch { /* 404 if already done */ }
    setAnalyzing((prev) => { const s = new Set(prev); s.delete(ticker); return s })
  }

  async function handleCancelAll() {
    try {
      await api.cancelAllAnalyses()
    } catch { /* ignore */ }
    setAnalyzing(new Set())
  }

  async function handleClearAll() {
    try {
      await api.cancelAllAnalyses()
      await api.clearAnalyses()
    } catch { /* ignore */ }
    setAnalyzing(new Set())
    setAnalyses([])
    setFeed([])
    setSelectedTicker(null)
  }

  async function handleClosePosition(ticker: string) {
    try {
      await api.closePosition(ticker)
      refreshPortfolio()
    } catch (e) {
      pushFeed(makeFeedItem('error', ticker, `Close failed: ${String(e)}`))
    }
  }

  // Scroll selected analysis card into view
  const selectedAnalysis = selectedTicker
    ? analyses.find((a) => a.ticker === selectedTicker) ?? null
    : null

  const openPnlColor = summary.total_pnl >= 0 ? 'text-buy' : 'text-sell'

  return (
    <div className="min-h-screen bg-surface text-white flex flex-col">
      {/* Header */}
      <header className="border-b border-border px-4 lg:px-6 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <BarChart2 size={20} className="text-accent" />
          <h1 className="font-bold text-base lg:text-lg">{t('app.title')}</h1>
        </div>
        <div className="flex items-center gap-2 lg:gap-3">
          {summary.total_pnl !== 0 && (
            <span className={`text-sm font-mono font-bold hidden sm:block ${openPnlColor}`}>
              {t('app.pnlLabel')} {summary.total_pnl >= 0 ? '+' : ''}${summary.total_pnl.toFixed(2)}
            </span>
          )}
          {analyzing.size > 0 && (
            <button
              onClick={handleCancelAll}
              className="flex items-center gap-1 text-xs text-sell border border-sell/40 hover:bg-sell/10 px-2 py-1 rounded-lg transition-colors"
            >
              <XCircle size={12} /> {t('btn.stopAll', { count: analyzing.size })}
            </button>
          )}
          <button
            onClick={handleClearAll}
            className="flex items-center gap-1 text-xs text-gray-500 border border-border hover:bg-white/5 px-2 py-1 rounded-lg transition-colors"
          >
            <Trash2 size={12} /> <span className="hidden sm:inline">{t('btn.reset')}</span>
          </button>
          <LanguageSwitcher />
          <div className={`flex items-center gap-1.5 text-xs ${wsConnected ? 'text-buy' : 'text-sell'}`}>
            {wsConnected ? <Wifi size={12} /> : <WifiOff size={12} />}
            <span className="hidden sm:inline">{wsConnected ? t('app.live') : t('app.reconnecting')}</span>
          </div>
        </div>
      </header>

      <div className="flex-1 max-w-7xl mx-auto w-full px-3 lg:px-4 py-4 lg:py-6 grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4 lg:gap-6 min-h-0">
        {/* Sidebar */}
        <div className="flex flex-col gap-4 min-h-0">
          <Watchlist
            tickers={watchlist}
            analyzing={analyzing}
            selectedTicker={selectedTicker}
            onAdd={(t) => setWatchlist((prev) => [...new Set([...prev, t])])}
            onRemove={(t) => { setWatchlist((prev) => prev.filter((x) => x !== t)); if (selectedTicker === t) setSelectedTicker(null) }}
            onAnalyze={handleAnalyze}
            onSelect={(t) => { setSelectedTicker(t); setTab('analysis') }}
            onCancel={handleCancel}
          />
          <ActivityFeed items={feed} onClear={() => setFeed([])} />
        </div>

        {/* Main content */}
        <div className="flex flex-col gap-4 min-h-0 overflow-y-auto">
          {/* Tabs */}
          <div className="flex gap-1 bg-panel border border-border rounded-lg p-1 w-fit shrink-0">
            {([['analysis', BarChart2, t('tab.analysis')], ['portfolio', Briefcase, t('tab.portfolio')]] as const).map(([id, Icon, label]) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={`flex items-center gap-1.5 px-3 lg:px-4 py-1.5 rounded text-sm transition-colors ${tab === id ? 'bg-accent text-white' : 'text-gray-400 hover:text-white'}`}
              >
                <Icon size={14} /> {label}
                {id === 'portfolio' && summary.open_count > 0 && (
                  <span className="bg-white/20 text-white text-xs px-1.5 rounded-full">{summary.open_count}</span>
                )}
              </button>
            ))}
          </div>

          {tab === 'analysis' && (
            <div className="space-y-3">
              {/* Selected ticker — show analysis card if available, otherwise just the chart */}
              {selectedTicker && selectedAnalysis && (
                <AnalysisCard key={`selected-${selectedAnalysis.ticker}`} analysis={selectedAnalysis} defaultExpanded={true} />
              )}
              {selectedTicker && !selectedAnalysis && (
                <TickerPanel
                  key={`panel-${selectedTicker}`}
                  ticker={selectedTicker}
                  analyzing={analyzing.has(selectedTicker)}
                  onAnalyze={() => handleAnalyze(selectedTicker)}
                  onCancel={() => handleCancel(selectedTicker)}
                />
              )}

              {!selectedTicker && analyses.length === 0 && (
                <div className="flex flex-col items-center justify-center h-48 text-gray-500 space-y-2">
                  <BarChart2 size={36} className="opacity-20" />
                  <p className="text-center text-sm">{t('analysis.empty', { count: watchlist.length })}</p>
                </div>
              )}

              {analyses
                .filter((a) => a.ticker !== selectedTicker)
                .map((a) => (
                  <AnalysisCard key={a.ticker} analysis={a} defaultExpanded={false} />
                ))}
            </div>
          )}

          {tab === 'portfolio' && (
            <Portfolio
              positions={positions}
              closedTrades={closedTrades}
              summary={summary}
              onClose={handleClosePosition}
            />
          )}
        </div>
      </div>
    </div>
  )
}
