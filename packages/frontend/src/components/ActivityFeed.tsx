import { useTranslation } from 'react-i18next'
import { Bell, Loader2, AlertCircle, CheckCircle2, Trash2, TrendingUp, TrendingDown, Zap } from 'lucide-react'

export type FeedItem = {
  id: string
  type: 'scanner_alert' | 'analysis_started' | 'analysis_complete' | 'error'
  ticker: string
  message: string
  timestamp: Date
  signal?: string
  confidence?: number
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
  const border = isBuy ? 'border-buy/40' : 'border-sell/40'
  const bg = isBuy ? 'bg-buy/10' : 'bg-sell/10'
  const textColor = isBuy ? 'text-buy' : 'text-sell'
  const Icon = isBuy ? TrendingUp : TrendingDown
  const label = isBuy ? t('feed.strongBuy') : t('feed.strongSell')

  return (
    <div className={`mx-2 my-1 rounded border ${border} ${bg} px-2 py-1.5`}>
      <div className="flex items-center justify-between gap-1">
        <div className="flex items-center gap-1 min-w-0">
          <Zap size={10} className={`${textColor} shrink-0`} />
          <span className={`text-[11px] font-bold ${textColor} shrink-0`}>{item.ticker}</span>
          <span className={`text-[10px] font-bold px-1 py-px rounded flex items-center gap-0.5 shrink-0 ${isBuy ? 'bg-buy/20 text-buy' : 'bg-sell/20 text-sell'}`}>
            <Icon size={9} /> {label}
          </span>
          {item.confidence != null && (
            <span className="text-[10px] text-muted">{item.confidence}%</span>
          )}
        </div>
        <span className="text-[10px] text-muted tabular-nums shrink-0">
          {item.timestamp.toLocaleTimeString()}
        </span>
      </div>
      <p className="text-[10px] text-[#d1d4dc]/70 pl-3.5 mt-0.5 leading-tight">{item.message}</p>
    </div>
  )
}

const ICONS = {
  scanner_alert: <Bell size={10} className="text-hold" />,
  analysis_started: <Loader2 size={10} className="text-accent animate-spin" />,
  analysis_complete: <CheckCircle2 size={10} className="text-buy" />,
  error: <AlertCircle size={10} className="text-sell" />,
}

export function ActivityFeed({ items, onClear }: Props) {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col h-full">
      {items.length === 0 ? (
        <p className="text-[11px] text-muted text-center py-6">{t('feed.empty')}</p>
      ) : (
        <>
          <div className="flex items-center justify-end px-3 py-1 shrink-0 border-b border-border">
            <button
              onClick={onClear}
              className="flex items-center gap-0.5 text-[10px] text-muted hover:text-sell transition-colors"
              title={t('feed.clear')}
            >
              <Trash2 size={10} /> {t('feed.clear')}
            </button>
          </div>
          <div className="flex-1 overflow-y-auto">
            {items.map((item) => {
              const strength = signalStrength(item.signal)
              if (strength !== 'normal') return <StrongSignalCard key={item.id} item={item} />
              return (
                <div key={item.id} className="flex items-start gap-1.5 px-3 py-[5px] hover:bg-panel2/50 border-b border-border/30">
                  <span className="mt-px shrink-0">{ICONS[item.type]}</span>
                  <div className="min-w-0 flex-1">
                    <span className="font-bold text-[11px] text-[#d1d4dc] mr-1">{item.ticker}</span>
                    <span className="text-[11px] text-muted">{item.message}</span>
                  </div>
                  <span className="shrink-0 text-[10px] text-muted tabular-nums">
                    {item.timestamp.toLocaleTimeString()}
                  </span>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
