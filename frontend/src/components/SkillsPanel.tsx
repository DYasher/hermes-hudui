import { useCallback, useEffect, useRef, useState, type Ref } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import { useApi } from '../hooks/useApi'
import Panel from './Panel'
import { timeAgo, formatSize } from '../lib/utils'
import { useTranslation, type TranslationKey } from '../i18n'

type TranslationMode = 'side-by-side' | 'original' | 'translation'
type SkillTranslationProvider = {
  id: string
  name: string
  models: string[]
  is_default?: boolean
}
type SkillTranslationOptions = {
  default_provider: string
  default_model: string
  providers: SkillTranslationProvider[]
  cache_dir?: string
}

const TRANSLATION_PROVIDER_STORAGE_KEY = 'hud-skill-translation-provider'
const TRANSLATION_MODEL_STORAGE_KEY = 'hud-skill-translation-model'

const SKILL_CATEGORY_TRANSLATIONS = {
  apple: {
    labelKey: 'skills.category.apple.label',
    descriptionKey: 'skills.category.apple.description',
  },
  'autonomous-ai-agents': {
    labelKey: 'skills.category.autonomous-ai-agents.label',
    descriptionKey: 'skills.category.autonomous-ai-agents.description',
  },
  'computer-use': {
    labelKey: 'skills.category.computer-use.label',
    descriptionKey: 'skills.category.computer-use.description',
  },
  creative: {
    labelKey: 'skills.category.creative.label',
    descriptionKey: 'skills.category.creative.description',
  },
  'data-science': {
    labelKey: 'skills.category.data-science.label',
    descriptionKey: 'skills.category.data-science.description',
  },
  dogfood: {
    labelKey: 'skills.category.dogfood.label',
    descriptionKey: 'skills.category.dogfood.description',
  },
  email: {
    labelKey: 'skills.category.email.label',
    descriptionKey: 'skills.category.email.description',
  },
  github: {
    labelKey: 'skills.category.github.label',
    descriptionKey: 'skills.category.github.description',
  },
  media: {
    labelKey: 'skills.category.media.label',
    descriptionKey: 'skills.category.media.description',
  },
  migration: {
    labelKey: 'skills.category.migration.label',
    descriptionKey: 'skills.category.migration.description',
  },
  mlops: {
    labelKey: 'skills.category.mlops.label',
    descriptionKey: 'skills.category.mlops.description',
  },
  'note-taking': {
    labelKey: 'skills.category.note-taking.label',
    descriptionKey: 'skills.category.note-taking.description',
  },
  'openclaw-imports': {
    labelKey: 'skills.category.openclaw-imports.label',
    descriptionKey: 'skills.category.openclaw-imports.description',
  },
  productivity: {
    labelKey: 'skills.category.productivity.label',
    descriptionKey: 'skills.category.productivity.description',
  },
  research: {
    labelKey: 'skills.category.research.label',
    descriptionKey: 'skills.category.research.description',
  },
  'smart-home': {
    labelKey: 'skills.category.smart-home.label',
    descriptionKey: 'skills.category.smart-home.description',
  },
  'social-media': {
    labelKey: 'skills.category.social-media.label',
    descriptionKey: 'skills.category.social-media.description',
  },
  'software-development': {
    labelKey: 'skills.category.software-development.label',
    descriptionKey: 'skills.category.software-development.description',
  },
  uncategorized: {
    labelKey: 'skills.category.uncategorized.label',
    descriptionKey: 'skills.category.uncategorized.description',
  },
  yuanbao: {
    labelKey: 'skills.category.yuanbao.label',
    descriptionKey: 'skills.category.yuanbao.description',
  },
} as const

type SkillCategoryId = keyof typeof SKILL_CATEGORY_TRANSLATIONS

function humanizeCategoryName(category: string) {
  return category
    .replace(/^\.+/, '')
    .split(/[-_]+/)
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ') || category
}

function getSkillCategoryDisplay(category: string, t: (key: TranslationKey) => string) {
  const translation = SKILL_CATEGORY_TRANSLATIONS[category as SkillCategoryId]
  if (!translation) {
    return {
      label: humanizeCategoryName(category),
      description: t('skills.category.default.description'),
    }
  }

  return {
    label: t(translation.labelKey),
    description: t(translation.descriptionKey),
  }
}

function readStoredValue(key: string) {
  try {
    return localStorage.getItem(key) || ''
  } catch {
    return ''
  }
}

