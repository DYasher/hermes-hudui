from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_skills_panel_opens_skill_detail_from_list_items() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "selectedSkillPath" in panel
    assert "setSelectedSkillPath(skill.path)" in panel
    assert "/skills/detail?path=${encodeURIComponent(path)}" in panel
    assert "function SkillDetailModal" in panel
    assert "role=\"dialog\"" in panel
    assert "aria-modal=\"true\"" in panel
    assert "<ReactMarkdown" in panel


def test_skills_panel_shows_bilingual_skill_reader_modal() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "translationMode" in panel
    assert "fetch('/api/skills/translate'" in panel
    assert "target_lang: 'auto'" in panel
    assert "skills.original" in panel
    assert "skills.translation" in panel
    assert "grid grid-cols-1 lg:grid-cols-2" in panel
    assert "setSelectedSkillPath(null)" in panel


def test_skills_panel_uses_language_aware_translation_labels() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "translationSourceLang" in panel
    assert "translationTargetLang" in panel
    assert "skills.originalEnglish" in panel
    assert "skills.originalChinese" in panel
    assert "skills.translationEnglish" in panel
    assert "skills.translationChinese" in panel


def test_skill_detail_modal_bounds_height_and_scrolls_panes() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "h-[92vh]" in panel
    assert "overflow-hidden" in panel
    assert "flex-1 min-h-0 overflow-y-auto" in panel


def test_skill_translation_effect_only_checks_cache_automatically() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "runTranslation(false, true)" in panel
    assert "cache_only: cacheOnly" in panel
    assert "runTranslation(true)" in panel
    assert "}, [data?.path, data?.content, isCurrentDetail, translation, translationLoading, translationError])" not in panel


def test_skill_translation_request_does_not_abort_slow_models_client_side() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "TRANSLATION_TIMEOUT_MS" not in panel
    assert "new AbortController()" not in panel
    assert "signal: controller.signal" not in panel
    assert "controller.abort()" not in panel


def test_skill_translation_model_picker_uses_persisted_options() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "TRANSLATION_PROVIDER_STORAGE_KEY" in panel
    assert "TRANSLATION_MODEL_STORAGE_KEY" in panel
    assert "readStoredValue(TRANSLATION_PROVIDER_STORAGE_KEY)" in panel
    assert "storeValue(TRANSLATION_PROVIDER_STORAGE_KEY" in panel
    assert "useApi<SkillTranslationOptions>('/skills/translation-options', 60000)" in panel
    assert "draftTranslationProvider" in panel
    assert "appliedTranslationProvider" in panel
    assert "applyTranslationModel" in panel
    assert "skills.translationProvider" in panel
    assert "skills.translationModel" in panel
    assert "skills.applyModel" in panel
    assert "data-skill-translation-provider" in panel
    assert "data-skill-translation-model" in panel


def test_skill_translation_model_picker_uses_bound_selects_for_provider_models() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "data-skill-translation-provider" in panel
    assert "data-skill-translation-model" in panel
    assert "value={provider.id}" in panel
    assert "modelDisplayOptions.map(model" in panel
    assert "value={model}" in panel
    assert 'list="skill-translation-provider-options"' not in panel


def test_skill_detail_modal_supports_synced_comparison_scrolling() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "syncCompareEnabled" in panel
    assert "skills.syncCompare" in panel
    assert "originalScrollRef" in panel
    assert "translationScrollRef" in panel
    assert "syncingScrollRef" in panel
    assert "syncPaneScroll" in panel
    assert "data-skill-sync-node" in panel
    assert "data-skill-sync-heading" in panel
    assert "getSyncAnchorTops" in panel
    assert "getSyncedScrollFromAnchorTops" in panel
    assert "computeSyncedScrollTop" in panel
    assert "getSyncAnchorTops(source, '[data-skill-sync-node]')" in panel
    assert "getSyncAnchorTops(source, '[data-skill-sync-heading]')" in panel
    assert "sourceHeadingTops.length === targetHeadingTops.length" in panel
    assert "scrollHeight - source.clientHeight" in panel
    assert "scrollHeight - target.clientHeight" in panel
    assert "requestAnimationFrame" in panel
    assert "onScroll={onScroll}" in panel


def test_skill_translation_request_includes_selected_provider_and_model() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "provider: appliedTranslationProvider || undefined" in panel
    assert "model: appliedTranslationModel || undefined" in panel
    assert "force," in panel
    assert "cache_only: cacheOnly" in panel


