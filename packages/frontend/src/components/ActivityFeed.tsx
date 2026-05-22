import { useTranslation } from 'react-i18next'
import { Bell, Loader2, AlertCircle, CheckCircle2, Trash2, TrendingUp, TrendingDown, Zap } from 'lucide-react'

export type FeedItem = {
  id: string
  type: 'scanner_alert' | 'analysis_started' | 'analysis_complete' | 'error'
  ticker: string
  message: string
  timestamp: Date
  signal?: string   // e.g. "STRONG_BUY", "STRONG_SELL", "BUY", "SELL", "HOLD"
  confidence?: number  // 0–100
}

type SignalStrength = 'strong_buy' | 'strong_sell' | 'normal'

function signalStrength(signal?: string): SignalStrength {
  if (signal === 'STRONG_BUY') return 'strong_buy'
  if (signal === 'STRONG_SELL') return 'strong_sell'
  return 'normal'
}

interface Props {
  items: FeedItem[]
  onClear: () => void
}

function StrongSignalCard({ item }: { item: FeedItem }) {
  const { t } = useTranslation()
  const isBuy = item.signal === 'STRONG_BUY'
  const border = isBuy ? 'border-buy/50' : 'border-sell/50'
  const bg = isBuy ? 'bg-buy/10' : 'bg-sell/10'
  const textColor = isBuy ? 'text-buy' : 'text-sell'
  const Icon = isBuy ? TrendingUp : TrendingDown
  const label = isBuy ? t('feed.strongBuy') : t('feed.strongSell')

  return (
    <li className={`rounded-lg border ${border} ${bg} px-3 py-2 space-y-1`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Zap size={12} className={`${textColor} shrink-0`} />
          <span className={`text-sm font-bold ${textColor}`}>{item.ticker}</span>
          <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${isBuy ? 'bg-buy/20 text-buy' : 'bg-sell/20 text-sell'} flex items-center gap-1`}>
            <Icon size={10} /> {label}
          </span>
          {item.confidence != null && (
            <span className="text-xs text-gray-400">{item.confidence}%</span>
          )}
        </div>
        <span className="text-xs text-gray-500 tabular-nums shrink-0 ml-2">
          {item.timestamp.toLocaleTimeString()}
        </span>
      </div>
      <p className="text-xs text-gray-300 pl-4">{item.message}</p>
    </li>
  )
}

const ICONS = {
  scanner_alert: <Bell size={12} className="text-hold" />,
  analysis_started: <Loader2 size={12} className="text-accent animate-spin" />,
  analysis_complete: <CheckCircle2 size={12} className="text-buy" />,
  error: <AlertCircle size={12} className="text-sell" />,
}

export function ActivityFeed({ items, onClear }: Props) {
  const { t } = useTranslation()

  return (
    <div className="bg-panel border border-border rounded-xl p-4 space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-white flex items-center gap-2">
          <Bell size={14} /> {t('feed.title')}
        </h2>
        {items.length > 0 && (
          <button
            onClick={onClear}
            className="flex items-center gap-1 text-xs text-gray-500 hover:text-sell transition-colors"
            title={t('feed.clear')}
          >
            <Trash2 size={11} /> {t('feed.clear')}
          </button>
        )}
      </div>
      {items.length === 0 && (
        <p className="text-sm text-gray-500 text-center py-2">{t('feed.empty')}</p>
      )}
      <ul className="space-y-1.5 max-h-64 overflow-y-auto">
        {items.map((item) => {
          const strength = signalStrength(item.signal)
          if (strength !== 'normal') return <StrongSignalCard key={item.id} item={item} />
          return (
            <li key={item.id} className="flex items-start gap-2 text-xs">
              <span className="mt-0.5 shrink-0">{ICONS[item.type]}</span>
              <div className="min-w-0">
                <span className="font-bold text-white mr-1">{item.ticker}</span>
                <span className="text-gray-400">{item.message}</span>
              </div>
              <span className="shrink-0 text-gray-600 ml-auto tabular-nums">
                {item.timestamp.toLocaleTimeString()}
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