function storeValue(key: string, value: string) {
  try {
    if (value) localStorage.setItem(key, value)
    else localStorage.removeItem(key)
  } catch {
    // Local storage can be unavailable in private or embedded contexts.
  }
}

const markdownComponents = {
  h1: ({ node: _node, ...props }: any) => <h1 data-skill-sync-node="" data-skill-sync-heading="" {...props} />,
  h2: ({ node: _node, ...props }: any) => <h2 data-skill-sync-node="" data-skill-sync-heading="" {...props} />,
  h3: ({ node: _node, ...props }: any) => <h3 data-skill-sync-node="" data-skill-sync-heading="" {...props} />,
  h4: ({ node: _node, ...props }: any) => <h4 data-skill-sync-node="" data-skill-sync-heading="" {...props} />,
  h5: ({ node: _node, ...props }: any) => <h5 data-skill-sync-node="" data-skill-sync-heading="" {...props} />,
  h6: ({ node: _node, ...props }: any) => <h6 data-skill-sync-node="" data-skill-sync-heading="" {...props} />,
  p: ({ node: _node, ...props }: any) => <p data-skill-sync-node="" {...props} />,
  li: ({ node: _node, ...props }: any) => <li data-skill-sync-node="" {...props} />,
  pre: ({ node: _node, ...props }: any) => <pre data-skill-sync-node="" {...props} />,
  table: ({ node: _node, ...props }: any) => <table data-skill-sync-node="" {...props} />,
  blockquote: ({ node: _node, ...props }: any) => <blockquote data-skill-sync-node="" {...props} />,
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}

function elementTopWithin(container: HTMLDivElement, element: HTMLElement) {
  return element.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop
}

function getSyncAnchorTops(container: HTMLDivElement, selector: string) {
  return Array.from(container.querySelectorAll<HTMLElement>(selector))
    .map(element => elementTopWithin(container, element))
    .filter(top => Number.isFinite(top))
}

function normalizeAnchorTops(tops: number[], maxScrollTop: number) {
  const maxTop = Math.max(0, maxScrollTop)
  const anchors = [0]
  tops
    .map(top => clamp(top, 0, maxTop))
    .sort((a, b) => a - b)
    .forEach(top => {
      if (top > anchors[anchors.length - 1] + 4) anchors.push(top)
    })
  if (anchors[anchors.length - 1] < maxTop - 4) anchors.push(maxTop)
  return anchors
}

function getSyncedScrollFromAnchorTops(
  sourcePosition: number,
  sourceMax: number,
  targetMax: number,
  sourceTops: number[],
  targetTops: number[],
  fallback: number,
) {
  const sourceAnchors = normalizeAnchorTops(sourceTops, sourceMax)
  const targetAnchors = normalizeAnchorTops(targetTops, targetMax)
  const anchorCount = Math.min(sourceAnchors.length, targetAnchors.length)
  if (anchorCount < 2) return clamp(fallback, 0, Math.max(0, targetMax))

  let anchorIndex = 0
  while (
    anchorIndex < anchorCount - 2
    && sourceAnchors[anchorIndex + 1] <= sourcePosition + 8
  ) {
    anchorIndex += 1
  }

  const sourceStart = sourceAnchors[anchorIndex]
  const sourceEnd = sourceAnchors[anchorIndex + 1]
  const targetStart = targetAnchors[anchorIndex]
  const targetEnd = targetAnchors[anchorIndex + 1]
  const segmentRatio = sourceEnd > sourceStart
    ? clamp((sourcePosition - sourceStart) / (sourceEnd - sourceStart), 0, 1)
    : 0

  return clamp(targetStart + segmentRatio * (targetEnd - targetStart), 0, Math.max(0, targetMax))
}

function computeSyncedScrollTop(source: HTMLDivElement, target: HTMLDivElement) {
  const sourceMax = source.scrollHeight - source.clientHeight
  const targetMax = target.scrollHeight - target.clientHeight
  const fallback = sourceMax > 0 && targetMax > 0
    ? (source.scrollTop / sourceMax) * targetMax
    : 0

  const sourceHeadingTops = getSyncAnchorTops(source, '[data-skill-sync-heading]')
  const targetHeadingTops = getSyncAnchorTops(target, '[data-skill-sync-heading]')
  if (
    sourceHeadingTops.length >= 2
    && sourceHeadingTops.length === targetHeadingTops.length
  ) {
    return getSyncedScrollFromAnchorTops(
      source.scrollTop,
      sourceMax,
      targetMax,
      sourceHeadingTops,
      targetHeadingTops,
      fallback,
    )
  }

  const sourceTops = getSyncAnchorTops(source, '[data-skill-sync-node]')
  const targetTops = getSyncAnchorTops(target, '[data-skill-sync-node]')
  if (sourceTops.length < 2 || targetTops.length < 2) {
    return clamp(fallback, 0, Math.max(0, targetMax))
  }
  return getSyncedScrollFromAnchorTops(
    source.scrollTop,
    sourceMax,
    targetMax,
    sourceTops,
    targetTops,
    fallback,
  )
}