def test_skill_translation_remounts_translated_pane_after_completion() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "translationRenderKey" in panel
    assert "setTranslationRenderKey(current => current + 1)" in panel
    assert "key={`${data.path}:${translationTargetLang}:${translationRenderKey}`}" in panel


def test_skills_panel_exposes_management_actions_and_editor() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "createSkill" in panel
    assert "saveSkillContent" in panel
    assert "deleteSkill" in panel
    assert "toggleSkillEnabled" in panel
    assert "SkillCreateModal" in panel
    assert "isEditing" in panel
    assert "editorContent" in panel
    assert "data-skill-editor" in panel
    assert "fetch('/api/skills'" in panel
    assert "fetch('/api/skills/detail'" in panel
    assert "fetch('/api/skills/toggle'" in panel
    assert "fetch('/api/skills'," in panel
    assert "skills.newSkill" in panel
    assert "skills.editSkill" in panel
    assert "skills.saveSkill" in panel
    assert "skills.deleteSkill" in panel
    assert "skills.enableSkill" in panel
    assert "skills.disableSkill" in panel


def test_skill_item_places_management_actions_on_right_side() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "grid grid-cols-[auto_minmax(0,1fr)_auto]" in panel
    assert "data-skill-row-actions" in panel
    assert 'className="flex shrink-0 flex-col items-stretch gap-1"' in panel
    assert 'className="text-[10px] px-1 leading-4"' in panel
    assert "deleteConfirming" in panel
    assert "skills.confirmDeleteAction" in panel
    assert "mt-2 flex flex-wrap gap-1" not in panel


def test_skills_panel_requires_confirmation_for_every_batch_operation() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()
    batch = (ROOT / "frontend/src/lib/skillBatch.ts").read_text()

    assert "export type SkillBatchAction = 'enable' | 'disable' | 'export' | 'delete' | 'move'" in batch
    assert "selectedSkillPaths" in panel
    assert "toggleSelectSkill" in panel
    assert "selectedSkills" in panel
    assert "handleBatchSetEnabled" in panel
    assert "handleBatchExport" in panel
    assert "handleBatchDelete" in panel
    assert "batchConfirmAction" in panel
    assert "requestBatchConfirmation" in panel
    assert "const action = enabled ? 'enable' : 'disable'" in panel
    assert "requestBatchConfirmation(action)" in panel
    assert "requestBatchConfirmation('export')" in panel
    assert "requestBatchConfirmation('delete')" in panel
    assert "skills.batchEnable" in panel
    assert "skills.batchConfirmEnable" in panel
    assert "skills.batchDisable" in panel
    assert "skills.batchConfirmDisable" in panel
    assert "skills.batchExport" in panel
    assert "skills.batchConfirmExport" in panel
    assert "skills.batchDelete" in panel
    assert "skills.batchConfirmDelete" in panel
    assert "allVisibleSelected" in panel
    assert "toggleSelectAllVisible" in panel
    assert "skills.selectAllVisible" in panel
    assert "skills.deselectAllVisible" in panel
    assert "t('skills.clearSelection')" not in panel


def test_skills_panel_supports_batch_export_without_clearing_selection() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "downloadSelectedSkills" in panel
    assert "fetch('/api/skills/export'" in panel
    assert "JSON.stringify({ paths })" in panel
    assert "handleBatchExport" in panel
    assert "await downloadSelectedSkills(skills.map(skill => skill.path))" in panel
    assert "await runBatchAction('export', selectedSkills)" in panel
    assert "onClick={handleBatchExport}" in panel
    assert "skills.batchExport" in panel
    assert "disabled={!selectedSkills.length || batchBusy}" in panel

    export_handler = panel.split("const handleBatchExport", 1)[1].split(
        "const handleBatchDelete", 1
    )[0]
    assert "clearBatchSelection()" not in export_handler


def test_skills_panel_reports_batch_progress_and_allows_failed_retries() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "runSkillBatch" in panel
    assert "batchProgress" in panel
    assert "batchResult" in panel
    assert "runBatchAction" in panel
    assert "retryBatchFailures" in panel
    assert "skills.batchProgress" in panel
    assert "skills.batchSucceeded" in panel
    assert "skills.batchFailed" in panel
    assert "skills.retryFailed" in panel
    assert "skills.confirmRetryFailed" in panel


