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
type SkillInfo = {
  name: string
  category: string
  description?: string
  path: string
  modified_at?: string
  file_size?: number
  is_custom?: boolean
  enabled?: boolean
}
type SkillsPayload = {
  total: number
  custom_count: number
  skills?: SkillInfo[]
  category_counts: Record<string, number>
  by_category: Record<string, SkillInfo[]>
  recently_modified: SkillInfo[]
}
type SkillDetail = SkillInfo & {
  content: string
}
type SkillMarketItem = {
  identifier: string
  name: string
  description?: string
  source?: string
  category?: string
  version?: string
  installed?: boolean
  installed_category?: string
  installed_path?: string
}
type SkillMarketInstallState = {
  status: 'installing' | 'success' | 'error'
  message?: string
}
type SkillImportItem = {
  name: string
  category: string
  status: 'add' | 'overwrite' | 'skip' | 'installed' | 'overwritten' | 'skipped'
}
type SkillImportPreview = {
  preview: true
  filename: string
  add_count: number
  overwrite_count: number
  skip_count: number
  items: SkillImportItem[]
}
type SkillImportResult = {
  filename: string
  installed_count: number
  items: SkillImportItem[]
}

const TRANSLATION_PROVIDER_STORAGE_KEY = 'hud-skill-translation-provider'
const TRANSLATION_MODEL_STORAGE_KEY = 'hud-skill-translation-model'

const skillFilterOptionStyle = {
  backgroundColor: 'var(--hud-bg-panel)',
  color: 'var(--hud-text)',
}

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

async function readJsonResponse(res: Response) {
  const payload = await res.json().catch(() => null)
  if (!res.ok) {
    const detail = payload?.detail || payload?.message || res.statusText
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return payload
}

async function createSkill(payload: {
  category: string
  name: string
  description: string
  content: string
}) {
  const res = await fetch('/api/skills', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return readJsonResponse(res)
}

async function saveSkillContent(path: string, content: string) {
  const res = await fetch('/api/skills/detail', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, content }),
  })
  return readJsonResponse(res)
}

async function deleteSkill(path: string) {
  const res = await fetch('/api/skills', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  return readJsonResponse(res)
}

async function toggleSkillEnabled(name: string, enabled: boolean) {
  const res = await fetch('/api/skills/toggle', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, enabled }),
  })
  return readJsonResponse(res)
}

