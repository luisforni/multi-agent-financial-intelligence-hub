export type Signal = 'STRONG_BUY' | 'BUY' | 'HOLD' | 'SELL' | 'STRONG_SELL'
export type Direction = 'LONG' | 'SHORT'

export interface ChartPattern {
  name: string
  confidence: number
  implication: 'bullish' | 'bearish'
}

export interface Analysis {
  ticker: string
  company_name: string
  signal: Signal
  confidence: number
  risk_level: string
  current_price: number | null
  targets: {
    bull: number | null
    base: number | null
    bear: number | null
    stop_loss: number | null
  }
  time_horizon_days: number
  scores: {
    technical: number | null
    fundamental: number | null
    sentiment: number | null
    risk_adjusted: number | null
  }
  analysis: {
    executive_summary: string
    bull_case: string
    bear_case: string
    key_risks: string[]
    key_catalysts: string[]
  }
  chart: {
    trend: string | null
    trend_strength: string | null
    chart_signal: string | null
    chart_confidence: number | null
    patterns: string[]
    support_levels: number[]
    resistance_levels: number[]
    chart_summary: string | null
  }
  sentiment: {
    label: string | null
    overall_score: number | null
  }
  meta: {
    agents_used: string[]
    timestamp: string
    analysis_duration_seconds: number | null
  }
}

export interface Candle {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface OpenPosition {
  ticker: string
  company_name: string
  direction: Direction
  entry_price: number
  current_price: number | null
  quantity: number
  stop_loss: number | null
  target_price: number | null
  unrealized_pnl: number | null
  unrealized_pnl_pct: number | null
  entry_time: string
  signal: string
}

export interface ClosedTrade {
  ticker: string
  company_name: string
  direction: Direction
  entry_price: number
  exit_price: number
  quantity: number
  realized_pnl: number
  realized_pnl_pct: number
  exit_reason: string
  entry_time: string
  exit_time: string
}

export interface PortfolioSummary {
  open_count: number
  closed_count: number
  total_open_pnl: number
  total_realized_pnl: number
  total_pnl: number
  equity?: number
  initial_balance?: number
  peak_equity?: number
  drawdown_pct?: number
  growth_pct?: number
  trading_paused?: boolean
  market_open?: boolean
  max_positions_allowed?: number
  day_trades_in_window?: number
  day_trades_remaining?: number
  pdt_min_confidence?: number
  unsettled_cash?: number
  slippage_pct?: number
  next_position_size?: number
}

export type WsEvent =
  | { type: 'connected'; clients: number }
  | { type: 'scanner_alert'; ticker: string; direction: string; score: number; signals: string[]; price: number; timestamp: string }
  | { type: 'analysis_started'; ticker: string }
  | { type: 'analysis_progress'; ticker: string; step: 'market_data' | 'sentiment' | 'chart' | 'risk'; message: string }
  | { type: 'analysis_complete'; ticker: string; data: Analysis }
  | { type: 'error'; ticker: string; message: string }
  | { type: 'position_opened'; ticker: string; direction: Direction; entry_price: number; quantity: number; stop_loss: number | null; target_price: number | null; signal: string }
  | { type: 'position_closed'; ticker: string; exit_price: number; realized_pnl: number; realized_pnl_pct: number; exit_reason: string }
  | { type: 'position_update'; ticker: string; current_price: number; unrealized_pnl: number | null; unrealized_pnl_pct: number | null }
  | { type: 'analysis_cancelled'; ticker: string }
  | { type: 'portfolio_reset' }
