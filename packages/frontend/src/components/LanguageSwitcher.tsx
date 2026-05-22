import { useTranslation } from 'react-i18next'
import { Globe } from 'lucide-react'
import { LANGUAGES, setLanguage, type LangCode } from '../i18n'

export function LanguageSwitcher() {
  const { i18n } = useTranslation()

  return (
    <div className="flex items-center gap-1 text-muted">
      <Globe size={11} className="shrink-0" />
      <select
        value={i18n.language}
        onChange={(e) => setLanguage(e.target.value as LangCode)}
        className="bg-transparent border-none text-[11px] text-muted hover:text-[#d1d4dc] cursor-pointer outline-none"
      >
        {LANGUAGES.map((l) => (
          <option key={l.code} value={l.code} className="bg-panel2 text-[#d1d4dc]">
            {l.label}
          </option>
        ))}
      </select>
    </div>
  )
}