async function importSkillsZip(file: File, overwrite: boolean, preview: boolean) {
  const params = new URLSearchParams({
    filename: file.name,
    overwrite: String(overwrite),
    preview: String(preview),
  })
  const res = await fetch(`/api/skills/import-zip?${params.toString()}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/zip' },
    body: file,
  })
  return readJsonResponse(res)
}

async function downloadSkillsBackup() {
  const res = await fetch('/api/skills/backup')
  if (!res.ok) {
    const payload = await res.json().catch(() => null)
    const detail = payload?.detail || payload?.message || res.statusText
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }

  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'hermes-skills-backup.zip'
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

async function searchSkillMarket(query: string, source: string) {
  const params = new URLSearchParams({
    q: query,
    source,
    limit: '30',
  })
  const res = await fetch(`/api/skills/market/search?${params.toString()}`)
  return readJsonResponse(res)
}

async function installMarketSkill(identifier: string, category: string, force: boolean) {
  const res = await fetch('/api/skills/market/install', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      identifier,
      category: category || undefined,
      force,
    }),
  })
  return readJsonResponse(res)
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
  onToggle,
  onDelete,
  selectedForBatch,
  onBatchSelect,
  deleteConfirming,
  busy,
}: {
  skill: SkillInfo
  variant: 'category' | 'recent'
  selected: boolean
  onSelect: () => void
  onToggle: (skill: SkillInfo) => void
  onDelete: (skill: SkillInfo) => void
  selectedForBatch: boolean
  onBatchSelect: (skill: SkillInfo, selected: boolean) => void
  deleteConfirming: boolean
  busy?: boolean
}) {
  const { t } = useTranslation()
  const descLimit = variant === 'category' ? 120 : 100
  const categoryDisplay = getSkillCategoryDisplay(skill.category || '', t)
  return (
    <div
      className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-2 w-full py-2 px-2 text-[13px] transition-colors"
      style={{
        background: selected ? 'var(--hud-bg-hover)' : 'transparent',
        borderLeft: selected ? '2px solid var(--hud-primary)' : '2px solid var(--hud-border)',
      }}
    >
      <label className="pt-1 cursor-pointer">
        <input
          type="checkbox"
          checked={selectedForBatch}
          onChange={event => onBatchSelect(skill, event.target.checked)}
          disabled={busy}
        />
      </label>
      <button
        type="button"
        onClick={onSelect}
        className="block w-full min-w-0 text-left cursor-pointer"
        title={t('skills.openDetail')}
      >
        <div className="flex items-center gap-2 mb-0.5">
          <span className="font-bold" style={{ color: 'var(--hud-primary)' }}>{skill.name}</span>
          <span
            className="text-[10px] px-1 leading-4"
            style={{
              background: skill.enabled === false ? 'var(--hud-soft-block)' : 'var(--hud-primary)',
              color: skill.enabled === false ? 'var(--hud-warning)' : 'var(--hud-bg-deep)',
            }}
          >
            {skill.enabled === false ? t('skills.disabled') : t('skills.enabled')}
          </span>
          {variant === 'recent' && (
            <span className="text-[10px] px-1 leading-4" style={{ background: 'var(--hud-solid-block)', color: 'var(--hud-text-dim)' }}>
              {categoryDisplay.label}
            </span>
          )}
          {skill.is_custom && (
            <span className="text-[10px] px-1 leading-4" style={{ background: 'var(--hud-accent)', color: 'var(--hud-bg-deep)' }}>{t('dashboard.custom')}</span>
          )}
          {variant === 'category' && (
            <span className="text-[13px] ml-auto" style={{ color: 'var(--hud-text-dim)' }}>
              {formatSize(skill.file_size || 0)}
            </span>
          )}
        </div>
        <div style={{ color: 'var(--hud-text-dim)' }}>
          {skill.description?.slice(0, descLimit)}{skill.description && skill.description.length > descLimit ? '...' : ''}
        </div>
        <div className="text-[13px] mt-0.5" style={{ color: 'var(--hud-text-dim)' }}>
          {variant === 'category'
            ? `${skill.modified_at ? new Date(skill.modified_at).toLocaleDateString() : ''} · ${skill.path?.split('/').slice(-3).join('/')}`
            : skill.modified_at ? timeAgo(skill.modified_at) : ''
          }
        </div>
      </button>
      <div data-skill-row-actions className="flex shrink-0 flex-col items-stretch gap-1">
        <button
          type="button"
          onClick={() => onToggle(skill)}
          disabled={busy}
          className="px-1.5 py-0.5 text-[11px] cursor-pointer disabled:opacity-40"
          style={{ color: 'var(--hud-primary)', border: '1px solid var(--hud-border)' }}
        >
          {skill.enabled === false ? t('skills.enableSkill') : t('skills.disableSkill')}
        </button>
        <button
          type="button"
          onClick={() => onDelete(skill)}
          disabled={busy}
          className="px-1.5 py-0.5 text-[11px] cursor-pointer disabled:opacity-40"
          style={{ color: 'var(--hud-error)', border: '1px solid var(--hud-border)' }}
        >
          {deleteConfirming ? t('skills.confirmDeleteAction') : t('skills.deleteSkill')}
        </button>
      </div>
    </div>
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
          background: 'var(--hud-solid-block)',
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

function SkillDetailModal({
  path,
  onClose,
  onChanged,
}: {
  path: string
  onClose: () => void
  onChanged: () => void
}) {
  const { t } = useTranslation()
  const [translationMode, setTranslationMode] = useState<TranslationMode>('side-by-side')
  const [syncCompareEnabled, setSyncCompareEnabled] = useState(true)
  const [isEditing, setIsEditing] = useState(false)
  const [editorContent, setEditorContent] = useState('')
  const [editorError, setEditorError] = useState('')
  const [editorSaving, setEditorSaving] = useState(false)
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
  const { data, isLoading, error, mutate } = useApi<SkillDetail>(
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
    setIsEditing(false)
    setEditorContent('')
    setEditorError('')
  }, [path])

  useEffect(() => {
    if (isCurrentDetail && data?.content && !isEditing) {
      setEditorContent(data.content)
    }
  }, [data?.content, isCurrentDetail, isEditing])

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

  const startEditing = () => {
    setEditorContent(data?.content || '')
    setEditorError('')
    setIsEditing(true)
  }

  const cancelEditing = () => {
    setEditorContent(data?.content || '')
    setEditorError('')
    setIsEditing(false)
  }

  const saveEditor = async () => {
    if (!data?.path) return
    setEditorSaving(true)
    setEditorError('')
    try {
      await saveSkillContent(data.path, editorContent)
      await mutate()
      onChanged()
      setIsEditing(false)
      setTranslation('')
      setTranslationError('')
      setTranslatedByProvider('')
      setTranslatedByModel('')
      setTranslationCached(false)
      setTranslationRenderKey(current => current + 1)
    } catch (err) {
      setEditorError(err instanceof Error ? err.message : String(err))
    } finally {
      setEditorSaving(false)
    }
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
          background: 'var(--hud-solid-block)',
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
                  <span className="px-1.5 py-0.5" style={{ background: 'var(--hud-solid-block)', color: 'var(--hud-primary)' }}>
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
            <button
              type="button"
              onClick={isEditing ? cancelEditing : startEditing}
              disabled={!isCurrentDetail || !data}
              className="px-2 py-1 text-[12px] cursor-pointer disabled:opacity-40"
              style={{
                color: isEditing ? 'var(--hud-bg-deep)' : 'var(--hud-primary)',
                background: isEditing ? 'var(--hud-warning)' : 'transparent',
                border: '1px solid var(--hud-border)',
              }}
            >
              {isEditing ? t('skills.previewSkill') : t('skills.editSkill')}
            </button>
            {isEditing && (
              <button
                type="button"
                onClick={saveEditor}
                disabled={editorSaving || !editorContent.trim()}
                className="px-2 py-1 text-[12px] cursor-pointer disabled:opacity-40"
                style={{ color: 'var(--hud-bg-deep)', background: 'var(--hud-primary)', border: '1px solid var(--hud-primary)' }}
              >
                {editorSaving ? '...' : t('skills.saveSkill')}
              </button>
            )}
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
          {editorError && (
            <div className="mt-2 text-[12px]" style={{ color: 'var(--hud-error)' }}>
              {editorError}
            </div>
          )}
          {!isEditing && (
          <div className="mt-3 grid grid-cols-1 md:grid-cols-[minmax(160px,220px)_minmax(220px,1fr)_auto] gap-2 items-end">
            <label className="text-[11px] uppercase tracking-widest" style={{ color: 'var(--hud-text-dim)' }}>
              <span className="block mb-1">{t('skills.translationProvider')}</span>
              <select
                value={draftTranslationProvider}
                onChange={event => updateTranslationProvider(event.target.value)}
                data-skill-translation-provider
                className="w-full px-2 py-1.5 text-[12px] outline-none"
                style={{ background: 'var(--hud-solid-block)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)' }}
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
                style={{ background: 'var(--hud-solid-block)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)' }}
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
          )}
          {!isEditing && (
          <div className="mt-2 flex flex-wrap gap-3 text-[11px]" style={{ color: 'var(--hud-text-dim)' }}>
            <span>{t('skills.translationCacheNote')}</span>
            {translatorLabel && (
              <span style={{ color: 'var(--hud-accent)' }}>
                {t('skills.translationGeneratedBy').replace('{model}', translatorLabel)}
                {translationCached ? ` (${t('skills.cachedTranslation')})` : ''}
              </span>
            )}
          </div>
          )}
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
          {!error && isCurrentDetail && data && isEditing && (
            <textarea
              value={editorContent}
              onChange={event => setEditorContent(event.target.value)}
              data-skill-editor
              className="w-full h-full min-h-0 resize-none p-3 font-mono text-[13px] outline-none"
              style={{ background: 'var(--hud-solid-block)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)' }}
            />
          )}
          {!error && isCurrentDetail && data && !isEditing && (
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

function SkillCreateModal({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: (path?: string) => void
}) {
  const { t } = useTranslation()
  const [category, setCategory] = useState('uncategorized')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [content, setContent] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async () => {
    setBusy(true)
    setError('')
    try {
      const result = await createSkill({ category, name, description, content })
      onCreated(result?.detail?.path || result?.path)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3" style={{ background: 'rgba(0,0,0,0.72)' }} role="dialog" aria-modal="true">
      <div className="w-full max-w-3xl max-h-[90vh] min-h-0 flex flex-col overflow-hidden" style={{ background: 'var(--hud-solid-block)', border: '1px solid var(--hud-border)' }}>
        <div className="shrink-0 px-4 py-3 border-b flex items-center justify-between gap-3" style={{ borderColor: 'var(--hud-border)' }}>
          <div className="text-[15px] font-bold" style={{ color: 'var(--hud-primary)' }}>{t('skills.newSkill')}</div>
          <button type="button" onClick={onClose} className="px-2 py-1 text-[13px] cursor-pointer" style={{ color: 'var(--hud-text-dim)', border: '1px solid var(--hud-border)' }}>
            x {t('skills.close')}
          </button>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="text-[12px]" style={{ color: 'var(--hud-text-dim)' }}>
              <span className="block mb-1">{t('skills.category')}</span>
              <input value={category} onChange={event => setCategory(event.target.value)} className="w-full px-2 py-1.5 outline-none" style={{ background: 'var(--hud-solid-block)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)' }} />
            </label>
            <label className="text-[12px]" style={{ color: 'var(--hud-text-dim)' }}>
              <span className="block mb-1">{t('skills.skillName')}</span>
              <input value={name} onChange={event => setName(event.target.value)} className="w-full px-2 py-1.5 outline-none" style={{ background: 'var(--hud-solid-block)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)' }} />
            </label>
          </div>
          <label className="block text-[12px]" style={{ color: 'var(--hud-text-dim)' }}>
            <span className="block mb-1">{t('skills.description')}</span>
            <input value={description} onChange={event => setDescription(event.target.value)} className="w-full px-2 py-1.5 outline-none" style={{ background: 'var(--hud-solid-block)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)' }} />
          </label>
          <label className="block text-[12px]" style={{ color: 'var(--hud-text-dim)' }}>
            <span className="block mb-1">SKILL.md</span>
            <textarea value={content} onChange={event => setContent(event.target.value)} className="w-full h-64 resize-none p-3 font-mono text-[13px] outline-none" style={{ background: 'var(--hud-solid-block)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)' }} />
          </label>
          {error && <div className="text-[12px]" style={{ color: 'var(--hud-error)' }}>{error}</div>}
        </div>
        <div className="shrink-0 px-4 py-3 border-t flex justify-end gap-2" style={{ borderColor: 'var(--hud-border)' }}>
          <button type="button" onClick={onClose} className="px-3 py-1.5 text-[12px] cursor-pointer" style={{ color: 'var(--hud-text-dim)', border: '1px solid var(--hud-border)' }}>{t('memory.cancel')}</button>
          <button type="button" onClick={submit} disabled={busy || !name.trim()} className="px-3 py-1.5 text-[12px] cursor-pointer disabled:opacity-40" style={{ color: 'var(--hud-bg-deep)', background: 'var(--hud-primary)', border: '1px solid var(--hud-primary)' }}>
            {busy ? '...' : t('skills.saveSkill')}
          </button>
        </div>
      </div>
    </div>
  )
}

function SkillImportModal({
  onClose,
  onImported,
  mode = 'import',
}: {
  onClose: () => void
  onImported: () => void
  mode?: 'import' | 'restore'
}) {
  const { t } = useTranslation()
  const isRestore = mode === 'restore'
  const [selectedZipFile, setSelectedZipFile] = useState<File | null>(null)
  const [overwrite, setOverwrite] = useState(isRestore)
  const [busy, setBusy] = useState<'preview' | 'import' | ''>('')
  const [error, setError] = useState('')
  const [previewResult, setPreviewResult] = useState<SkillImportPreview | null>(null)
  const [result, setResult] = useState<SkillImportResult | null>(null)

  const resetPreview = () => {
    setPreviewResult(null)
    setResult(null)
    setError('')
  }

  const previewImport = async () => {
    if (!selectedZipFile) return
    setBusy('preview')
    setError('')
    setResult(null)
    try {
      const payload = await importSkillsZip(selectedZipFile, overwrite, true)
      setPreviewResult(payload)
    } catch (err) {
      setPreviewResult(null)
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy('')
    }
  }

  const submit = async () => {
    if (!selectedZipFile || !previewResult) return
    setBusy('import')
    setError('')
    try {
      const payload = await importSkillsZip(selectedZipFile, overwrite, false)
      setResult(payload)
      setPreviewResult(null)
      onImported()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy('')
    }
  }

  const importStatusLabel = (status: SkillImportItem['status']) => {
    if (status === 'add') return t('skills.importWillAdd')
    if (status === 'overwrite') return t('skills.importWillOverwrite')
    if (status === 'skip') return t('skills.importWillSkip')
    if (status === 'overwritten') return t('skills.importOverwritten')
    if (status === 'skipped') return t('skills.importSkipped')
    return t('skills.importInstalled')
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3" style={{ background: 'rgba(0,0,0,0.72)' }} role="dialog" aria-modal="true">
      <div className="w-full max-w-2xl max-h-[88vh] min-h-0 flex flex-col overflow-hidden" style={{ background: 'var(--hud-solid-block)', border: '1px solid var(--hud-border)' }}>
        <div className="shrink-0 px-4 py-3 border-b flex items-center justify-between gap-3" style={{ borderColor: 'var(--hud-border)' }}>
          <div className="text-[15px] font-bold" style={{ color: 'var(--hud-primary)' }}>{isRestore ? t('skills.restoreSkills') : t('skills.importZip')}</div>
          <button type="button" onClick={onClose} className="px-2 py-1 text-[13px] cursor-pointer" style={{ color: 'var(--hud-text-dim)', border: '1px solid var(--hud-border)' }}>
            x {t('skills.close')}
          </button>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
          <input
            type="file"
            accept=".zip,application/zip"
            disabled={Boolean(busy)}
            onChange={event => {
              setSelectedZipFile(event.target.files?.[0] || null)
              resetPreview()
            }}
            className="w-full text-[13px]"
            style={{ color: 'var(--hud-text)' }}
          />
          <label className="flex items-center gap-2 text-[13px]" style={{ color: 'var(--hud-text-dim)' }}>
            <input
              type="checkbox"
              checked={overwrite}
              disabled={Boolean(busy)}
              onChange={event => {
                setOverwrite(event.target.checked)
                resetPreview()
              }}
            />
            {t('skills.overwriteExisting')}
          </label>
          {isRestore && (
            <div className="text-[12px]" style={{ color: 'var(--hud-warning)' }}>
              {t('skills.restoreWarning')}
            </div>
          )}
          {error && <div className="text-[12px]" style={{ color: 'var(--hud-error)' }}>{error}</div>}
          {previewResult && (
            <div className="space-y-2">
              <div className="grid grid-cols-3 gap-2 text-[12px]">
                <div className="px-2 py-1.5 border" style={{ borderColor: 'var(--hud-border)', color: 'var(--hud-primary)' }}>
                  {t('skills.importWillAdd')}: {previewResult.add_count}
                </div>
                <div className="px-2 py-1.5 border" style={{ borderColor: 'var(--hud-border)', color: 'var(--hud-warning)' }}>
                  {t('skills.importWillOverwrite')}: {previewResult.overwrite_count}
                </div>
                <div className="px-2 py-1.5 border" style={{ borderColor: 'var(--hud-border)', color: 'var(--hud-text-dim)' }}>
                  {t('skills.importWillSkip')}: {previewResult.skip_count}
                </div>
              </div>
              <div className="space-y-1">
                {previewResult.items.map(item => (
                  <div key={`${item.category}/${item.name}`} className="text-[12px] px-2 py-1" style={{ background: 'var(--hud-solid-block)', color: 'var(--hud-text-dim)' }}>
                    <span style={{ color: item.status === 'add' ? 'var(--hud-primary)' : item.status === 'overwrite' ? 'var(--hud-warning)' : 'var(--hud-text-dim)' }}>
                      {importStatusLabel(item.status)}
                    </span>
                    {' '} {item.category}/{item.name}
                  </div>
                ))}
              </div>
            </div>
          )}
          {result?.items && (
            <div className="space-y-1">
              {result.items.map(item => (
                <div key={`${item.category}/${item.name}`} className="text-[12px] px-2 py-1" style={{ background: 'var(--hud-solid-block)', color: 'var(--hud-text-dim)' }}>
                  <span style={{ color: item.status === 'installed' ? 'var(--hud-primary)' : item.status === 'overwritten' ? 'var(--hud-warning)' : 'var(--hud-text-dim)' }}>
                    {importStatusLabel(item.status)}
                  </span>
                  {' '} {item.category}/{item.name}
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="shrink-0 px-4 py-3 border-t flex justify-end gap-2" style={{ borderColor: 'var(--hud-border)' }}>
          <button type="button" onClick={onClose} className="px-3 py-1.5 text-[12px] cursor-pointer" style={{ color: 'var(--hud-text-dim)', border: '1px solid var(--hud-border)' }}>{t('memory.cancel')}</button>
          <button type="button" onClick={previewImport} disabled={Boolean(busy) || !selectedZipFile} className="px-3 py-1.5 text-[12px] cursor-pointer disabled:opacity-40" style={{ color: 'var(--hud-primary)', border: '1px solid var(--hud-primary)' }}>
            {busy === 'preview' ? '...' : isRestore ? t('skills.previewRestore') : t('skills.previewImport')}
          </button>
          <button type="button" onClick={submit} disabled={Boolean(busy) || !selectedZipFile || !previewResult} className="px-3 py-1.5 text-[12px] cursor-pointer disabled:opacity-40" style={{ color: 'var(--hud-bg-deep)', background: 'var(--hud-primary)', border: '1px solid var(--hud-primary)' }}>
            {busy === 'import' ? '...' : isRestore ? t('skills.confirmRestore') : t('skills.confirmImport')}
          </button>
        </div>
      </div>
    </div>
  )
}

function SkillMarketModal({
  onClose,
  onInstalled,
}: {
  onClose: () => void
  onInstalled: () => void
}) {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const [source, setSource] = useState('official')
  const [category, setCategory] = useState('')
  const [force, setForce] = useState(false)
  const [items, setItems] = useState<SkillMarketItem[]>([])
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [activeInstall, setActiveInstall] = useState('')
  const [installStates, setInstallStates] = useState<Record<string, SkillMarketInstallState>>({})

  const submitSearch = async () => {
    setSearching(true)
    setSearchError('')
    setInstallStates({})
    try {
      const result = await searchSkillMarket(query, source)
      setItems(result?.items || [])
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : String(err))
    } finally {
      setSearching(false)
    }
  }

  const installItem = async (item: SkillMarketItem) => {
    if (item.installed && !force) return
    setActiveInstall(item.identifier)
    setInstallStates(current => ({
      ...current,
      [item.identifier]: { status: 'installing' },
    }))
    try {
      await installMarketSkill(item.identifier, category, force)
      setItems(current => current.map(candidate => (
        candidate.identifier === item.identifier
          ? {
              ...candidate,
              installed: true,
              installed_category: category || candidate.installed_category || candidate.category || '',
            }
          : candidate
      )))
      setInstallStates(current => ({
        ...current,
        [item.identifier]: { status: 'success' },
      }))
      onInstalled()
    } catch (err) {
      setInstallStates(current => ({
        ...current,
        [item.identifier]: {
          status: 'error',
          message: err instanceof Error ? err.message : String(err),
        },
      }))
    } finally {
      setActiveInstall('')
    }
  }

  const installActionLabel = (
    item: SkillMarketItem,
    state: SkillMarketInstallState | undefined,
  ) => {
    if (state?.status === 'installing') return t('skills.installingSkill')
    if (item.installed && !force) return t('skills.marketInstalled')
    if (state?.status === 'error') return t('skills.retryInstall')
    if (item.installed) return t('skills.reinstallSkill')
    return t('skills.installSkill')
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3" style={{ background: 'rgba(0,0,0,0.72)' }} role="dialog" aria-modal="true">
      <div className="w-full max-w-4xl h-[88vh] min-h-0 flex flex-col overflow-hidden" style={{ background: 'var(--hud-solid-block)', border: '1px solid var(--hud-border)' }}>
        <div className="shrink-0 px-4 py-3 border-b flex items-center justify-between gap-3" style={{ borderColor: 'var(--hud-border)' }}>
          <div className="text-[15px] font-bold" style={{ color: 'var(--hud-primary)' }}>{t('skills.skillMarket')}</div>
          <button type="button" onClick={onClose} className="px-2 py-1 text-[13px] cursor-pointer" style={{ color: 'var(--hud-text-dim)', border: '1px solid var(--hud-border)' }}>
            x {t('skills.close')}
          </button>
        </div>
        <div className="shrink-0 p-4 border-b" style={{ borderColor: 'var(--hud-border)' }}>
          <div className="grid grid-cols-1 md:grid-cols-[1fr_140px_160px_auto] gap-2">
            <input value={query} onChange={event => setQuery(event.target.value)} placeholder={t('skills.searchMarket')} className="px-2 py-1.5 outline-none text-[13px]" style={{ background: 'var(--hud-solid-block)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)' }} />
            <select value={source} onChange={event => setSource(event.target.value)} className="px-2 py-1.5 outline-none text-[13px]" style={{ background: 'var(--hud-solid-block)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)' }}>
              {['official', 'all', 'skills-sh', 'github', 'clawhub', 'lobehub', 'browse-sh'].map(option => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
            <input value={category} onChange={event => setCategory(event.target.value)} placeholder={t('skills.category')} className="px-2 py-1.5 outline-none text-[13px]" style={{ background: 'var(--hud-solid-block)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)' }} />
            <button type="button" onClick={submitSearch} disabled={searching || Boolean(activeInstall)} className="px-3 py-1.5 text-[12px] cursor-pointer disabled:opacity-40" style={{ color: 'var(--hud-bg-deep)', background: 'var(--hud-primary)', border: '1px solid var(--hud-primary)' }}>
              {searching ? '...' : t('skills.search')}
            </button>
          </div>
          <label className="mt-2 flex items-center gap-2 text-[12px]" style={{ color: 'var(--hud-text-dim)' }}>
            <input type="checkbox" checked={force} onChange={event => setForce(event.target.checked)} />
            {t('skills.forceInstall')}
          </label>
          {searchError && <div className="mt-2 text-[12px]" style={{ color: 'var(--hud-error)' }}>{searchError}</div>}
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-2">
          {items.map(item => {
            const installState = installStates[item.identifier]
            const installing = installState?.status === 'installing'
            const installDisabled = searching || Boolean(activeInstall) || Boolean(item.installed && !force)
            return (
              <div key={item.identifier} className="p-3 border" style={{ borderColor: 'var(--hud-border)', background: 'var(--hud-solid-block)' }}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="text-[14px] font-bold break-words" style={{ color: 'var(--hud-primary)' }}>{item.name}</div>
                    <div className="text-[12px] font-mono break-all" style={{ color: 'var(--hud-text-dim)' }}>{item.identifier}</div>
                    {item.installed && (
                      <div className="mt-1 text-[11px]" style={{ color: 'var(--hud-primary)' }}>
                        {t('skills.marketInstalled')}
                        {item.installed_category ? ` · ${item.installed_category}` : ''}
                      </div>
                    )}
                    {item.description && <div className="mt-1 text-[13px] break-words" style={{ color: 'var(--hud-text-dim)' }}>{item.description}</div>}
                    {installState?.status === 'success' && (
                      <div className="mt-2 text-[12px]" style={{ color: 'var(--hud-primary)' }}>{t('skills.installSucceeded')}</div>
                    )}
                    {installState?.status === 'error' && (
                      <div className="mt-2 text-[12px] break-words" style={{ color: 'var(--hud-error)' }}>{installState.message}</div>
                    )}
                  </div>
                  <button type="button" onClick={() => installItem(item)} disabled={installDisabled} className="shrink-0 px-3 py-1.5 text-[12px] cursor-pointer disabled:opacity-40" style={{ color: 'var(--hud-primary)', border: '1px solid var(--hud-primary)' }}>
                    {installing ? t('skills.installingSkill') : installActionLabel(item, installState)}
                  </button>
                </div>
              </div>
            )
          })}
          {items.length === 0 && (
            <div className="text-[13px]" style={{ color: 'var(--hud-text-dim)' }}>{t('skills.marketEmpty')}</div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function SkillsPanel() {
  const { t } = useTranslation()
  const { data, isLoading, error, mutate } = useApi<SkillsPayload>('/skills', 60000)
  const [selectedCat, setSelectedCat] = useState<string | null>(null)
  const [selectedSkillPath, setSelectedSkillPath] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [restoreOpen, setRestoreOpen] = useState(false)
  const [marketOpen, setMarketOpen] = useState(false)
  const [busySkillPath, setBusySkillPath] = useState('')
  const [backupBusy, setBackupBusy] = useState(false)
  const [batchBusy, setBatchBusy] = useState(false)
  const [batchDeleteConfirming, setBatchDeleteConfirming] = useState(false)
  const [confirmDeletePath, setConfirmDeletePath] = useState('')
  const [selectedSkillPaths, setSelectedSkillPaths] = useState<string[]>([])
  const [operationError, setOperationError] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'enabled' | 'disabled'>('all')
  const [typeFilter, setTypeFilter] = useState<'all' | 'custom' | 'builtin'>('all')

  const refreshSkills = useCallback(async () => {
    await mutate()
  }, [mutate])

  const handleBackup = async () => {
    setBackupBusy(true)
    setOperationError('')
    try {
      await downloadSkillsBackup()
    } catch (err) {
      setOperationError(err instanceof Error ? err.message : String(err))
    } finally {
      setBackupBusy(false)
    }
  }

  const handleToggleSkill = async (skill: SkillInfo) => {
    setBusySkillPath(skill.path)
    setOperationError('')
    setConfirmDeletePath('')
    setBatchDeleteConfirming(false)
    try {
      await toggleSkillEnabled(skill.name, skill.enabled === false)
      await refreshSkills()
    } catch (err) {
      setOperationError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusySkillPath('')
    }
  }

  const handleDeleteSkill = async (skill: SkillInfo) => {
    if (confirmDeletePath !== skill.path) {
      setConfirmDeletePath(skill.path)
      setBatchDeleteConfirming(false)
      return
    }
    setBusySkillPath(skill.path)
    setOperationError('')
    try {
      await deleteSkill(skill.path)
      if (selectedSkillPath === skill.path) setSelectedSkillPath(null)
      setSelectedSkillPaths(current => current.filter(path => path !== skill.path))
      setConfirmDeletePath('')
      await refreshSkills()
    } catch (err) {
      setOperationError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusySkillPath('')
    }
  }

  const toggleSelectSkill = (skill: SkillInfo, selected: boolean) => {
    setBatchDeleteConfirming(false)
    setSelectedSkillPaths(current => {
      if (selected) {
        return current.includes(skill.path) ? current : [...current, skill.path]
      }
      return current.filter(path => path !== skill.path)
    })
  }

  const clearBatchSelection = () => {
    setSelectedSkillPaths([])
    setBatchDeleteConfirming(false)
  }

  // Only show loading on initial load
  if (isLoading && !data) {
    return <Panel title={t('skills.title')} className="col-span-full h-full min-h-0" noPadding><div className="p-3 glow text-[13px] animate-pulse">{t('skills.scanning')}</div></Panel>
  }

  if (error && !data) {
    return (
      <Panel title={t('skills.title')} className="col-span-full h-full min-h-0" noPadding>
        <div className="p-3 text-[13px]" style={{ color: 'var(--hud-error)' }}>
          {t('skills.detailUnavailable')}
        </div>
      </Panel>
    )
  }

  const catCounts: Record<string, number> = data?.category_counts || {}
  const byCategory: Record<string, SkillInfo[]> = data?.by_category || {}
  const recentlyMod = data?.recently_modified || []
  const allSkills = data?.skills || Object.values(byCategory).flat()

  // Sort categories by count descending
  const sorted = Object.entries(catCounts).sort((a: any, b: any) => b[1] - a[1])
  const maxCount = sorted.length > 0 ? sorted[0][1] : 1

  // Skills in selected category
  const catSkills = selectedCat ? byCategory[selectedCat] || [] : []
  const normalizedSearch = searchQuery.trim().toLowerCase()
  const filteredSkills = allSkills.filter(skill => {
    if (selectedCat && skill.category !== selectedCat) return false
    if (statusFilter === 'enabled' && skill.enabled === false) return false
    if (statusFilter === 'disabled' && skill.enabled !== false) return false
    if (typeFilter === 'custom' && !skill.is_custom) return false
    if (typeFilter === 'builtin' && skill.is_custom) return false
    if (!normalizedSearch) return true
    const categoryDisplay = getSkillCategoryDisplay(skill.category || '', t)
    const searchable = [
      skill.name,
      skill.description,
      skill.category,
      categoryDisplay.label,
      categoryDisplay.description,
    ].join(' ').toLowerCase()
    return searchable.includes(normalizedSearch)
  })
  const hasListFilters = Boolean(normalizedSearch)
    || statusFilter !== 'all'
    || typeFilter !== 'all'
  const visibleSkills = selectedCat || hasListFilters ? filteredSkills : recentlyMod
  const selectedSkills = visibleSkills.filter(skill => selectedSkillPaths.includes(skill.path))
  const selectedCategoryDisplay = selectedCat ? getSkillCategoryDisplay(selectedCat, t) : null
  const selectedCountLabel = t('skills.selectedCount').replace('{count}', String(selectedSkills.length))

  const selectAllVisible = () => {
    setSelectedSkillPaths(visibleSkills.map(skill => skill.path))
    setBatchDeleteConfirming(false)
  }

  const allVisibleSelected = visibleSkills.length > 0
    && visibleSkills.every(skill => selectedSkillPaths.includes(skill.path))

  const toggleSelectAllVisible = () => {
    if (allVisibleSelected) {
      clearBatchSelection()
      return
    }
    selectAllVisible()
  }

  const handleBatchSetEnabled = async (enabled: boolean) => {
    if (!selectedSkills.length) return
    setBatchBusy(true)
    setOperationError('')
    setConfirmDeletePath('')
    setBatchDeleteConfirming(false)
    try {
      for (const skill of selectedSkills) {
        await toggleSkillEnabled(skill.name, enabled)
      }
      clearBatchSelection()
      await refreshSkills()
    } catch (err) {
      setOperationError(err instanceof Error ? err.message : String(err))
    } finally {
      setBatchBusy(false)
    }
  }

  const handleBatchDelete = async () => {
    if (!selectedSkills.length) return
    if (!batchDeleteConfirming) {
      setBatchDeleteConfirming(true)
      setConfirmDeletePath('')
      return
    }
    setBatchBusy(true)
    setOperationError('')
    try {
      const deletingPaths = selectedSkills.map(skill => skill.path)
      for (const skill of selectedSkills) {
        await deleteSkill(skill.path)
      }
      if (selectedSkillPath && deletingPaths.includes(selectedSkillPath)) {
        setSelectedSkillPath(null)
      }
      clearBatchSelection()
      await refreshSkills()
    } catch (err) {
      setOperationError(err instanceof Error ? err.message : String(err))
    } finally {
      setBatchBusy(false)
    }
  }

  return (
    <>
      {selectedSkillPath && (
        <SkillDetailModal
          path={selectedSkillPath}
          onClose={() => setSelectedSkillPath(null)}
          onChanged={refreshSkills}
        />
      )}
      {createOpen && (
        <SkillCreateModal
          onClose={() => setCreateOpen(false)}
          onCreated={(path) => {
            if (path) setSelectedSkillPath(path)
            refreshSkills()
          }}
        />
      )}
      {importOpen && (
        <SkillImportModal
          onClose={() => setImportOpen(false)}
          onImported={refreshSkills}
        />
      )}
      {restoreOpen && (
        <SkillImportModal
          mode="restore"
          onClose={() => setRestoreOpen(false)}
          onImported={refreshSkills}
        />
      )}
      {marketOpen && (
        <SkillMarketModal
          onClose={() => setMarketOpen(false)}
          onInstalled={refreshSkills}
        />
      )}

      <div className="skills-panel-root col-span-full h-full min-h-0 grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-2">
        <Panel title={t('dashboard.skillLibrary')} className="h-full min-h-0" noPadding>
          <div className="shrink-0 p-3 border-b" style={{ borderColor: 'var(--hud-border)' }}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[13px] px-2 py-0.5" style={{ background: 'var(--hud-solid-block)', color: 'var(--hud-primary)' }}>
                {data?.total || 0} {t('dashboard.total')}
              </span>
              <span className="text-[13px] px-2 py-0.5" style={{ background: 'var(--hud-solid-block)', color: 'var(--hud-accent)' }}>
                {data?.custom_count || 0} {t('dashboard.custom')}
              </span>
              <span className="text-[13px]" style={{ color: 'var(--hud-text-dim)' }}>
                {sorted.length} {t('dashboard.categories')}
              </span>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" onClick={() => setCreateOpen(true)} className="px-2 py-1 text-[12px] cursor-pointer" style={{ color: 'var(--hud-bg-deep)', background: 'var(--hud-primary)', border: '1px solid var(--hud-primary)' }}>
                + {t('skills.newSkill')}
              </button>
              <button type="button" onClick={() => setImportOpen(true)} className="px-2 py-1 text-[12px] cursor-pointer" style={{ color: 'var(--hud-primary)', border: '1px solid var(--hud-border)' }}>
                {t('skills.importZip')}
              </button>
              <button type="button" onClick={() => setRestoreOpen(true)} className="px-2 py-1 text-[12px] cursor-pointer" style={{ color: 'var(--hud-warning)', border: '1px solid var(--hud-border)' }}>
                {t('skills.restoreSkills')}
              </button>
              <button type="button" onClick={handleBackup} disabled={backupBusy} className="px-2 py-1 text-[12px] cursor-pointer disabled:opacity-40" style={{ color: 'var(--hud-accent)', border: '1px solid var(--hud-border)' }}>
                {backupBusy ? '...' : t('skills.backup')}
              </button>
              <button type="button" onClick={() => setMarketOpen(true)} className="px-2 py-1 text-[12px] cursor-pointer" style={{ color: 'var(--hud-accent)', border: '1px solid var(--hud-border)' }}>
                {t('skills.skillMarket')}
              </button>
              <button type="button" onClick={refreshSkills} className="px-2 py-1 text-[12px] cursor-pointer" style={{ color: 'var(--hud-text-dim)', border: '1px solid var(--hud-border)' }}>
                {t('skills.refresh')}
              </button>
            </div>
            {operationError && <div className="mt-2 text-[12px]" style={{ color: 'var(--hud-error)' }}>{operationError}</div>}
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-1 text-[13px]">
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
                    clearBatchSelection()
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
                  <div className="flex-1 h-[6px]" style={{ background: 'var(--hud-solid-block)' }}>
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

        <Panel title={selectedCat ? selectedCategoryDisplay?.label || selectedCat : t('dashboard.recentlyModified')} className="h-full min-h-0" noPadding>
          <div className="shrink-0 p-3 border-b" style={{ borderColor: 'var(--hud-border)' }}>
            {selectedCategoryDisplay?.description ? (
              <div className="text-[13px]" style={{ color: 'var(--hud-text-dim)' }}>{selectedCategoryDisplay.description}</div>
            ) : (
              <div className="text-[13px]" style={{ color: 'var(--hud-text-dim)' }}>{t('skills.selectPrompt')}</div>
            )}
            <div className="mt-3 grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_auto_auto] gap-2">
              <input
                value={searchQuery}
                onChange={event => setSearchQuery(event.target.value)}
                placeholder={t('skills.searchSkillsPlaceholder')}
                aria-label={t('skills.searchSkills')}
                className="min-w-0 px-2 py-1.5 text-[12px] outline-none"
                style={{ background: 'var(--hud-solid-block)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)' }}
              />
              <label className="flex items-center gap-1 text-[12px]" style={{ color: 'var(--hud-text-dim)' }}>
                <span>{t('skills.statusFilter')}</span>
                <select data-skill-filter-status value={statusFilter} onChange={event => setStatusFilter(event.target.value as typeof statusFilter)} className="px-1.5 py-1 outline-none" style={{ background: 'var(--hud-solid-block)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)', colorScheme: 'dark' }}>
                  <option value="all" style={skillFilterOptionStyle}>{t('skills.allStatuses')}</option>
                  <option value="enabled" style={skillFilterOptionStyle}>{t('skills.enabled')}</option>
                  <option value="disabled" style={skillFilterOptionStyle}>{t('skills.disabled')}</option>
                </select>
              </label>
              <label className="flex items-center gap-1 text-[12px]" style={{ color: 'var(--hud-text-dim)' }}>
                <span>{t('skills.typeFilter')}</span>
                <select data-skill-filter-type value={typeFilter} onChange={event => setTypeFilter(event.target.value as typeof typeFilter)} className="px-1.5 py-1 outline-none" style={{ background: 'var(--hud-solid-block)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)', colorScheme: 'dark' }}>
                  <option value="all" style={skillFilterOptionStyle}>{t('skills.allTypes')}</option>
                  <option value="custom" style={skillFilterOptionStyle}>{t('skills.customType')}</option>
                  <option value="builtin" style={skillFilterOptionStyle}>{t('skills.builtinType')}</option>
                </select>
              </label>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="text-[12px]" style={{ color: 'var(--hud-text-dim)' }}>{selectedCountLabel}</span>
              <button type="button" onClick={toggleSelectAllVisible} disabled={!visibleSkills.length || batchBusy} className="px-2 py-1 text-[12px] cursor-pointer disabled:opacity-40" style={{ color: 'var(--hud-primary)', border: '1px solid var(--hud-border)' }}>
                {allVisibleSelected ? t('skills.deselectAllVisible') : t('skills.selectAllVisible')}
              </button>
              <button type="button" onClick={() => handleBatchSetEnabled(true)} disabled={!selectedSkills.length || batchBusy} className="px-2 py-1 text-[12px] cursor-pointer disabled:opacity-40" style={{ color: 'var(--hud-primary)', border: '1px solid var(--hud-border)' }}>
                {t('skills.batchEnable')}
              </button>
              <button type="button" onClick={() => handleBatchSetEnabled(false)} disabled={!selectedSkills.length || batchBusy} className="px-2 py-1 text-[12px] cursor-pointer disabled:opacity-40" style={{ color: 'var(--hud-warning)', border: '1px solid var(--hud-border)' }}>
                {t('skills.batchDisable')}
              </button>
              <button type="button" onClick={handleBatchDelete} disabled={!selectedSkills.length || batchBusy} className="px-2 py-1 text-[12px] cursor-pointer disabled:opacity-40" style={{ color: 'var(--hud-error)', border: '1px solid var(--hud-border)' }}>
                {batchDeleteConfirming ? t('skills.batchConfirmDelete') : t('skills.batchDelete')}
              </button>
            </div>
          </div>
          <div className="skill-list-scroll flex-1 min-h-0 overflow-y-auto p-3 space-y-2">
            {visibleSkills.map((skill: SkillInfo) => (
              <div key={skill.path || skill.name}>
                <SkillItem
                  skill={skill}
                  variant={selectedCat ? 'category' : 'recent'}
                  selected={selectedSkillPath === skill.path}
                  onSelect={() => setSelectedSkillPath(skill.path)}
                  onToggle={handleToggleSkill}
                  onDelete={handleDeleteSkill}
                  selectedForBatch={selectedSkillPaths.includes(skill.path)}
                  onBatchSelect={toggleSelectSkill}
                  deleteConfirming={confirmDeletePath === skill.path}
                  busy={busySkillPath === skill.path || batchBusy}
                />
              </div>
            ))}
            {visibleSkills.length === 0 && hasListFilters && (
              <div className="text-[13px]" style={{ color: 'var(--hud-text-dim)' }}>{t('skills.noMatches')}</div>
            )}
            {selectedCat && catSkills.length === 0 && (
              <div className="text-[13px]" style={{ color: 'var(--hud-text-dim)' }}>{t('dashboard.noSkillsInCategory')}</div>
            )}
            {!selectedCat && recentlyMod.length === 0 && (
              <div className="text-[13px]" style={{ color: 'var(--hud-text-dim)' }}>{t('dashboard.noRecentModifications')}</div>
            )}
          </div>
        </Panel>
      </div>
    </>
  )
}
