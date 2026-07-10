from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_memory_tab_renders_memory_and_user_profile_as_separate_top_level_panels() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()
    app = (ROOT / "frontend/src/App.tsx").read_text()
    render_block = panel.split("return (\n    <>", 1)[1]

    assert "<Panel title={t('memory.title')}>" in panel
    assert "<Panel title={t('memory.userProfile')}>" in panel
    assert render_block.index("<Panel title={t('memory.title')}>") < render_block.index("<Panel title={t('memory.userProfile')}>")
    assert "memory: 'grid-cols-1'" in app
    assert "memory: 'grid-cols-1 sm:grid-cols-2'" not in app


def test_user_profile_entries_render_two_per_row_on_wide_screens() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()

    assert "columns?: 1 | 2" in panel
    assert "columns === 2 ? 'grid grid-cols-1 lg:grid-cols-2 gap-1.5' : 'space-y-1.5'" in panel
    assert 'target="user" onMutate={refreshMemoryState} columns={2}' in panel
    assert "user?.entries || files?.user?.entries || []" in panel


def test_memory_panel_places_builtin_and_external_memory_cards_at_the_top() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()
    render_block = panel.split("return (\n    <>", 1)[1]
    memory_panel = render_block.split("<Panel title={t('memory.title')}>", 1)[1].split("<Panel title={t('memory.userProfile')}>", 1)[0]
    translations = (ROOT / "frontend/src/i18n/translations.ts").read_text()

    assert memory_panel.index("memory.builtinMemoryTitle") < memory_panel.index("<MemoryEntries")
    assert "<MemoryProvidersPanel" in memory_panel
    assert "memory.externalMemory" in panel
    assert "externalMemoryTitleContext" in panel
    assert "'memory.builtinMemoryTitle'" in translations
    assert "'memory.externalMemory'" in translations
    assert "<Panel title={t('memory.providers')}" not in panel


def test_memory_panel_exposes_provider_config_and_status_actions() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()

    assert "saveMemoryProviderConfig" in panel
    assert "/api/memory/providers/check" in panel
    assert "memory.configureProvider" in panel
    assert "memory.saveProviderConfig" in panel
    assert "memory.checkStatus" in panel
    assert "memory.configured" in panel


def test_memory_panel_labels_provider_fields_by_requirement() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()
    translations = (ROOT / "frontend/src/i18n/translations.ts").read_text()

    assert "field.requirement" in panel
    assert "required_group" in panel
    assert "memory.requiredMarker" in panel
    assert "fieldRequirementLabel" not in panel
    assert "fieldRequirementColor" not in panel
    assert "memory.requiredField" not in panel
    assert "memory.optionalField" not in panel
    assert "memory.requiredAnyField" not in panel
    assert "memory.requiredAnyOf" not in panel
    assert "'memory.requiredMarker'" in translations


def test_memory_panel_only_shows_required_missing_hint_not_duplicate_missing_config_hint() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()

    assert "missingConfig(detailProvider)" not in panel
    assert "memory.requiredConfigMissing" in panel


def test_memory_panel_renders_read_only_provider_health_summary() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()
    translations = (ROOT / "frontend/src/i18n/translations.ts").read_text()

    assert "health?: MemoryProviderHealth" in panel
    assert "interface MemoryProviderRuntimeCheck" in panel
    assert "runtime:" in panel
    assert "statusResult?.health || detailProvider?.health" in panel
    assert "activeHealth" in panel
    assert "memory.healthChecks" in panel
    assert "memory.healthRuntime" in panel
    assert "memory.healthConfigFiles" in panel
    assert "formatRuntimeOutput" in panel
    assert "checked_at" in panel
    assert "config_files" in panel
    assert "'memory.healthChecks'" in translations
    assert "'memory.healthRuntime'" in translations
    assert "'memory.healthConfigFiles'" in translations
    assert "'memory.lastChecked'" in translations


def test_memory_panel_checks_status_for_selected_provider_mode() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()

    assert "async function checkMemoryProviderStatus(provider: string, selectedMode = '')" in panel
    assert "body: JSON.stringify({ provider, mode: selectedMode })" in panel
    assert "checkMemoryProviderStatus(detailProvider.id, selectedMode)" in panel


