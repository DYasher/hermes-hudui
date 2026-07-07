from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_visual_refresh_registers_new_theme_variants() -> None:
    theme_ts = (ROOT / "frontend/src/hooks/useTheme.tsx").read_text()
    css = (ROOT / "frontend/src/index.css").read_text()
    translations = (ROOT / "frontend/src/i18n/translations.ts").read_text()

    assert "'graphite'" in theme_ts
    assert "'aurora'" in theme_ts
    assert "'sunset'" in theme_ts
    assert "theme.graphite" in theme_ts
    assert "theme.aurora" in theme_ts
    assert "theme.sunset" in theme_ts

    assert '[data-theme="graphite"]' in css
    assert '[data-theme="aurora"]' in css
    assert '[data-theme="sunset"]' in css
    assert "--hud-bg-deep: #0d131a;" in css
    assert "--hud-bg-deep: #07161b;" in css
    assert "--hud-bg-deep: #1a1010;" in css

    assert "'theme.graphite': 'Graphite Grid'" in translations
    assert "'theme.aurora': 'Aurora Pulse'" in translations
    assert "'theme.sunset': 'Sunset Signal'" in translations
    assert "'theme.graphite': '石墨矩阵'" in translations
    assert "'theme.aurora': '极光脉冲'" in translations
    assert "'theme.sunset': '落日信号'" in translations


def test_visual_refresh_hooks_exist_for_topbar_dashboard_and_list_cards() -> None:
    top_bar = (ROOT / "frontend/src/components/TopBar.tsx").read_text()
    dashboard = (ROOT / "frontend/src/components/DashboardPanel.tsx").read_text()
    plugins = (ROOT / "frontend/src/components/PluginsPanel.tsx").read_text()
    providers = (ROOT / "frontend/src/components/ProvidersPanel.tsx").read_text()
    css = (ROOT / "frontend/src/index.css").read_text()

    assert "hud-topbar" in top_bar
    assert "hud-topbar-brand" in top_bar
    assert "hud-topbar-tabs" in top_bar
    assert "hud-tab" in top_bar
    assert "hud-toolbar-button" in top_bar
    assert "hud-topbar-utility-group" in top_bar
    assert "hud-topbar-status" in top_bar
    assert "hud-popover-section-label" in top_bar
    assert "t('theme.title')" in top_bar

    assert "dashboard-hero" in dashboard
    assert "dashboard-metric-grid" in dashboard
    assert "dashboard-metric-card" in dashboard
    assert "dashboard-overview-grid" in dashboard
    assert "dashboard-section-stack" in dashboard
    assert "dashboard-section-card" in dashboard
    assert "dashboard-signal-list" in dashboard
    assert "dashboard-list-card" in dashboard

    assert "hud-stat-tile" in plugins
    assert "hud-empty-state" in plugins
    assert "hud-list-card" in plugins
    assert "hud-empty-state" in providers
    assert "hud-list-card" in providers

    assert ".hud-topbar {" in css
    assert ".hud-topbar-brand {" in css
    assert ".hud-tab {" in css
    assert ".hud-tab--active {" in css
    assert ".hud-toolbar-button {" in css
    assert ".hud-topbar-utility-group {" in css
    assert ".hud-topbar-status {" in css
    assert ".hud-popover-section-label {" in css
    assert ".dashboard-hero {" in css
    assert ".dashboard-metric-grid {" in css
    assert ".dashboard-metric-card {" in css
    assert ".dashboard-overview-grid {" in css
    assert ".dashboard-section-stack {" in css
    assert ".dashboard-signal-list {" in css
    assert ".dashboard-section-card {" in css
    assert ".dashboard-list-card {" in css
    assert ".hud-stat-tile {" in css
    assert ".hud-empty-state {" in css
    assert ".hud-list-card {" in css


def test_feedback_polish_handles_long_model_names_and_lighter_glass() -> None:
    app = (ROOT / "frontend/src/App.tsx").read_text()
    dashboard = (ROOT / "frontend/src/components/DashboardPanel.tsx").read_text()
    css = (ROOT / "frontend/src/index.css").read_text()
    memory_panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()
    skills_panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()
    profiles_panel = (ROOT / "frontend/src/components/ProfilesPanel.tsx").read_text()

    assert "dashboard-metric-card--model" not in dashboard
    assert "dashboard-metric-value--model" not in dashboard
    assert ".dashboard-metric-card--model {" not in css
    assert "grid-column: span 2;" not in css
    assert "min-height: 132px;" not in css
    assert ".dashboard-metric-card--model .dashboard-metric-value--model {" not in css

    assert "className=\"hud-workspace-scroll\"" not in app
    assert "overflow: activeTab === 'skills' ? 'hidden' : 'auto'" in app
    assert "height: 0" in app
    assert ".hud-workspace {" in css
    assert "min-height: 100%;" not in css
    assert ".hud-workspace::before {" in css
    assert ".hud-workspace::after {" in css
    assert "position: fixed;" in css
    assert "inset: 0;" in css

    assert "--hud-panel-surface-strength:" in css
    assert "--hud-card-surface-strength:" in css
    assert "--hud-metric-surface-strength:" in css
    assert "--hud-shell-surface-strength:" in css
    assert "--hud-inner-surface-strength:" in css
    assert "var(--hud-panel-surface-strength)" in css
    assert "var(--hud-card-surface-strength)" in css
    assert "var(--hud-metric-surface-strength)" in css
    assert "var(--hud-shell-surface-strength)" in css
    assert "var(--hud-inner-surface-strength)" in css
    assert "backdrop-filter: blur(16px) saturate(1.08);" in css
    assert "--hud-soft-block:" in css
    assert "--hud-solid-block:" in css

    memory_panel_without_picker = (
        memory_panel.split("function ProviderPicker", 1)[0]
        + memory_panel.split("function ProviderStatusCards", 1)[1]
    )
    assert "background: 'var(--hud-bg-panel)'" not in memory_panel_without_picker
    assert "background: 'var(--hud-bg-surface)'" not in memory_panel
    assert "background: 'var(--hud-bg-deep)'" not in memory_panel
    assert "background: 'var(--hud-bg-panel)'" not in skills_panel
    assert "background: 'var(--hud-bg-surface)'" not in skills_panel
    assert "background: 'var(--hud-bg-panel)'" not in profiles_panel


def test_background_revalidation_keeps_scroll_state_stable() -> None:
    websocket = (ROOT / "frontend/src/hooks/useWebSocket.ts").read_text()

    assert "populateCache: false" in websocket
    assert "const [lastMessage" not in websocket
    assert "setLastMessage(data)" not in websocket
    assert "lastMessage:" not in websocket
