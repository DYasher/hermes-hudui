import { useState, useEffect, useRef } from 'react'
import { useTheme, THEMES } from '../hooks/useTheme'
import { useI18n } from '../i18n'

export const TABS = [
  { id: 'dashboard', labelKey: 'tab.dashboard', key: '1' },
  { id: 'memory', labelKey: 'tab.memory', key: '2' },
  { id: 'skills', labelKey: 'tab.skills', key: '3' },
  { id: 'sessions', labelKey: 'tab.sessions', key: '4' },
  { id: 'replay', labelKey: 'tab.replay', key: null },
  { id: 'cron', labelKey: 'tab.cron', key: '5' },
  { id: 'projects', labelKey: 'tab.projects', key: '6' },
  { id: 'health', labelKey: 'tab.health', key: '7' },
  { id: 'agents', labelKey: 'tab.agents', key: '8' },
  { id: 'chat', labelKey: 'tab.chat', key: '9' },
  { id: 'profiles', labelKey: 'tab.profiles', key: '0' },
  { id: 'token-costs', labelKey: 'tab.token-costs', key: null },
  { id: 'corrections', labelKey: 'tab.corrections', key: null },
  { id: 'patterns', labelKey: 'tab.patterns', key: null },
  { id: 'sudo', labelKey: 'tab.sudo', key: null },
  { id: 'providers', labelKey: 'tab.providers', key: null },
  { id: 'gateway', labelKey: 'tab.gateway', key: null },
  { id: 'model-info', labelKey: 'tab.model-info', key: null },
  { id: 'plugins', labelKey: 'tab.plugins', key: null },
  { id: 'safety', labelKey: 'tab.safety', key: null },
] as const

export type TabId = typeof TABS[number]['id']

interface TopBarProps {
  activeTab: TabId
  onTabChange: (tab: TabId) => void
}