def test_memory_panel_renders_provider_capability_matrix_and_schema_source() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()
    translations = (ROOT / "frontend/src/i18n/translations.ts").read_text()

    assert "interface MemoryProviderCapabilities" in panel
    assert "interface MemoryProviderSchemaSource" in panel
    assert "capabilities: MemoryProviderCapabilities" in panel
    assert "schema_source: MemoryProviderSchemaSource" in panel
    assert "CapabilityMatrix" in panel
    assert "provider.capabilities" in panel
    assert "external_read_mode" in panel
    assert "direct_hud_config" in panel
    assert "requires_network" in panel
    assert "hooks" in panel
    assert "memory.capabilityMatrix" in panel
    assert "memory.schemaSource" in panel
    assert "memory.officialSchema" in panel
    assert "memory.hudMetadata" in panel
    assert "'memory.capabilityMatrix'" in translations
    assert "'memory.schemaSource'" in translations
    assert "'memory.officialSchema'" in translations
    assert "'memory.hudMetadata'" in translations


def test_memory_panel_renders_provider_specific_external_memory_view() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()
    translations = (ROOT / "frontend/src/i18n/translations.ts").read_text()

    assert "interface MemoryProviderExternalView" in panel
    assert "external_view: MemoryProviderExternalViewSummary" in panel
    assert "fetchProviderExternalView" in panel
    assert "/api/memory/providers/${provider}/external" in panel
    assert "ExternalMemoryViewPanel" in panel
    assert "detailProvider.external_view" in panel
    assert "externalView?.summary.categories" in panel
    assert "trust_score" in panel
    assert "retrieval_count" in panel
    assert "memory.externalView" in panel
    assert "memory.readOnly" in panel
    assert "memory.externalUnavailable" in panel
    assert "memory.externalCategories" in panel
    assert "memory.externalTrust" in panel
    assert "'memory.externalView'" in translations
    assert "'memory.readOnly'" in translations
    assert "'memory.externalUnavailable'" in translations
    assert "'memory.externalCategories'" in translations
    assert "'memory.externalTrust'" in translations


def test_memory_panel_renders_summary_only_external_memory_view() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()
    translations = (ROOT / "frontend/src/i18n/translations.ts").read_text()

    assert "summaryOnly" in panel
    assert "externalView?.reason === 'summary_only'" in panel
    assert "memory.externalSummaryOnly" in panel
    assert "'memory.externalSummaryOnly'" in translations


def test_memory_panel_uses_external_memory_console_tabs() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()
    translations = (ROOT / "frontend/src/i18n/translations.ts").read_text()

    assert "type MemoryProviderConsoleTab" in panel
    assert "providerConsoleTabs" in panel
    assert "activeProviderTab" in panel
    assert "ProviderOverviewTab" in panel
    assert "ProviderConfigTab" in panel
    assert "ProviderDiagnosticsTab" in panel
    assert "ProviderExternalDataTab" in panel
    assert "ProviderInstallGuideTab" in panel
    assert "memory.providerOverview" in panel
    assert "memory.providerDiagnostics" in panel
    assert "memory.installGuide" in panel
    assert "'memory.providerOverview'" in translations
    assert "'memory.providerDiagnostics'" in translations
    assert "'memory.installGuide'" in translations


def test_memory_panel_renders_mode_aware_install_guide() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()
    install_block = panel.split("function ProviderInstallGuideTab", 1)[1].split("function MemoryProvidersPanel", 1)[0]

    assert "modeCommands" in install_block
    assert "provider.config_modes.map(mode => ({ mode, commands }))" in install_block
    assert "item.mode.label" in install_block
    assert "item.mode.description" in install_block
    assert "modeRequirementLabels(provider, item.mode)" in install_block
    assert "memory.minimumConfig" in install_block
    assert "item.commands.map(command =>" in install_block


def test_memory_panel_shows_provider_config_requirements_and_next_step() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()
    translations = (ROOT / "frontend/src/i18n/translations.ts").read_text()
    config_block = panel.split("function ProviderConfigTab", 1)[1].split("function ProviderDiagnosticsTab", 1)[0]

    assert "modeRequirementLabels(provider, activeMode)" in config_block
    assert "memory.minimumConfig" in config_block
    assert "memory.configNextStep" in config_block
    assert "statusCommand" in config_block
    assert "'memory.configNextStep'" in translations


def test_memory_panel_uses_grouped_provider_select_instead_of_provider_button_strip() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()
    translations = (ROOT / "frontend/src/i18n/translations.ts").read_text()

    assert "ProviderPicker" in panel
    assert "providerGroups" in panel
    assert "<select" in panel
    assert "<optgroup" in panel
    assert "memory.officialProviders" in panel
    assert "memory.communityProviders" in panel
    assert "memory.providerConfiguredSuffix" in panel
    assert "providers.map(provider => {" not in panel
    assert "'memory.officialProviders'" in translations
    assert "'memory.communityProviders'" in translations
    assert "'memory.providerConfiguredSuffix'" in translations


