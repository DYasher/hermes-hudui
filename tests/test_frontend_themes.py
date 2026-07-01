from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_hermes_official_theme_is_registered_and_styled() -> None:
    theme_ts = (ROOT / "frontend/src/hooks/useTheme.tsx").read_text()
    css = (ROOT / "frontend/src/index.css").read_text()
    translations = (ROOT / "frontend/src/i18n/translations.ts").read_text()
    top_bar = (ROOT / "frontend/src/components/TopBar.tsx").read_text()
    main_ts = (ROOT / "frontend/src/main.tsx").read_text()
    app_ts = (ROOT / "frontend/src/App.tsx").read_text()

    assert "'hermes-official'" in theme_ts
    assert "|| 'hermes-official'" in theme_ts
    assert "|| 'hermes-official'" in main_ts
    assert "theme.hermesOfficial" in theme_ts
    assert '[data-theme="hermes-official"]' in css
    assert "--hud-bg-deep: #041c1c;" in css
    assert "--hud-primary: #ffe6cb;" in css
    assert "--hud-primary-glow: rgba(255, 189, 56, 0.35);" in css
    assert "--hud-bg: var(--hud-bg-deep);" in css
    assert "--hud-panel-alt: var(--hud-bg-surface);" in css
    assert "'theme.hermesOfficial': 'Hermes Teal'" in translations
    assert 'aria-label="Open theme picker"' in top_bar
    assert '<span className="hidden md:inline">Theme</span>' in top_bar

    assert "PANEL_BACKGROUND_STORAGE_KEY = 'hud-panel-background'" in theme_ts
    assert "PANEL_BACKGROUND_AUTO_STORAGE_KEY = 'hud-panel-background-auto'" in theme_ts
    assert "AUTO_PANEL_BACKGROUND_SOURCE_URL = 'https://bing.img.run/rand.php'" in theme_ts
    assert "panelBackground: string" in theme_ts
    assert "panelBackgroundAuto: boolean" in theme_ts
    assert "isValidPanelBackground(value: string)" in theme_ts
    assert "buildAutoPanelBackgroundUrl()" in theme_ts
    assert "resolvePanelBackground(panelBackground, panelBackgroundAuto)" in theme_ts
    assert "syncPanelBackground(resolvedPanelBackground)" in theme_ts
    assert "resolvePanelBackground(initialPanelBackground, initialPanelBackgroundAuto)" in main_ts
    assert "hud-workspace" in app_ts
    assert "--hud-panel-bg-image: none;" in css
    assert "--hud-panel-bg-opacity: 0;" in css
    assert ".hud-workspace {" in css
    assert "background-image: var(--hud-panel-bg-image);" in css
    assert "opacity: var(--hud-panel-bg-opacity);" in css
    assert ".hud-workspace::before {" in css
    assert "'theme.panelBackground': 'Panel Background'" in translations
    assert "'theme.panelBackgroundPlaceholder': 'Image URL or data URI'" in translations
    assert "'theme.autoWallpaper': 'Auto Wallpaper'" in translations
    assert "'theme.panelBackgroundOverridesAuto': 'Manual background overrides auto wallpaper'" in translations
    assert "'theme.clearBackground': 'Clear Background'" in translations
    assert "placeholder={t('theme.panelBackgroundPlaceholder')}" in top_bar
    assert "aria-label={t('theme.panelBackground')}" in top_bar
    assert "setPanelBackgroundAuto(!panelBackgroundAuto)" in top_bar
    assert "{t('theme.autoWallpaper')}" in top_bar
    assert "{t('theme.panelBackgroundOverridesAuto')}" in top_bar
    assert "{t('theme.clearBackground')}" in top_bar
