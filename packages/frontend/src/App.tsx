import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Wifi, WifiOff, BarChart2, XCircle, RotateCcw } from 'lucide-react'
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
  try { const r = localStorage.getItem(key); return r ? (JSON.parse(r) as T) : fallback } catch { return fallback }
}
function lsSet(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)) } catch {}
}

let feedSeq = 0
function makeFeedItem(
  type: FeedItem['type'], ticker: string, message: string,
  extra?: { signal?: string; confidence?: number }
): FeedItem {
  return { id: String(++feedSeq), type, ticker, message, timestamp: new Date(), ...extra }
}

const EMPTY_SUMMARY: PortfolioSummary = {
  open_count: 0, closed_count: 0,
  total_open_pnl: 0, total_realized_pnl: 0, total_pnl: 0,
}

type RightTab = 'portfolio' | 'feed'

export default function App() {
  const { t } = useTranslation()
  const [watchlist, setWatchlist] = useState<string[]>([])
  const [selectedTicker, setSelectedTicker] = useState<string | null>(() => lsGet('selectedTicker', null))
  const [analyses, setAnalyses] = useState<Analysis[]>([])
  const [analyzing, setAnalyzing] = useState<Set<string>>(new Set())
  const [feed, setFeed] = useState<FeedItem[]>(() =>
    lsGet<Omit<FeedItem, 'timestamp'>[]>('feed', []).map(f => ({ ...f, timestamp: new Date(0) }))
  )
  const [rightTab, setRightTab] = useState<RightTab>(() => lsGet('rightTab', 'portfolio'))

  const [positions, setPositions] = useState<OpenPosition[]>([])
  const [closedTrades, setClosedTrades] = useState<ClosedTrade[]>([])
  const [summary, setSummary] = useState<PortfolioSummary>(EMPTY_SUMMARY)

  const positionsRef = useRef(positions)
  positionsRef.current = positions

  useEffect(() => { lsSet('selectedTicker', selectedTicker) }, [selectedTicker])
  useEffect(() => { lsSet('rightTab', rightTab) }, [rightTab])
  useEffect(() => {
    lsSet('feed', feed.slice(0, 50).map(f => ({ ...f, timestamp: f.timestamp.toISOString() })))
  }, [feed])

  const pushFeed = useCallback((item: FeedItem) => {
    setFeed(prev => [item, ...prev].slice(0, 50))
  }, [])

  const refreshPortfolio = useCallback(() => {
    api.getPortfolio().then(r => {
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
      setAnalyzing(prev => new Set([...prev, evt.ticker]))
      pushFeed(makeFeedItem('analysis_started', evt.ticker, t('feed.analysisStarted')))
    } else if (evt.type === 'analysis_progress') {
      pushFeed(makeFeedItem('analysis_started', evt.ticker,
        `[${t(`progress.${evt.step}`)}] ${evt.message}`))
    } else if (evt.type === 'analysis_complete') {
      setAnalyzing(prev => { const s = new Set(prev); s.delete(evt.ticker); return s })
      setAnalyses(prev => [evt.data, ...prev.filter(a => a.ticker !== evt.ticker)])
      const conf = Math.round(evt.data.confidence * 100)
      const sig = evt.data.signal as string
      pushFeed(makeFeedItem('analysis_complete', evt.ticker,
        t('analysis.confidence', { value: conf }) + ` — ${sig}`,
        { signal: sig, confidence: conf }))
    } else if (evt.type === 'error') {
      setAnalyzing(prev => { const s = new Set(prev); s.delete(evt.ticker); return s })
      pushFeed(makeFeedItem('error', evt.ticker, evt.message))
    } else if (evt.type === 'analysis_cancelled') {
      setAnalyzing(prev => { const s = new Set(prev); s.delete(evt.ticker); return s })
      pushFeed(makeFeedItem('error', evt.ticker, t('feed.analysisCancelled')))
    } else if (evt.type === 'position_opened') {
      pushFeed(makeFeedItem('analysis_complete', evt.ticker,
        `${evt.direction} @ $${evt.entry_price.toFixed(2)}`))
      refreshPortfolio()
      setRightTab('portfolio')
    } else if (evt.type === 'position_closed') {
      const pnl = evt.realized_pnl
      pushFeed(makeFeedItem(pnl >= 0 ? 'analysis_complete' : 'error', evt.ticker,
        `P&L $${pnl.toFixed(2)} (${evt.realized_pnl_pct.toFixed(1)}%) [${t(`portfolio.exit.${evt.exit_reason}`, { defaultValue: evt.exit_reason })}]`))
      refreshPortfolio()
    } else if (evt.type === 'position_update') {
      setPositions(prev => prev.map(p =>
        p.ticker === evt.ticker
          ? { ...p, current_price: evt.current_price, unrealized_pnl: evt.unrealized_pnl, unrealized_pnl_pct: evt.unrealized_pnl_pct }
          : p
      ))
    }
  }, [pushFeed, refreshPortfolio, t])

  const wsConnected = useWebSocket(handleWsEvent)

  useEffect(() => {
    api.getWatchlist().then(r => setWatchlist(r.tickers)).catch(() => {})
    api.getRecentAnalyses().then(r => { if (r.analyses.length > 0) setAnalyses(r.analyses) }).catch(() => {})
    api.getActiveAnalyses().then(r => { if (r.active.length > 0) setAnalyzing(new Set(r.active)) }).catch(() => {})
    refreshPortfolio()
  }, [refreshPortfolio])

  async function handleAnalyze(ticker: string) {
    if (analyzing.has(ticker)) return
    setAnalyzing(prev => new Set([...prev, ticker]))
    pushFeed(makeFeedItem('analysis_started', ticker, t('feed.analysisStarted')))
    try {
      const result = await api.analyze(ticker)
      setAnalyses(prev => [result, ...prev.filter(a => a.ticker !== ticker)])
      const conf = Math.round(result.confidence * 100)
      const sig = result.signal as string
      pushFeed(makeFeedItem('analysis_complete', ticker, `${sig} — ${conf}% conf`, { signal: sig, confidence: conf }))
      refreshPortfolio()
    } catch (e) {
      pushFeed(makeFeedItem('error', ticker, String(e)))
    } finally {
      setAnalyzing(prev => { const s = new Set(prev); s.delete(ticker); return s })
    }
  }

  async function handleCancel(ticker: string) {
    try { await api.cancelAnalysis(ticker) } catch {}
    setAnalyzing(prev => { const s = new Set(prev); s.delete(ticker); return s })
  }

  async function handleCancelAll() {
    try { await api.cancelAllAnalyses() } catch {}
    setAnalyzing(new Set())
  }

  async function handleClearAll() {
    try { await api.cancelAllAnalyses(); await api.clearAnalyses() } catch {}
    setAnalyzing(new Set()); setAnalyses([]); setFeed([]); setSelectedTicker(null)
  }

  async function handleClosePosition(ticker: string) {
    try { await api.closePosition(ticker); refreshPortfolio() }
    catch (e) { pushFeed(makeFeedItem('error', ticker, `Close failed: ${String(e)}`)) }
  }

  const selectedAnalysis = selectedTicker ? analyses.find(a => a.ticker === selectedTicker) ?? null : null
  const pnlColor = summary.total_pnl > 0 ? 'text-buy' : summary.total_pnl < 0 ? 'text-sell' : 'text-muted'

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-surface text-[#d1d4dc]">

      {/* ── Top toolbar ─────────────────────────────────────────────────────── */}
      <header className="h-[36px] shrink-0 border-b border-border bg-panel flex items-center px-3 gap-4 select-none">
        {/* Brand */}
        <div className="flex items-center gap-1.5 shrink-0">
          <BarChart2 size={14} className="text-accent" />
          <span className="font-bold text-[11px] text-[#d1d4dc] tracking-wide uppercase">{t('app.title')}</span>
        </div>

        <div className="w-px h-4 bg-border shrink-0" />

        {/* P&L summary */}
        {summary.total_pnl !== 0 && (
          <span className={`text-[11px] font-mono font-bold shrink-0 ${pnlColor}`}>
            P&L {summary.total_pnl >= 0 ? '+' : ''}${summary.total_pnl.toFixed(2)}
          </span>
        )}

        <div className="flex-1" />

        {/* Actions */}
        {analyzing.size > 0 && (
          <button
            onClick={handleCancelAll}
            className="flex items-center gap-1 text-[11px] text-sell border border-sell/30 hover:bg-sell/10 px-2 py-0.5 rounded transition-colors"
          >
            <XCircle size={11} /> {t('btn.stopAll', { count: analyzing.size })}
          </button>
        )}
        <button
          onClick={handleClearAll}
          className="flex items-center gap-1 text-[11px] text-muted border border-border hover:text-[#d1d4dc] hover:bg-panel2 px-2 py-0.5 rounded transition-colors"
        >
          <RotateCcw size={11} /> {t('btn.reset')}
        </button>

        <div className="w-px h-4 bg-border shrink-0" />
        <LanguageSwitcher />
        <div className="w-px h-4 bg-border shrink-0" />

        {/* WS status */}
        <div className={`flex items-center gap-1 text-[11px] shrink-0 ${wsConnected ? 'text-buy' : 'text-sell'}`}>
          {wsConnected ? <Wifi size={11} /> : <WifiOff size={11} />}
          <span className="hidden sm:inline">{wsConnected ? t('app.live') : t('app.reconnecting')}</span>
        </div>
      </header>

      {/* ── Body: 3-panel layout ─────────────────────────────────────────────── */}
      <div className="flex-1 flex overflow-hidden">

        {/* LEFT — Watchlist */}
        <div className="w-[200px] shrink-0 border-r border-border flex flex-col overflow-hidden bg-panel">
          <Watchlist
            tickers={watchlist}
            analyzing={analyzing}
            selectedTicker={selectedTicker}
            onAdd={t => setWatchlist(prev => [...new Set([...prev, t])])}
            onRemove={t => { setWatchlist(prev => prev.filter(x => x !== t)); if (selectedTicker === t) setSelectedTicker(null) }}
            onAnalyze={handleAnalyze}
            onSelect={t => setSelectedTicker(t)}
            onCancel={handleCancel}
            analyses={analyses}
          />
        </div>

        {/* CENTER — Analysis / Chart area */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Center content */}
          <div className="flex-1 overflow-y-auto p-2 space-y-2">
            {selectedTicker && selectedAnalysis && (
              <AnalysisCard key={`sel-${selectedAnalysis.ticker}`} analysis={selectedAnalysis} defaultExpanded={true} />
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
              <div className="h-full flex flex-col items-center justify-center text-muted space-y-2 select-none">
                <BarChart2 size={32} className="opacity-20" />
                <p className="text-[11px]">{t('analysis.empty', { count: watchlist.length })}</p>
              </div>
            )}
            {analyses
              .filter(a => a.ticker !== selectedTicker)
              .map(a => <AnalysisCard key={a.ticker} analysis={a} defaultExpanded={false} />)}
          </div>
        </div>

        {/* RIGHT — Portfolio + Feed */}
        <div className="w-[280px] shrink-0 border-l border-border flex flex-col overflow-hidden bg-panel">
          {/* Right tab bar */}
          <div className="h-[32px] shrink-0 border-b border-border flex items-stretch">
            {(['portfolio', 'feed'] as RightTab[]).map(id => (
              <button
                key={id}
                onClick={() => setRightTab(id)}
                className={`flex-1 flex items-center justify-center gap-1 text-[11px] font-medium transition-colors border-b-2 ${
                  rightTab === id
                    ? 'border-accent text-[#d1d4dc]'
                    : 'border-transparent text-muted hover:text-[#d1d4dc]'
                }`}
              >
                {id === 'portfolio' ? (
                  <>
                    {t('tab.portfolio')}
                    {summary.open_count > 0 && (
                      <span className="bg-accent/20 text-accent text-[10px] px-1 rounded">{summary.open_count}</span>
                    )}
                  </>
                ) : t('tab.feed')}
              </button>
            ))}
          </div>

          {/* Right panel content */}
          <div className="flex-1 overflow-y-auto">
            {rightTab === 'portfolio' && (
              <Portfolio
                positions={positions}
                closedTrades={closedTrades}
                summary={summary}
                onClose={handleClosePosition}
              />
            )}
            {rightTab === 'feed' && (
              <ActivityFeed items={feed} onClear={() => setFeed([])} />
            )}
          </div>
        </div>

      </div>

      {/* ── Status bar ───────────────────────────────────────────────────────── */}
      <div className="h-[22px] shrink-0 border-t border-border bg-panel flex items-center px-3 gap-4 text-[10px] text-muted select-none">
        <span>Paper trading · $10k/trade</span>
        <span className="ml-auto">{summary.open_count} {t('portfolio.openPositions').toLowerCase()} · {closedTrades.length} {t('portfolio.tradeHistory').toLowerCase()}</span>
      </div>
    </div>
  )
}