def test_skills_panel_exposes_zip_import_and_market_install() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "SkillImportModal" in panel
    assert "SkillMarketModal" in panel
    assert "selectedZipFile" in panel
    assert "importSkillsZip" in panel
    assert "searchSkillMarket" in panel
    assert "installMarketSkill" in panel
    assert "fetch(`/api/skills/import-zip?${params.toString()}`" in panel
    assert "fetch(`/api/skills/market/search?${params.toString()}`" in panel
    assert "fetch('/api/skills/market/install'" in panel
    assert "application/zip" in panel
    assert "skills.importZip" in panel
    assert "skills.skillMarket" in panel
    assert "skills.installSkill" in panel


def test_skills_panel_exposes_search_filters_and_backup_restore_actions() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "searchQuery" in panel
    assert "statusFilter" in panel
    assert "typeFilter" in panel
    assert "filteredSkills" in panel
    assert "skills.searchSkills" in panel
    assert "skills.statusFilter" in panel
    assert "skills.typeFilter" in panel
    assert "downloadSkillsBackup" in panel
    assert "fetch('/api/skills/backup')" in panel
    assert "skills.backup" in panel
    assert "mode?: 'import' | 'restore'" in panel
    assert "mode === 'restore'" in panel
    assert "skills.restoreSkills" in panel
    assert "skills.previewRestore" in panel
    assert "skills.confirmRestore" in panel


def test_skills_filters_use_theme_aware_translucent_popovers() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()
    styles = (ROOT / "frontend/src/index.css").read_text()

    assert "function SkillFilterSelect" in panel
    assert 'data-skill-filter="status"' in panel
    assert 'data-skill-filter="type"' in panel
    assert 'aria-haspopup="listbox"' in panel
    assert 'role="listbox"' in panel
    assert "skill-filter-menu" in panel
    assert "skill-filter-option" in panel
    assert "skillFilterOptionStyle" not in panel
    assert ".skill-filter-menu" in styles
    assert "backdrop-filter: blur(16px)" in styles
    assert "color-mix(in srgb, var(--hud-bg-hover) 62%, transparent)" in styles


def test_skills_panel_requires_zip_import_preview_before_confirmation() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "type SkillImportPreview" in panel
    assert "preview: String(preview)" in panel
    assert "const [previewResult, setPreviewResult]" in panel
    assert "setPreviewResult(null)" in panel
    assert "const previewImport = async ()" in panel
    assert "await importSkillsZip(selectedZipFile, overwrite, true)" in panel
    assert "await importSkillsZip(selectedZipFile, overwrite, false)" in panel
    assert "disabled={Boolean(busy) || !selectedZipFile || !previewResult}" in panel
    assert "skills.previewImport" in panel
    assert "skills.confirmImport" in panel
    assert "skills.importWillAdd" in panel
    assert "skills.importWillOverwrite" in panel
    assert "skills.importWillSkip" in panel


def test_skills_restore_rejects_non_zip_files_before_preview() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "isZipArchiveFile" in panel
    assert "file.name.toLowerCase().endsWith('.zip')" in panel
    assert "skills.zipOnly" in panel
    assert "application/x-zip-compressed" in panel


def test_skills_market_shows_installed_and_per_item_install_status() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "installed?: boolean" in panel
    assert "installed_category?: string" in panel
    assert "type SkillMarketInstallState" in panel
    assert "const [searching, setSearching]" in panel
    assert "const [activeInstall, setActiveInstall]" in panel
    assert "const [installStates, setInstallStates]" in panel
    assert "status: 'installing'" in panel
    assert "status: 'success'" in panel
    assert "status: 'error'" in panel
    assert "item.installed && !force" in panel
    assert "skills.marketInstalled" in panel
    assert "skills.reinstallSkill" in panel
    assert "skills.installingSkill" in panel
    assert "skills.retryInstall" in panel
    assert "skills.installSucceeded" in panel


def test_skills_page_uses_internal_panel_scrolling() -> None:
    app = (ROOT / "frontend/src/App.tsx").read_text()
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "activeTab === 'skills'" in app
    assert "overflow: activeTab === 'skills' ? 'hidden' : 'auto'" in app
    assert "skills-panel-root" in panel
    assert "h-full min-h-0" in panel
    assert "noPadding" in panel
    assert "overflow-y-auto" in panel
    assert "skill-list-scroll" in panel


def test_skill_translation_shows_translator_model_and_manual_button() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "translatedByProvider" in panel
    assert "translatedByModel" in panel
    assert "skills.translationGeneratedBy" in panel
    assert "skills.translate" in panel
    assert "skills.retranslate" in panel
    assert "onClick={() => runTranslation(true)}" in panel