export default function TopBar({ activeTab, onTabChange }: TopBarProps) {
  const {
    theme,
    setTheme,
    scanlines,
    setScanlines,
    panelBackground,
    setPanelBackground,
    panelBackgroundAuto,
    setPanelBackgroundAuto,
  } = useTheme()
  const { t, lang, setLang } = useI18n()
  const [showThemePicker, setShowThemePicker] = useState(false)
  const [panelBackgroundDraft, setPanelBackgroundDraft] = useState(panelBackground)
  const [time, setTime] = useState(new Date())
  const tabRefs = useRef<Partial<Record<TabId, HTMLButtonElement>>>({})
  const themeTitle = t('theme.title')

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    const scrollActiveTab = () => {
      tabRefs.current[activeTab]?.scrollIntoView({
        block: 'nearest',
        inline: 'nearest',
      })
    }
    scrollActiveTab()
    window.addEventListener('resize', scrollActiveTab)
    return () => window.removeEventListener('resize', scrollActiveTab)
  }, [activeTab])

  useEffect(() => {
    setPanelBackgroundDraft(panelBackground)
  }, [panelBackground])

  const handlePanelBackgroundSave = () => {
    setPanelBackground(panelBackgroundDraft)
  }

  const handlePanelBackgroundClear = () => {
    setPanelBackgroundDraft('')
    setPanelBackground('')
  }

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return
      if (e.metaKey || e.ctrlKey || e.altKey) return

      const num = parseInt(e.key)
      if (!isNaN(num) && num >= 1 && num <= 9) {
        const tab = TABS.find(t => t.key === String(num))
        if (tab) {
          onTabChange(tab.id)
          return
        }
      }
      if (e.key === '0') {
        onTabChange('profiles')
        return
      }
      if (e.key === 't') {
        setShowThemePicker(p => !p)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onTabChange])

  return (
    <div
      data-testid="top-bar"
      className="hud-topbar flex items-center gap-1 px-3 py-1.5 border-b w-full min-w-0 overflow-visible relative z-40"
      style={{ borderColor: 'var(--hud-border)', background: 'var(--hud-bg-surface)' }}
    >
      <button
        type="button"
        className="hud-topbar-brand gradient-text font-bold text-[13px] mr-3 tracking-wider cursor-pointer shrink-0"
        onClick={() => onTabChange('dashboard')}
      >
        <span aria-hidden="true">☤</span>
        <span>HERMES</span>
      </button>

      <div
        data-testid="top-tabs"
        className="hud-topbar-tabs flex gap-0.5 flex-1 min-w-0 overflow-x-auto overscroll-x-contain pb-1"
        style={{ scrollbarWidth: 'thin', WebkitOverflowScrolling: 'touch' }}
      >
        {TABS.map(tab => {
          const active = activeTab === tab.id
          return (
            <button
              key={tab.id}
              ref={(node) => {
                if (node) tabRefs.current[tab.id] = node
                else delete tabRefs.current[tab.id]
              }}
              onClick={() => onTabChange(tab.id)}
              className={`hud-tab ${active ? 'hud-tab--active' : ''} px-2 py-1.5 text-[13px] tracking-widest uppercase transition-all duration-150 shrink-0 cursor-pointer`}
              style={{
                color: active ? 'var(--hud-primary)' : 'var(--hud-text-dim)',
                minHeight: '32px',
              }}
            >
              {tab.key && <span className="opacity-40 mr-1">{tab.key}</span>}
              {t(tab.labelKey)}
            </button>
          )
        })}
      </div>

      <div className="hud-topbar-utility-group shrink-0">
        <div className="relative shrink-0">
          <button
            onClick={() => setShowThemePicker(p => !p)}
            className={`hud-toolbar-button ${showThemePicker ? 'hud-toolbar-button--active' : ''} px-2 py-1.5 text-[12px] tracking-wider uppercase cursor-pointer flex items-center gap-1`}
            title={`${themeTitle} (t)`}
            aria-label="Open theme picker"
            aria-expanded={showThemePicker}
          >
            <span aria-hidden="true">◆</span>
            <span className="hidden md:inline">Theme</span>
          </button>
          {showThemePicker && (
            <div className="hud-popover absolute right-0 top-full mt-2 z-50 py-2 min-w-[300px] max-w-[360px]">
              <div className="px-3 pb-2">
                <div className="hud-popover-section-label">{themeTitle}</div>
                <div className="text-[11px] leading-5" style={{ color: 'var(--hud-text-dim)' }}>
                  Pick a shell tone for the dashboard and management panels.
                </div>
              </div>
              <div className="hud-theme-grid px-2 pb-2">
                {THEMES.map(themeItem => (
                  <button
                    key={themeItem.id}
                    onClick={() => { setTheme(themeItem.id); setShowThemePicker(false) }}
                    className={`hud-popover-option hud-theme-option block w-full text-left px-3 py-2 text-[13px] transition-colors cursor-pointer ${theme === themeItem.id ? 'hud-popover-option--active' : ''}`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span>{themeItem.icon} {t(themeItem.labelKey as any)}</span>
                      {theme === themeItem.id && <span className="hud-theme-option-check">●</span>}
                    </div>
                  </button>
                ))}
              </div>
              <div className="border-t my-2" style={{ borderColor: 'var(--hud-border)' }} />
              <div className="px-3 py-1.5">
                <div className="hud-popover-section-label">{t('theme.panelBackground')}</div>
                <input
                  value={panelBackgroundDraft}
                  onChange={(e) => setPanelBackgroundDraft(e.target.value)}
                  onBlur={handlePanelBackgroundSave}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      handlePanelBackgroundSave()
                    }
                  }}
                  className="w-full px-2 py-1.5 text-[12px] hud-inline-input"
                  style={{
                    color: 'var(--hud-text)',
                    background: 'var(--hud-bg-surface)',
                    border: '1px solid var(--hud-border)',
                  }}
                  placeholder={t('theme.panelBackgroundPlaceholder')}
                  aria-label={t('theme.panelBackground')}
                />
                <div className="mt-2 flex justify-between gap-2">
                  <button
                    onClick={() => setPanelBackgroundAuto(!panelBackgroundAuto)}
                    className="hud-toolbar-button hud-toolbar-button--compact px-2 py-1 text-[11px] uppercase tracking-wider cursor-pointer"
                    aria-pressed={panelBackgroundAuto}
                  >
                    {panelBackgroundAuto ? '◉' : '○'} {t('theme.autoWallpaper')}
                  </button>
                  <button
                    onClick={handlePanelBackgroundClear}
                    className="hud-toolbar-button hud-toolbar-button--compact px-2 py-1 text-[11px] uppercase tracking-wider cursor-pointer"
                  >
                    {t('theme.clearBackground')}
                  </button>
                </div>
                {panelBackgroundAuto && panelBackground && (
                  <div className="mt-2 text-[10px] leading-4" style={{ color: 'var(--hud-text-dim)' }}>
                    {t('theme.panelBackgroundOverridesAuto')}
                  </div>
                )}
              </div>
              <div className="border-t my-2" style={{ borderColor: 'var(--hud-border)' }} />
              <div className="px-3 pt-1 pb-2">
                <div className="hud-popover-section-label">{t('theme.scanlines')}</div>
                <button
                  onClick={() => setScanlines(!scanlines)}
                  className="hud-popover-option block w-full text-left px-3 py-2 text-[13px] cursor-pointer hud-theme-toggle"
                  style={{ color: 'var(--hud-text-dim)', minHeight: '36px' }}
                >
                  {scanlines ? '▣' : '□'} {t('theme.scanlines')}
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="hud-topbar-status hidden sm:flex">
          <span className="text-[13px] tabular-nums hud-topbar-clock" style={{ color: 'var(--hud-text-dim)' }}>
            {time.toLocaleTimeString('en-US', { hour12: false })}
          </span>
        </div>

        <button
          onClick={() => setLang(lang === 'en' ? 'zh' : 'en')}
          className="hud-toolbar-button hud-toolbar-button--lang px-2 py-0.5 text-[12px] font-bold tracking-wider cursor-pointer shrink-0"
          title={lang === 'en' ? 'Switch to Chinese' : '切换到英文'}
        >
          {lang === 'en' ? '中文' : 'EN'}
        </button>
      </div>
    </div>
  )
}
