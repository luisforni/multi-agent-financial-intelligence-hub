import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import es from './locales/es'
import en from './locales/en'
import pt from './locales/pt'
import fr from './locales/fr'
import de from './locales/de'
import zh from './locales/zh'
import ja from './locales/ja'

export const LANGUAGES = [
  { code: 'es', label: 'Español' },
  { code: 'en', label: 'English' },
  { code: 'pt', label: 'Português' },
  { code: 'fr', label: 'Français' },
  { code: 'de', label: 'Deutsch' },
  { code: 'zh', label: '中文' },
  { code: 'ja', label: '日本語' },
] as const

export type LangCode = (typeof LANGUAGES)[number]['code']

// Priority: localStorage > VITE_DEFAULT_LANG > 'es'
const stored = localStorage.getItem('lang') as LangCode | null
const envDefault = (import.meta.env.VITE_DEFAULT_LANG as string | undefined) || 'es'
const defaultLang: LangCode = (stored ?? envDefault) as LangCode

i18n.use(initReactI18next).init({
  resources: { es: { t: es }, en: { t: en }, pt: { t: pt }, fr: { t: fr }, de: { t: de }, zh: { t: zh }, ja: { t: ja } },
  lng: defaultLang,
  fallbackLng: 'es',
  ns: ['t'],
  defaultNS: 't',
  interpolation: { escapeValue: false },
})

export function setLanguage(code: LangCode) {
  i18n.changeLanguage(code)
  localStorage.setItem('lang', code)
}

export default i18n