def test_skills_panel_handles_missing_skills_payload() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "const { data, isLoading, error, mutate } = useApi<SkillsPayload>('/skills', 60000)" in panel
    assert "if (error && !data)" in panel
    assert "data?.category_counts || {}" in panel
    assert "data?.by_category || {}" in panel
    assert "data?.recently_modified || []" in panel
    assert "data?.total || 0" in panel
    assert "data?.custom_count || 0" in panel


def test_skills_panel_displays_localized_category_names_and_descriptions() -> None:
    panel = (ROOT / "frontend/src/components/SkillsPanel.tsx").read_text()

    assert "getSkillCategoryDisplay" in panel
    assert "skills.category.data-science.label" in panel
    assert "skills.category.data-science.description" in panel
    assert "categoryDisplay.description" in panel
    assert "selectedCat ? selectedCategoryDisplay?.label || selectedCat : t('dashboard.recentlyModified')" in panel
    assert "{categoryDisplay.label}" in panel


def test_skills_translations_include_modal_and_bilingual_labels() -> None:
    translations = (ROOT / "frontend/src/i18n/translations.ts").read_text()

    assert "'skills.original': 'Original'" in translations
    assert "'skills.originalEnglish': 'English Original'" in translations
    assert "'skills.originalChinese': 'Chinese Original'" in translations
    assert "'skills.translation': 'Translation'" in translations
    assert "'skills.translationChinese': 'Chinese Translation'" in translations
    assert "'skills.translationEnglish': 'English Translation'" in translations
    assert "'skills.translationProvider': 'Provider'" in translations
    assert "'skills.translationModel': 'Translation model'" in translations
    assert "'skills.translationCacheNote': 'Translations are cached outside the Hermes skills directory.'" in translations
    assert "'skills.applyModel': 'Apply model'" in translations
    assert "'skills.translate': 'Translate'" in translations
    assert "'skills.retranslate': 'Translate again'" in translations
    assert "'skills.translationGeneratedBy': 'Translated by {model}'" in translations
    assert "'skills.cachedTranslation': 'cached'" in translations
    assert "'skills.translationOnly': 'Translation only'" in translations
    assert "'skills.sideBySide': 'Side by Side'" in translations
    assert "'skills.syncCompare': 'Compare reading'" in translations
    assert "'skills.newSkill': 'New skill'" in translations
    assert "'skills.editSkill': 'Edit'" in translations
    assert "'skills.previewSkill': 'Preview'" in translations
    assert "'skills.saveSkill': 'Save skill'" in translations
    assert "'skills.deleteSkill': 'Delete'" in translations
    assert "'skills.enableSkill': 'Enable'" in translations
    assert "'skills.disableSkill': 'Disable'" in translations
    assert "'skills.confirmDeleteAction': 'Confirm delete'" in translations
    assert "'skills.enabled': 'Enabled'" in translations
    assert "'skills.disabled': 'Disabled'" in translations
    assert "'skills.batchEnable': 'Enable selected'" in translations
    assert "'skills.batchConfirmEnable': 'Confirm enabling {count}'" in translations
    assert "'skills.batchDisable': 'Disable selected'" in translations
    assert "'skills.batchConfirmDisable': 'Confirm disabling {count}'" in translations
    assert "'skills.batchExport': 'Export selected'" in translations
    assert "'skills.batchConfirmExport': 'Confirm exporting {count}'" in translations
    assert "'skills.batchDelete': 'Delete selected'" in translations
    assert "'skills.batchConfirmDelete': 'Confirm deleting {count}'" in translations
    assert "'skills.batchProgress': '{completed}/{total} completed'" in translations
    assert "'skills.batchSucceeded': '{count} succeeded'" in translations
    assert "'skills.batchFailed': '{count} failed'" in translations
    assert "'skills.retryFailed': 'Retry failed'" in translations
    assert "'skills.confirmRetryFailed': 'Confirm retrying {count}'" in translations
    assert "'skills.selectedCount': '{count} selected'" in translations
    assert "'skills.selectAllVisible': 'Select visible'" in translations
    assert "'skills.deselectAllVisible': 'Deselect visible'" in translations
    assert "'skills.importZip': 'Import ZIP'" in translations
    assert "'skills.skillMarket': 'Skill Market'" in translations
    assert "'skills.installSkill': 'Install'" in translations
    assert "'skills.searchMarket': 'Search official skills'" in translations
    assert "'skills.previewImport': 'Preview import'" in translations
    assert "'skills.confirmImport': 'Confirm import'" in translations
    assert "'skills.importWillAdd': 'Add'" in translations
    assert "'skills.importWillOverwrite': 'Overwrite'" in translations
    assert "'skills.importWillSkip': 'Skip'" in translations
    assert "'skills.marketInstalled': 'Installed'" in translations
    assert "'skills.reinstallSkill': 'Reinstall'" in translations
    assert "'skills.installingSkill': 'Installing...'" in translations
    assert "'skills.retryInstall': 'Retry'" in translations
    assert "'skills.installSucceeded': 'Installed successfully.'" in translations
    assert "'skills.category.data-science.label': 'Data Science'" in translations
    assert "'skills.category.data-science.description': 'Analysis, notebooks, datasets, and data workflows.'" in translations
    assert "'skills.original': '原文'" in translations
    assert "'skills.originalEnglish': '英文原文'" in translations
    assert "'skills.originalChinese': '中文原文'" in translations
    assert "'skills.translation': '译文'" in translations
    assert "'skills.translationChinese': '中文译文'" in translations
    assert "'skills.translationEnglish': '英文译文'" in translations
    assert "'skills.translationProvider': '提供商'" in translations
    assert "'skills.translationModel': '翻译模型'" in translations
    assert "'skills.translationCacheNote': '译文会缓存到 Hermes 技能目录之外。'" in translations
    assert "'skills.applyModel': '应用模型'" in translations
    assert "'skills.translate': '翻译'" in translations
    assert "'skills.retranslate': '重新翻译'" in translations
    assert "'skills.translationGeneratedBy': '当前译文由 {model} 生成'" in translations
    assert "'skills.cachedTranslation': '缓存'" in translations
    assert "'skills.translationOnly': '只看译文'" in translations
    assert "'skills.sideBySide': '中英对照'" in translations
    assert "'skills.syncCompare': '对照看'" in translations
    assert "'skills.newSkill': '新增技能'" in translations
    assert "'skills.editSkill': '编辑'" in translations
    assert "'skills.previewSkill': '预览'" in translations
    assert "'skills.saveSkill': '保存技能'" in translations
    assert "'skills.deleteSkill': '删除'" in translations
    assert "'skills.enableSkill': '启用'" in translations
    assert "'skills.disableSkill': '禁用'" in translations
    assert "'skills.confirmDeleteAction': '确认删除'" in translations
    assert "'skills.enabled': '已启用'" in translations
    assert "'skills.disabled': '已禁用'" in translations
    assert "'skills.batchEnable': '批量启用'" in translations
    assert "'skills.batchConfirmEnable': '确认启用 {count} 个'" in translations
    assert "'skills.batchDisable': '批量禁用'" in translations
    assert "'skills.batchConfirmDisable': '确认禁用 {count} 个'" in translations
    assert "'skills.batchExport': '批量导出'" in translations
    assert "'skills.batchConfirmExport': '确认导出 {count} 个'" in translations
    assert "'skills.batchDelete': '批量删除'" in translations
    assert "'skills.batchConfirmDelete': '确认删除 {count} 个'" in translations
    assert "'skills.batchProgress': '已完成 {completed}/{total}'" in translations
    assert "'skills.batchSucceeded': '成功 {count} 个'" in translations
    assert "'skills.batchFailed': '失败 {count} 个'" in translations
    assert "'skills.retryFailed': '重试失败项'" in translations
    assert "'skills.confirmRetryFailed': '确认重试 {count} 个'" in translations
    assert "'skills.selectedCount': '已选择 {count} 个'" in translations
    assert "'skills.selectAllVisible': '选择当前列表'" in translations
    assert "'skills.deselectAllVisible': '取消当前列表'" in translations
    assert "'skills.importZip': '导入 ZIP'" in translations
    assert "'skills.skillMarket': '技能市场'" in translations
    assert "'skills.installSkill': '安装'" in translations
    assert "'skills.searchMarket': '搜索官方技能'" in translations
    assert "'skills.previewImport': '预览导入'" in translations
    assert "'skills.confirmImport': '确认导入'" in translations
    assert "'skills.importWillAdd': '新增'" in translations
    assert "'skills.importWillOverwrite': '覆盖'" in translations
    assert "'skills.importWillSkip': '跳过'" in translations
    assert "'skills.marketInstalled': '已安装'" in translations
    assert "'skills.reinstallSkill': '重新安装'" in translations
    assert "'skills.installingSkill': '安装中...'" in translations
    assert "'skills.retryInstall': '重试'" in translations
    assert "'skills.installSucceeded': '安装成功。'" in translations
    assert "'skills.category.data-science.label': '数据科学'" in translations
    assert "'skills.category.data-science.description': '数据分析、Notebook、数据集和数据处理流程。'" in translations
