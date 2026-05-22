import { useTranslation } from 'react-i18next'
import { Globe } from 'lucide-react'
import { LANGUAGES, setLanguage, type LangCode } from '../i18n'

export function LanguageSwitcher() {
  const { i18n } = useTranslation()

  return (
    <div className="flex items-center gap-1 text-gray-400">
      <Globe size={12} className="shrink-0" />
      <select
        value={i18n.language}
        onChange={(e) => setLanguage(e.target.value as LangCode)}
        className="bg-transparent text-xs text-gray-400 hover:text-white cursor-pointer outline-none"
      >
        {LANGUAGES.map((l) => (
          <option key={l.code} value={l.code} className="bg-surface text-white">
            {l.label}
          </option>
        ))}
      </select>
    </div>
  )
}