function SkillItem({
  skill,
  variant,
  selected,
  onSelect,
}: {
  skill: any
  variant: 'category' | 'recent'
  selected: boolean
  onSelect: () => void
}) {
  const { t } = useTranslation()
  const descLimit = variant === 'category' ? 120 : 100
  const categoryDisplay = getSkillCategoryDisplay(skill.category || '', t)
  return (
    <button
      type="button"
      onClick={onSelect}
      className="block w-full py-2 px-2 text-[13px] text-left cursor-pointer transition-colors"
      style={{
        background: selected ? 'var(--hud-bg-hover)' : 'transparent',
        borderLeft: selected ? '2px solid var(--hud-primary)' : '2px solid var(--hud-border)',
      }}
      title={t('skills.openDetail')}
    >
      <div className="flex items-center gap-2 mb-0.5">
        <span className="font-bold" style={{ color: 'var(--hud-primary)' }}>{skill.name}</span>
        {variant === 'recent' && (
          <span className="text-[13px] px-1" style={{ background: 'var(--hud-bg-panel)', color: 'var(--hud-text-dim)' }}>
            {categoryDisplay.label}
          </span>
        )}
        {skill.is_custom && (
          <span className="text-[13px] px-1" style={{ background: 'var(--hud-accent)', color: 'var(--hud-bg-deep)' }}>{t('dashboard.custom')}</span>
        )}
        {variant === 'category' && (
          <span className="text-[13px] ml-auto" style={{ color: 'var(--hud-text-dim)' }}>
            {formatSize(skill.file_size)}
          </span>
        )}
      </div>
      <div style={{ color: 'var(--hud-text-dim)' }}>
        {skill.description?.slice(0, descLimit)}{skill.description?.length > descLimit ? '...' : ''}
      </div>
      <div className="text-[13px] mt-0.5" style={{ color: 'var(--hud-text-dim)' }}>
        {variant === 'category'
          ? `${skill.modified_at ? new Date(skill.modified_at).toLocaleDateString() : ''} · ${skill.path?.split('/').slice(-3).join('/')}`
          : skill.modified_at ? timeAgo(skill.modified_at) : ''
        }
      </div>
    </button>
  )
}

function MarkdownPane({
  title,
  content,
  tone = 'default',
  scrollRef,
  onScroll,
}: {
  title: string
  content: string
  tone?: 'default' | 'translation'
  scrollRef?: Ref<HTMLDivElement>
  onScroll?: () => void
}) {
  return (
    <section className="min-h-0 flex flex-col border" style={{ borderColor: 'var(--hud-border)' }}>
      <div
        className="px-3 py-2 text-[11px] uppercase tracking-widest shrink-0"
        style={{
          color: tone === 'translation' ? 'var(--hud-accent)' : 'var(--hud-primary)',
          borderBottom: '1px solid var(--hud-border)',
          background: 'var(--hud-bg-panel)',
        }}
      >
        {title}
      </div>
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="prose-hud flex-1 min-h-0 overflow-y-auto p-3 text-[13px]"
        style={{ color: 'var(--hud-text)' }}
      >
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeHighlight]}
          components={markdownComponents}
        >
          {content}
        </ReactMarkdown>
      </div>
    </section>
  )
}

