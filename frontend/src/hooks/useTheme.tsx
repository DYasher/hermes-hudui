import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'

export type ThemeId =
  | 'hermes-official'
  | 'graphite'
  | 'aurora'
  | 'sunset'
  | 'ai'
  | 'blade-runner'
  | 'fsociety'
  | 'anime'

const THEME_STORAGE_KEY = 'hud-theme'
const SCANLINES_STORAGE_KEY = 'hud-scanlines'
export const PANEL_BACKGROUND_STORAGE_KEY = 'hud-panel-background'
export const PANEL_BACKGROUND_AUTO_STORAGE_KEY = 'hud-panel-background-auto'
const AUTO_PANEL_BACKGROUND_SOURCE_URL = 'https://bing.img.run/rand.php'

function toCssImage(value: string) {
  return `url("${value.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}")`
}

export function isValidPanelBackground(value: string) {
  const next = value.trim()
  if (!next) return false
  if (next.startsWith('data:image/')) return true
  try {
    const url = new URL(next)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

export function buildAutoPanelBackgroundUrl() {
  return AUTO_PANEL_BACKGROUND_SOURCE_URL
}

export function resolvePanelBackground(panelBackground: string, panelBackgroundAuto: boolean) {
  const manual = panelBackground.trim()
  if (isValidPanelBackground(manual)) return manual
  if (panelBackgroundAuto) return buildAutoPanelBackgroundUrl()
  return ''
}

export function syncPanelBackground(panelBackground: string) {
  const next = panelBackground.trim()
  document.documentElement.style.setProperty('--hud-panel-bg-image', next ? toCssImage(next) : 'none')
  document.documentElement.style.setProperty('--hud-panel-bg-opacity', next ? '0.38' : '0')
}

interface ThemeContextValue {
  theme: ThemeId
  setTheme: (t: ThemeId) => void
  scanlines: boolean
  setScanlines: (s: boolean) => void
  panelBackground: string
  setPanelBackground: (value: string) => void
  panelBackgroundAuto: boolean
  setPanelBackgroundAuto: (enabled: boolean) => void
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: 'hermes-official',
  setTheme: () => {},
  scanlines: false,
  setScanlines: () => {},
  panelBackground: '',
  setPanelBackground: () => {},
  panelBackgroundAuto: false,
  setPanelBackgroundAuto: () => {},
})

export const THEMES: { id: ThemeId; labelKey: string; icon: string }[] = [
  { id: 'hermes-official', labelKey: 'theme.hermesOfficial', icon: '☤' },
  { id: 'graphite', labelKey: 'theme.graphite', icon: '◼' },
  { id: 'aurora', labelKey: 'theme.aurora', icon: '✦' },
  { id: 'sunset', labelKey: 'theme.sunset', icon: '◐' },
  { id: 'ai', labelKey: 'theme.neuralAwakening', icon: '◆' },
  { id: 'blade-runner', labelKey: 'theme.bladeRunner', icon: '◈' },
  { id: 'fsociety', labelKey: 'theme.fsociety', icon: '▣' },
  { id: 'anime', labelKey: 'theme.anime', icon: '◎' },
]

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeId>(() => {
    return (localStorage.getItem(THEME_STORAGE_KEY) as ThemeId) || 'hermes-official'
  })
  const [scanlines, setScanlinesState] = useState(() => {
    return localStorage.getItem(SCANLINES_STORAGE_KEY) === 'true'
  })
  const [panelBackground, setPanelBackgroundState] = useState(() => {
    return localStorage.getItem(PANEL_BACKGROUND_STORAGE_KEY)?.trim() || ''
  })
  const [panelBackgroundAuto, setPanelBackgroundAutoState] = useState(() => {
    return localStorage.getItem(PANEL_BACKGROUND_AUTO_STORAGE_KEY) === 'true'
  })

  const setTheme = (t: ThemeId) => {
    setThemeState(t)
    localStorage.setItem(THEME_STORAGE_KEY, t)
  }

  const setScanlines = (s: boolean) => {
    setScanlinesState(s)
    localStorage.setItem(SCANLINES_STORAGE_KEY, String(s))
  }

  const setPanelBackground = (value: string) => {
    const next = value.trim()
    setPanelBackgroundState(next)
    if (next) localStorage.setItem(PANEL_BACKGROUND_STORAGE_KEY, next)
    else localStorage.removeItem(PANEL_BACKGROUND_STORAGE_KEY)
  }

  const setPanelBackgroundAuto = (enabled: boolean) => {
    setPanelBackgroundAutoState(enabled)
    if (enabled) localStorage.setItem(PANEL_BACKGROUND_AUTO_STORAGE_KEY, 'true')
    else localStorage.removeItem(PANEL_BACKGROUND_AUTO_STORAGE_KEY)
  }

  const resolvedPanelBackground = resolvePanelBackground(panelBackground, panelBackgroundAuto)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  useEffect(() => {
    syncPanelBackground(resolvedPanelBackground)
  }, [resolvedPanelBackground])

  return (
    <ThemeContext.Provider
      value={{
        theme,
        setTheme,
        scanlines,
        setScanlines,
        panelBackground,
        setPanelBackground,
        panelBackgroundAuto,
        setPanelBackgroundAuto,
      }}
    >
      <div className={scanlines ? 'scanlines' : ''} style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        {children}
      </div>
    </ThemeContext.Provider>
  )
}

export const useTheme = () => useContext(ThemeContext)
