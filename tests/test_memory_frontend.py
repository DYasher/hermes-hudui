from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_memory_panel_places_provider_console_before_internal_memory() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()
    render_block = panel.split("return (\n    <>", 1)[1]

    assert render_block.index("<MemoryProvidersPanel") < render_block.index("<Panel title={t('memory.title')}")


def test_memory_panel_exposes_provider_config_and_status_actions() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()

    assert "saveMemoryProviderConfig" in panel
    assert "/api/memory/providers/check" in panel
    assert "memory.configureProvider" in panel
    assert "memory.saveProviderConfig" in panel
    assert "memory.checkStatus" in panel
    assert "memory.configured" in panel