def test_memory_panel_styles_provider_select_options_for_theme_contrast() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()
    provider_picker = panel.split("function ProviderPicker", 1)[1].split("function ProviderStatusCards", 1)[0]

    assert "providerPickerOptionStyle" in provider_picker
    assert "background: 'var(--hud-bg-panel)'" in provider_picker
    assert "color: 'var(--hud-text)'" in provider_picker
    assert '<option value="" style={providerPickerOptionStyle}>' in provider_picker
    assert '<optgroup key={group.id} label={t(group.labelKey)} style={providerPickerOptionStyle}>' in provider_picker
    assert '<option key={item.id} value={item.id} style={providerPickerOptionStyle}>' in provider_picker


def test_memory_panel_uses_backend_provider_group_metadata() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()

    assert "communityProviderIds" not in panel
    assert "group: 'official' | 'community'" in panel
    assert "provider.group" in panel
    assert "providerGroups(providers" in panel


def test_memory_panel_moves_diagnostics_and_external_view_out_of_default_flow() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()

    overview_block = panel.split("function ProviderOverviewTab", 1)[1].split("function ProviderConfigTab", 1)[0]
    config_block = panel.split("function ProviderConfigTab", 1)[1].split("function ProviderDiagnosticsTab", 1)[0]
    diagnostics_block = panel.split("function ProviderDiagnosticsTab", 1)[1].split("function ProviderExternalDataTab", 1)[0]
    external_block = panel.split("function ProviderExternalDataTab", 1)[1].split("function ProviderInstallGuideTab", 1)[0]

    assert "ProviderStatusCards" in overview_block
    assert "CapabilitySummary" in overview_block
    assert "CapabilityMatrix" not in overview_block
    assert "ExternalMemoryViewPanel" not in overview_block
    assert "statusOutput" not in overview_block
    assert "minimumConfigFields" not in config_block
    assert "CapabilityMatrix" in diagnostics_block
    assert "activeHealth" in diagnostics_block
    assert "statusOutput" in diagnostics_block
    assert "ExternalMemoryViewPanel" not in diagnostics_block
    assert "ExternalMemoryViewPanel" in external_block


def test_memory_panel_renders_mode_specific_provider_config_form() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()
    translations = (ROOT / "frontend/src/i18n/translations.ts").read_text()

    assert "interface MemoryProviderConfigMode" in panel
    assert "config_modes: MemoryProviderConfigMode[]" in panel
    assert "selectedModes" in panel
    assert "activeMode" in panel
    assert "visibleConfigFields" in panel
    assert "ProviderConfigTab" in panel
    assert "mode_ids" in panel
    assert "mode: selectedMode" in panel
    assert "memory.configMode" in panel
    assert "'memory.configMode'" in translations


def test_memory_panel_blocks_save_until_required_provider_fields_are_present() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()
    translations = (ROOT / "frontend/src/i18n/translations.ts").read_text()

    assert "validateRequiredConfig" in panel
    assert "requiredConfigIssues" in panel
    assert "memory.requiredConfigMissing" in panel
    assert "disabled={busy || !provider.config_fields?.length || !!requiredConfigIssues.length}" in panel
    assert "'memory.requiredConfigMissing'" in translations


def test_memory_panel_opens_status_modal_from_output_box_without_extra_button() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()
    translations = (ROOT / "frontend/src/i18n/translations.ts").read_text()

    assert "statusModalOpen" in panel
    assert "memory.openStatusModal" not in panel
    assert "'memory.openStatusModal'" not in translations
    assert "onOpenStatusModal={() => setStatusModalOpen(true)}" in panel
    assert "onClick={onOpenStatusModal}" in panel
    diagnostics_block = panel.split("function ProviderDiagnosticsTab", 1)[1].split("function ProviderExternalDataTab", 1)[0]
    assert "role=\"button\"" not in diagnostics_block
    assert "<textarea" in diagnostics_block
    assert "readOnly" in diagnostics_block
    assert "value={statusOutput}" in diagnostics_block
    assert "aria-readonly=\"true\"" in diagnostics_block
    assert "aria-multiline=\"true\"" in diagnostics_block
    assert "tabIndex={0}" in panel
    assert "memory.closeStatusModal" in panel
    assert "maxHeight: '280px'" in panel
    assert "minHeight: '180px'" in panel
    assert "role=\"dialog\"" in panel
    assert "'memory.closeStatusModal'" in translations


