import { useTranslation } from 'react-i18next'
import { Bell, Loader2, AlertCircle, CheckCircle2, Trash2 } from 'lucide-react'

export type FeedItem = {
  id: string
  type: 'scanner_alert' | 'analysis_started' | 'analysis_complete' | 'error'
  ticker: string
  message: string
  timestamp: Date
}

interface Props {
  items: FeedItem[]
  onClear: () => void
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
        {items.map((item) => (
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
        ))}
      </ul>
    </div>
  )
}
