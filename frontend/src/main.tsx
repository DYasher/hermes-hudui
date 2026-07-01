import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'
import { I18nProvider } from './i18n'
import {
  PANEL_BACKGROUND_AUTO_STORAGE_KEY,
  PANEL_BACKGROUND_STORAGE_KEY,
  resolvePanelBackground,
  syncPanelBackground,
} from './hooks/useTheme'

function getInitialLang() {
  const stored = localStorage.getItem('hermes-hudui-lang')
  if (stored === 'zh' || stored === 'en') return stored
  return navigator.language.toLowerCase().startsWith('zh') ? 'zh' : 'en'
}

// Set default theme before render to avoid flash
if (!document.documentElement.getAttribute('data-theme')) {
  document.documentElement.setAttribute('data-theme', localStorage.getItem('hud-theme') || 'hermes-official')
}
document.documentElement.lang = getInitialLang()
document.documentElement.setAttribute('data-lang', document.documentElement.lang)
const initialPanelBackground = localStorage.getItem(PANEL_BACKGROUND_STORAGE_KEY) || ''
const initialPanelBackgroundAuto = localStorage.getItem(PANEL_BACKGROUND_AUTO_STORAGE_KEY) === 'true'
syncPanelBackground(resolvePanelBackground(initialPanelBackground, initialPanelBackgroundAuto))

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <I18nProvider>
      <App />
    </I18nProvider>
  </StrictMode>,
)