function SkillDetailModal({ path, onClose }: { path: string; onClose: () => void }) {
  const { t } = useTranslation()
  const [translationMode, setTranslationMode] = useState<TranslationMode>('side-by-side')
  const [syncCompareEnabled, setSyncCompareEnabled] = useState(true)
  const [translation, setTranslation] = useState('')
  const [translationSourceLang, setTranslationSourceLang] = useState('')
  const [translationTargetLang, setTranslationTargetLang] = useState('')
  const [translationLoading, setTranslationLoading] = useState(false)
  const [translationError, setTranslationError] = useState('')
  const [translationRenderKey, setTranslationRenderKey] = useState(0)
  const [draftTranslationProvider, setDraftTranslationProvider] = useState(() => readStoredValue(TRANSLATION_PROVIDER_STORAGE_KEY))
  const [draftTranslationModel, setDraftTranslationModel] = useState(() => readStoredValue(TRANSLATION_MODEL_STORAGE_KEY))
  const [appliedTranslationProvider, setAppliedTranslationProvider] = useState(() => readStoredValue(TRANSLATION_PROVIDER_STORAGE_KEY))
  const [appliedTranslationModel, setAppliedTranslationModel] = useState(() => readStoredValue(TRANSLATION_MODEL_STORAGE_KEY))
  const [translatedByProvider, setTranslatedByProvider] = useState('')
  const [translatedByModel, setTranslatedByModel] = useState('')
  const [translationCached, setTranslationCached] = useState(false)
  const [translationModelApplyTick, setTranslationModelApplyTick] = useState(0)
  const originalScrollRef = useRef<HTMLDivElement | null>(null)
  const translationScrollRef = useRef<HTMLDivElement | null>(null)
  const syncingScrollRef = useRef(false)
  const { data, isLoading, error } = useApi(
    `/skills/detail?path=${encodeURIComponent(path)}`,
    0,
  )
  const { data: translationOptions } = useApi<SkillTranslationOptions>('/skills/translation-options', 60000)
  const isCurrentDetail = data?.path === path
  const providerOptions = translationOptions?.providers || []
  const selectedProviderOption = providerOptions.find(provider => provider.id === draftTranslationProvider)
  const modelOptions = selectedProviderOption?.models || []
  const modelDisplayOptions = draftTranslationModel && !modelOptions.includes(draftTranslationModel)
    ? [draftTranslationModel, ...modelOptions]
    : modelOptions
  const appliedProviderOption = providerOptions.find(provider => provider.id === appliedTranslationProvider)
  const appliedModelOptions = appliedProviderOption?.models || []
  const translationOptionsReady = Boolean(translationOptions)

  useEffect(() => {
    if (!translationOptions) return

    const fallbackProvider = translationOptions.default_provider || providerOptions[0]?.id || ''
    const nextDraftProvider = draftTranslationProvider || fallbackProvider
    const nextAppliedProvider = appliedTranslationProvider || nextDraftProvider
    if (nextDraftProvider !== draftTranslationProvider) {
      setDraftTranslationProvider(nextDraftProvider)
    }
    if (nextAppliedProvider !== appliedTranslationProvider) {
      setAppliedTranslationProvider(nextAppliedProvider)
      storeValue(TRANSLATION_PROVIDER_STORAGE_KEY, nextAppliedProvider)
    }

    const provider = providerOptions.find(option => option.id === nextDraftProvider)
    const models = provider?.models || []
    const defaultModel = nextDraftProvider === translationOptions.default_provider ? translationOptions.default_model : ''
    const fallbackModel = defaultModel && models.includes(defaultModel)
      ? defaultModel
      : models[0] || defaultModel || ''
    const draftModelAvailable = !models.length || !draftTranslationModel || models.includes(draftTranslationModel)
    const nextDraftModel = draftModelAvailable ? draftTranslationModel || fallbackModel : fallbackModel
    const appliedModelAvailable = !models.length || !appliedTranslationModel || models.includes(appliedTranslationModel)
    const nextAppliedModel = appliedModelAvailable ? appliedTranslationModel || nextDraftModel : nextDraftModel
    if (nextDraftModel !== draftTranslationModel) {
      setDraftTranslationModel(nextDraftModel)
    }
    if (nextAppliedModel !== appliedTranslationModel) {
      setAppliedTranslationModel(nextAppliedModel)
      storeValue(TRANSLATION_MODEL_STORAGE_KEY, nextAppliedModel)
    }
  }, [translationOptions, providerOptions, draftTranslationProvider, draftTranslationModel, appliedTranslationProvider, appliedTranslationModel])

  useEffect(() => {
    setTranslation('')
    setTranslationSourceLang('')
    setTranslationTargetLang('')
    setTranslationError('')
    setTranslationLoading(false)
    setTranslatedByProvider('')
    setTranslatedByModel('')
    setTranslationCached(false)
    setTranslationRenderKey(current => current + 1)
  }, [path])

  const applyTranslationPayload = (payload: any) => {
    setTranslation(payload.translation || '')
    setTranslationSourceLang(payload.source_lang || '')
    setTranslationTargetLang(payload.target_lang || '')
    setTranslatedByProvider(payload.provider || appliedTranslationProvider || '')
    setTranslatedByModel(payload.model || appliedTranslationModel || '')
    setTranslationCached(Boolean(payload.cached))
    setTranslationRenderKey(current => current + 1)
  }

  const runTranslation = (force: boolean, cacheOnly = false) => {
    if (!isCurrentDetail || !data?.path || !data?.content) return
    if (!translationOptionsReady) return
    if (providerOptions.length > 0 && !appliedTranslationProvider) return
    if (appliedModelOptions.length > 0 && !appliedTranslationModel) return

    if (!cacheOnly) {
      setTranslation('')
      setTranslationError('')
      setTranslationLoading(true)
      setTranslationCached(false)
      setTranslationRenderKey(current => current + 1)
    }

    fetch('/api/skills/translate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        path: data.path,
        target_lang: 'auto',
        provider: appliedTranslationProvider || undefined,
        model: appliedTranslationModel || undefined,
        force,
        cache_only: cacheOnly,
      }),
    })
      .then(async res => {
        if (!res.ok) throw new Error(await res.text())
        return res.json()
      })
      .then(payload => {
        if (payload.cache_miss) return
        applyTranslationPayload(payload)
      })
      .catch(err => {
        if (!cacheOnly) {
          const message = err instanceof Error ? err.message : String(err)
          setTranslationError(message)
          setTranslationRenderKey(current => current + 1)
        }
      })
      .finally(() => {
        if (!cacheOnly) setTranslationLoading(false)
      })
  }

  useEffect(() => {
    if (!isCurrentDetail || !data?.path || !data?.content) return
    if (!translationOptionsReady) return
    if (providerOptions.length > 0 && !appliedTranslationProvider) return
    if (appliedModelOptions.length > 0 && !appliedTranslationModel) return
    setTranslation('')
    setTranslationError('')
    setTranslatedByProvider('')
    setTranslatedByModel('')
    setTranslationCached(false)
    setTranslationRenderKey(current => current + 1)
    runTranslation(false, true)
  }, [data?.path, data?.content, isCurrentDetail, translationOptionsReady, appliedTranslationProvider, appliedTranslationModel, translationModelApplyTick, t])

  const updateTranslationProvider = (providerId: string) => {
    const provider = providerOptions.find(option => option.id === providerId)
    const defaultModel = providerId === translationOptions?.default_provider ? translationOptions?.default_model || '' : ''
    const nextModel = defaultModel && provider?.models.includes(defaultModel)
      ? defaultModel
      : provider?.models[0] || defaultModel || ''
    setDraftTranslationProvider(providerId)
    setDraftTranslationModel(provider ? nextModel : '')
  }

  const updateTranslationModel = (model: string) => {
    setDraftTranslationModel(model)
  }

  const applyTranslationModel = () => {
    const provider = draftTranslationProvider.trim()
    const model = draftTranslationModel.trim()
    setAppliedTranslationProvider(provider)
    setAppliedTranslationModel(model)
    storeValue(TRANSLATION_PROVIDER_STORAGE_KEY, provider)
    storeValue(TRANSLATION_MODEL_STORAGE_KEY, model)
    setTranslation('')
    setTranslationError('')
    setTranslatedByProvider('')
    setTranslatedByModel('')
    setTranslationCached(false)
    setTranslationRenderKey(current => current + 1)
    setTranslationModelApplyTick(current => current + 1)
  }

  const showOriginal = translationMode === 'side-by-side' || translationMode === 'original'
  const showTranslation = translationMode === 'side-by-side' || translationMode === 'translation'
  const canSyncCompare = syncCompareEnabled && showOriginal && showTranslation
  const syncPaneScroll = useCallback((source: HTMLDivElement | null, target: HTMLDivElement | null) => {
    if (!canSyncCompare || !source || !target || syncingScrollRef.current) return
    syncingScrollRef.current = true
    target.scrollTop = computeSyncedScrollTop(source, target)
    requestAnimationFrame(() => {
      syncingScrollRef.current = false
    })
  }, [canSyncCompare])

  useEffect(() => {
    if (!canSyncCompare) return
    const frame = requestAnimationFrame(() => {
      syncPaneScroll(originalScrollRef.current, translationScrollRef.current)
    })
    return () => cancelAnimationFrame(frame)
  }, [canSyncCompare, data?.path, translationRenderKey, syncPaneScroll])

  const originalTitle = translationSourceLang === 'zh'
    ? t('skills.originalChinese')
    : translationSourceLang === 'en'
      ? t('skills.originalEnglish')
      : t('skills.original')
  const translationTitle = translationTargetLang === 'en'
    ? t('skills.translationEnglish')
    : translationTargetLang === 'zh'
      ? t('skills.translationChinese')
      : t('skills.translation')
  const translatorLabel = [translatedByProvider, translatedByModel].filter(Boolean).join(' / ')
  const translationActionLabel = translation ? t('skills.retranslate') : t('skills.translate')
  const detailCategoryDisplay = data?.category ? getSkillCategoryDisplay(data.category, t) : null
  const translatedContent = translationLoading
    ? t('skills.translating')
    : translationError
      ? `${t('skills.translationUnavailable')}\n\n${translationError}`
      : translation || t('skills.translationPending')

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-3"
      style={{ background: 'rgba(0,0,0,0.72)' }}
      role="dialog"
      aria-modal="true"
      aria-label={data?.name || t('skills.detail')}
    >
      <div
        className="w-full max-w-7xl h-[92vh] min-h-0 flex flex-col overflow-hidden"
        style={{
          background: 'var(--hud-bg-surface)',
          border: '1px solid var(--hud-border)',
          boxShadow: '0 12px 48px rgba(0,0,0,0.62)',
        }}
      >
        <div className="shrink-0 px-4 py-3 border-b" style={{ borderColor: 'var(--hud-border)' }}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-[15px] font-bold truncate" style={{ color: 'var(--hud-primary)' }}>
                {data?.name || t('skills.detail')}
              </div>
              <div className="mt-1 flex flex-wrap gap-2 text-[12px]">
                {detailCategoryDisplay && (
                  <span className="px-1.5 py-0.5" style={{ background: 'var(--hud-bg-panel)', color: 'var(--hud-primary)' }}>
                    {detailCategoryDisplay.label}
                  </span>
                )}
                <span style={{ color: 'var(--hud-text-dim)' }}>
                  {formatSize(data?.file_size || 0)}
                </span>
                {data?.modified_at && (
                  <span style={{ color: 'var(--hud-text-dim)' }}>
                    {new Date(data.modified_at).toLocaleString()}
                  </span>
                )}
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="px-2 py-1 text-[13px] shrink-0 cursor-pointer"
              style={{ color: 'var(--hud-text-dim)', border: '1px solid var(--hud-border)' }}
            >
              x {t('skills.close')}
            </button>
          </div>
          {data?.description && (
            <div className="mt-2 text-[13px]" style={{ color: 'var(--hud-text-dim)' }}>{data.description}</div>
          )}
          {data?.path && (
            <div className="mt-1 truncate text-[11px] font-mono" style={{ color: 'var(--hud-text-dim)' }}>
              {data.path}
            </div>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            {[
              ['side-by-side', t('skills.sideBySide')],
              ['original', t('skills.originalOnly')],
              ['translation', t('skills.translationOnly')],
            ].map(([mode, label]) => (
              <button
                type="button"
                key={mode}
                onClick={() => setTranslationMode(mode as TranslationMode)}
                className="px-2 py-1 text-[12px] cursor-pointer"
                style={{
                  color: translationMode === mode ? 'var(--hud-bg-deep)' : 'var(--hud-text-dim)',
                  background: translationMode === mode ? 'var(--hud-primary)' : 'transparent',
                  border: '1px solid var(--hud-border)',
                }}
              >
                {label}
              </button>
            ))}
            <button
              type="button"
              onClick={() => setSyncCompareEnabled(current => !current)}
              disabled={!showOriginal || !showTranslation}
              aria-pressed={canSyncCompare}
              className="px-2 py-1 text-[12px] cursor-pointer disabled:opacity-40"
              style={{
                color: canSyncCompare ? 'var(--hud-bg-deep)' : 'var(--hud-text-dim)',
                background: canSyncCompare ? 'var(--hud-accent)' : 'transparent',
                border: '1px solid var(--hud-border)',
              }}
            >
              {t('skills.syncCompare')}
            </button>
          </div>
          <div className="mt-3 grid grid-cols-1 md:grid-cols-[minmax(160px,220px)_minmax(220px,1fr)_auto] gap-2 items-end">
            <label className="text-[11px] uppercase tracking-widest" style={{ color: 'var(--hud-text-dim)' }}>
              <span className="block mb-1">{t('skills.translationProvider')}</span>
              <select
                value={draftTranslationProvider}
                onChange={event => updateTranslationProvider(event.target.value)}
                data-skill-translation-provider
                className="w-full px-2 py-1.5 text-[12px] outline-none"
                style={{ background: 'var(--hud-bg-panel)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)' }}
              >
                <option value="">{t('skills.translationProvider')}</option>
                {providerOptions.map(provider => (
                  <option key={provider.id} value={provider.id}>
                    {provider.name ? `${provider.name} (${provider.id})` : provider.id}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-[11px] uppercase tracking-widest" style={{ color: 'var(--hud-text-dim)' }}>
              <span className="block mb-1">{t('skills.translationModel')}</span>
              <select
                value={draftTranslationModel}
                onChange={event => updateTranslationModel(event.target.value)}
                data-skill-translation-model
                className="w-full px-2 py-1.5 text-[12px] outline-none font-mono"
                style={{ background: 'var(--hud-bg-panel)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)' }}
              >
                <option value="">{t('skills.translationModel')}</option>
                {modelDisplayOptions.map(model => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={applyTranslationModel}
                className="px-2 py-1.5 text-[12px] cursor-pointer"
                style={{ color: 'var(--hud-primary)', background: 'transparent', border: '1px solid var(--hud-border)' }}
              >
                {t('skills.applyModel')}
              </button>
              <button
                type="button"
                onClick={() => runTranslation(true)}
                disabled={translationLoading || !appliedTranslationModel}
                className="px-2 py-1.5 text-[12px] cursor-pointer disabled:opacity-40"
                style={{ color: 'var(--hud-bg-deep)', background: 'var(--hud-primary)', border: '1px solid var(--hud-primary)' }}
              >
                {translationLoading ? '...' : translationActionLabel}
              </button>
            </div>
          </div>
          <div className="mt-2 flex flex-wrap gap-3 text-[11px]" style={{ color: 'var(--hud-text-dim)' }}>
            <span>{t('skills.translationCacheNote')}</span>
            {translatorLabel && (
              <span style={{ color: 'var(--hud-accent)' }}>
                {t('skills.translationGeneratedBy').replace('{model}', translatorLabel)}
                {translationCached ? ` (${t('skills.cachedTranslation')})` : ''}
              </span>
            )}
          </div>
        </div>

        <div className="flex-1 min-h-0 overflow-hidden p-3">
          {(isLoading && !isCurrentDetail) && (
            <div className="glow text-[13px] animate-pulse">{t('skills.loadingDetail')}</div>
          )}
          {error && (
            <div className="text-[13px]" style={{ color: 'var(--hud-error)' }}>
              {t('skills.detailUnavailable')}
            </div>
          )}
          {!error && isCurrentDetail && data && (
            <div className={`h-full min-h-0 grid gap-3 ${showOriginal && showTranslation ? 'grid grid-cols-1 lg:grid-cols-2' : 'grid grid-cols-1'}`}>
              {showOriginal && (
                <MarkdownPane
                  title={originalTitle}
                  content={data?.content || ''}
                  scrollRef={originalScrollRef}
                  onScroll={() => syncPaneScroll(originalScrollRef.current, translationScrollRef.current)}
                />
              )}
              {showTranslation && (
                <MarkdownPane
                  key={`${data.path}:${translationTargetLang}:${translationRenderKey}`}
                  title={translationTitle}
                  content={translatedContent}
                  tone="translation"
                  scrollRef={translationScrollRef}
                  onScroll={() => syncPaneScroll(translationScrollRef.current, originalScrollRef.current)}
                />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function SkillsPanel() {
  const { t } = useTranslation()
  const { data, isLoading, error } = useApi('/skills', 60000)
  const [selectedCat, setSelectedCat] = useState<string | null>(null)
  const [selectedSkillPath, setSelectedSkillPath] = useState<string | null>(null)

  // Only show loading on initial load
  if (isLoading && !data) {
    return <Panel title={t('skills.title')} className="col-span-full"><div className="glow text-[13px] animate-pulse">{t('skills.scanning')}</div></Panel>
  }

  if (error && !data) {
    return (
      <Panel title={t('skills.title')} className="col-span-full">
        <div className="text-[13px]" style={{ color: 'var(--hud-error)' }}>
          {t('skills.detailUnavailable')}
        </div>
      </Panel>
    )
  }

  const catCounts: Record<string, number> = data?.category_counts || {}
  const byCategory: Record<string, any[]> = data?.by_category || {}
  const recentlyMod = data?.recently_modified || []

  // Sort categories by count descending
  const sorted = Object.entries(catCounts).sort((a: any, b: any) => b[1] - a[1])
  const maxCount = sorted.length > 0 ? sorted[0][1] : 1

  // Skills in selected category
  const catSkills = selectedCat ? byCategory[selectedCat] || [] : []
  const selectedCategoryDisplay = selectedCat ? getSkillCategoryDisplay(selectedCat, t) : null

  return (
    <>
      {selectedSkillPath && (
        <SkillDetailModal
          path={selectedSkillPath}
          onClose={() => setSelectedSkillPath(null)}
        />
      )}

      {/* Category overview */}
      <Panel title={t('dashboard.skillLibrary')} className="col-span-1">
        <div className="flex gap-2 mb-3">
          <span className="text-[13px] px-2 py-0.5" style={{ background: 'var(--hud-bg-panel)', color: 'var(--hud-primary)' }}>
            {data?.total || 0} {t('dashboard.total')}
          </span>
          <span className="text-[13px] px-2 py-0.5" style={{ background: 'var(--hud-bg-panel)', color: 'var(--hud-accent)' }}>
            {data?.custom_count || 0} {t('dashboard.custom')}
          </span>
          <span className="text-[13px]" style={{ color: 'var(--hud-text-dim)' }}>
            {sorted.length} {t('dashboard.categories')}
          </span>
        </div>

        {/* Category bar chart — scannable at a glance */}
        <div className="space-y-1 text-[13px]">
          {sorted.map(([cat, count]) => {
            const pct = (count / maxCount) * 100
            const isSelected = selectedCat === cat
            const categoryDisplay = getSkillCategoryDisplay(cat, t)
            return (
              <button
                key={cat}
                onClick={() => {
                  setSelectedCat(isSelected ? null : cat)
                  setSelectedSkillPath(null)
                }}
                className="flex items-center gap-2 w-full py-1 px-2 text-left transition-colors"
                style={{
                  background: isSelected ? 'var(--hud-bg-hover)' : 'transparent',
                  borderLeft: isSelected ? '2px solid var(--hud-primary)' : '2px solid transparent',
                }}
                title={`${categoryDisplay.label} · ${categoryDisplay.description}`}
              >
                <span className="w-[160px] min-w-0" style={{ color: isSelected ? 'var(--hud-primary)' : 'var(--hud-text)' }}>
                  <span className="block truncate">{categoryDisplay.label}</span>
                  <span className="block truncate text-[11px]" style={{ color: 'var(--hud-text-dim)' }}>
                    {categoryDisplay.description}
                  </span>
                </span>
                <div className="flex-1 h-[6px]" style={{ background: 'var(--hud-bg-panel)' }}>
                  <div
                    style={{
                      width: `${pct}%`,
                      height: '100%',
                      background: isSelected ? 'var(--hud-primary)' : 'var(--hud-primary-dim)',
                    }}
                  />
                </div>
                <span className="tabular-nums w-8 text-right" style={{ color: isSelected ? 'var(--hud-primary)' : 'var(--hud-text-dim)' }}>
                  {count}
                </span>
              </button>
            )
          })}
        </div>
      </Panel>

      {/* Selected category skills OR recently modified */}
      {selectedCat ? (
        <Panel title={selectedCategoryDisplay?.label || selectedCat}>
          <div className="space-y-2">
            {selectedCategoryDisplay?.description && (
              <div className="text-[13px]" style={{ color: 'var(--hud-text-dim)' }}>
                {selectedCategoryDisplay.description}
              </div>
            )}
            {catSkills.map((skill: any) => (
              <SkillItem
                key={skill.path || skill.name}
                skill={skill}
                variant="category"
                selected={selectedSkillPath === skill.path}
                onSelect={() => setSelectedSkillPath(skill.path)}
              />
            ))}
            {catSkills.length === 0 && (
              <div className="text-[13px]" style={{ color: 'var(--hud-text-dim)' }}>{t('dashboard.noSkillsInCategory')}</div>
            )}
          </div>
        </Panel>
      ) : (
        <Panel title={t('dashboard.recentlyModified')}>
          <div className="space-y-2">
            {recentlyMod.map((skill: any) => (
              <SkillItem
                key={skill.path || skill.name}
                skill={skill}
                variant="recent"
                selected={selectedSkillPath === skill.path}
                onSelect={() => setSelectedSkillPath(skill.path)}
              />
            ))}
            {recentlyMod.length === 0 && (
              <div className="text-[13px]" style={{ color: 'var(--hud-text-dim)' }}>{t('dashboard.noRecentModifications')}</div>
            )}
          </div>
        </Panel>
      )}
    </>
  )
}