def test_memory_panel_fetches_builtin_memory_files_without_rendering_soul() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()
    translations = (ROOT / "frontend/src/i18n/translations.ts").read_text()

    assert "interface MemoryFileState" in panel
    assert "target: 'memory' | 'user'" in panel
    assert "target: 'memory' | 'user' | 'soul'" not in panel
    assert "useApi<MemoryFilesState>('/memory/files'" in panel
    assert "saveMemoryFile" in panel
    assert "BuiltinMemoryFileCard" in panel
    assert "files?.memory" in panel
    assert "files?.user" in panel
    assert "soul: MemoryFileState" not in panel
    assert "files?.soul" not in panel
    assert "soulFile" not in panel
    assert "memory.soulTitle" not in panel
    assert "memory.fullFileEditor" in panel
    assert "'memory.soulTitle'" not in translations
    assert "'memory.fullFileEditor'" in translations


def test_memory_panel_exposes_memory_settings_controls() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()
    translations = (ROOT / "frontend/src/i18n/translations.ts").read_text()

    assert "interface MemorySettingsState" in panel
    assert "useApi<MemorySettingsState>('/memory/settings'" in panel
    assert "saveMemorySettings" in panel
    assert "memory.memoryEnabled" in panel
    assert "memory.userProfileEnabled" in panel
    assert "memory.writeApproval" in panel
    assert "memory.memoryNotifications" in panel
    assert "memory.memoryCharLimit" in panel
    assert "memory.userCharLimit" in panel
    assert "'memory.writeApproval'" in translations
    assert "'memory.memoryNotifications'" in translations


def test_memory_panel_exposes_pending_memory_approval_queue() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()
    translations = (ROOT / "frontend/src/i18n/translations.ts").read_text()

    assert "interface PendingMemoryWrite" in panel
    assert "useApi<MemoryPendingState>('/memory/pending'" in panel
    assert "approvePendingMemory" in panel
    assert "rejectPendingMemory" in panel
    assert "/api/memory/pending/${pendingId}/approve" in panel
    assert "/api/memory/pending/${pendingId}/reject" in panel
    assert "PendingMemoryPanel" in panel
    assert "memory.pendingWrites" in panel
    assert "memory.approve" in panel
    assert "memory.reject" in panel
    assert "'memory.pendingWrites'" in translations


def test_memory_panel_exposes_session_history_candidate_flow() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()
    translations = (ROOT / "frontend/src/i18n/translations.ts").read_text()

    assert "interface MemoryHistoryCandidate" in panel
    assert "fetchMemoryHistory" in panel
    assert "commitMemoryHistoryCandidate" in panel
    assert "/api/memory/history?${params.toString()}" in panel
    assert "/api/memory/history/commit" in panel
    assert "MemoryHistoryPanel" in panel
    assert "memory.historyCandidates" in panel
    assert "memory.searchHistory" in panel
    assert "memory.saveToMemory" in panel
    assert "memory.saveToUser" in panel
    assert "'memory.historyCandidates'" in translations
    assert "'memory.savedToPending'" in translations


def test_memory_panel_exposes_export_backup_without_soul() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()
    translations = (ROOT / "frontend/src/i18n/translations.ts").read_text()

    assert "interface MemoryExportState" in panel
    assert "fetchMemoryExport" in panel
    assert "createMemoryBackup" in panel
    assert "MemoryExportPanel" in panel
    assert "fetch('/api/memory/export')" in panel
    assert "fetch('/api/memory/export', { method: 'POST' })" in panel
    assert "memory.exportBackup" in panel
    assert "memory.createBackup" in panel
    assert "SOUL.md" not in panel
    assert "'memory.exportBackup'" in translations
    assert "'memory.soulTitle'" not in translations


def test_memory_panel_groups_settings_pending_and_backup_as_governance() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()
    render_block = panel.split("return (\n    <>", 1)[1]
    memory_panel = render_block.split("<Panel title={t('memory.title')}>", 1)[1].split("<Panel title={t('memory.userProfile')}>", 1)[0]
    translations = (ROOT / "frontend/src/i18n/translations.ts").read_text()

    assert "function MemoryGovernancePanel" in panel
    assert "<MemoryHistoryPanel" in memory_panel
    assert "<MemoryGovernancePanel" in memory_panel
    assert memory_panel.index("<MemoryHistoryPanel") < memory_panel.index("<MemoryGovernancePanel")
    assert "memory.governance" in panel
    assert "'memory.governance'" in translations
