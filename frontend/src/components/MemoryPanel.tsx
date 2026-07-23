import { useEffect, useState, type ReactNode } from 'react'
import { useApi } from '../hooks/useApi'
import Panel, { CapacityBar } from './Panel'
import { useTranslation, type TranslationKey } from '../i18n'

interface MemoryStatusCommand {
  ok: boolean
  exit_code: number | null
  output: string
  error: string
  command: string
}

interface MemoryProviderRuntimeCheck {
  kind: string
  name: string
  ok: boolean
  url?: string
  command?: string
  executable?: string
  status_code?: number | null
  error?: string
}

interface MemoryProviderHealth {
  provider: string
  active: boolean
  checked_at: string
  config_files: Array<{
    path: string
    kind: 'file' | 'directory'
    exists: boolean
  }>
  required_config: {
    ok: boolean
    missing_fields: string[]
    missing_any: string[][]
  }
  dependencies: {
    ok: boolean
    checks: Array<{
      kind: string
      name: string
      ok: boolean
    }>
  }
  runtime: {
    ok: boolean | null
    mode: string
    reason: string
    checks: MemoryProviderRuntimeCheck[]
  }
  status_command: MemoryStatusCommand | null
}

interface MemoryProviderDependency {
  kind: string
  name: string
}

interface MemoryProviderConfigMode {
  id: string
  label: string
  storage: string
  description: string
  fields: string[]
  required_fields: string[]
  required_any: string[][]
  optional_fields: string[]
  dependencies: MemoryProviderDependency[]
  setup_command?: string
  status_command?: string
  next_steps?: string
}

interface MemoryProviderCapabilities {
  external_read: boolean
  external_read_mode: string
  direct_hud_config: boolean
  requires_network: boolean
  local_storage: boolean
  supports_tools: boolean
  supports_auto_recall: boolean
  supports_session_ingest: boolean
  supports_manual_write: boolean
  hooks: string[]
}

interface MemoryProviderSchemaSource {
  kind: 'official_schema' | 'hud_metadata'
  method: string
  fallback: boolean
  source: string
}

interface MemoryProviderExternalViewSummary {
  available: boolean
  readonly: boolean
  endpoint: string
  view_type: string
  reason: string
}

interface MemoryProviderExternalFact {
  id: string
  content: string
  category: string
  tags: string[]
  trust_score: number
  retrieval_count: number
  helpful_count: number
  created_at: string
  updated_at: string
}

interface MemoryProviderExternalView {
  provider: string
  available: boolean
  readonly: boolean
  reason?: string
  error?: string
  db_path?: string
  summary: {
    total: number
    categories: Record<string, number>
  }
  items: MemoryProviderExternalFact[]
}

interface MemoryProviderInfo {
  id: string
  group: 'official' | 'community'
  label: string
  storage: string
  setup_command: string
  config_command: string
  active: boolean
  configured: boolean
  readiness: 'missing_config' | 'configured' | 'selected' | 'ready'
  missing_fields: string[]
  missing_any: string[][]
  checks: Array<{
    kind: string
    name: string
    ok: boolean
  }>
  config_fields: Array<{
    name: string
    label: string
    storage: string
    path: string
    secret: boolean
    control?: 'text' | 'boolean'
    help: string
    requirement: 'required' | 'required_any' | 'optional'
    required_group: string[]
    mode_ids: string[]
  }>
  config_modes: MemoryProviderConfigMode[]
  default_mode: string
  current_mode: string
  config_values: Record<string, {
    configured: boolean
    secret: boolean
    source: string
    value: string
  }>
  capabilities: MemoryProviderCapabilities
  schema_source: MemoryProviderSchemaSource
  external_view: MemoryProviderExternalViewSummary
  health?: MemoryProviderHealth
  notes?: string[]
}

interface MemoryProvidersState {
  builtin: {
    enabled: boolean
    sources: string[]
  }
  active_provider: string
  providers: Record<string, MemoryProviderInfo>
  setup_command: string
  status_command: string
  off_command: string
}

interface MemoryProviderCheckResult {
  provider: string
  active_provider: string
  status_command: MemoryStatusCommand
  health?: MemoryProviderHealth | null
}

interface MemoryFileState {
  target: 'memory' | 'user'
  label: string
  path: string
  exists: boolean
  editable: boolean
  content: string
  total_chars: number
  max_chars: number
  capacity_pct: number
  entry_count: number
  entries: any[]
  count_by_category: Record<string, number>
  modified_at: string
}

interface MemorySettingsState {
  memory_enabled: boolean
  user_profile_enabled: boolean
  memory_char_limit: number
  user_char_limit: number
  write_approval: boolean
  memory_notifications: 'off' | 'on' | 'verbose'
  pending_count: number
}

interface MemoryFilesState {
  files: {
    memory: MemoryFileState
    user: MemoryFileState
  }
  settings: MemorySettingsState
}

interface MemoryHistoryCandidate {
  session_id: string
  message_id: string
  title: string
  source: string
  started_at: number
  message_count: number
  role: string
  timestamp: number
  snippet: string
  content: string
  suggested_target: 'memory' | 'user'
}

interface MemoryHistoryState {
  query: string
  count: number
  status: string
  candidates: MemoryHistoryCandidate[]
}

interface MemoryHistoryCommitResult {
  ok: boolean
  staged: boolean
  target: 'memory' | 'user'
  pending_id?: string
  entry_count?: number
}

interface MemoryExportState {
  generated_at: string
  hermes_home: string
  files: {
    memory: MemoryFileState
    user: MemoryFileState
  }
  provider: {
    active_provider: string
    providers: Record<string, {
      label: string
      storage: string
      active: boolean
      configured: boolean
      current_mode: string
      fields: Record<string, {
        label: string
        storage: string
        source: string
        configured: boolean
        redacted: boolean
        value: string
      }>
    }>
    redactions: string[]
  }
}

interface PendingMemoryWrite {
  id: string
  subsystem: string
  action: string
  summary: string
  origin: string
  created_at: number
  payload: {
    action?: string
    target?: string
    content?: string
    old_text?: string
    operations?: Array<Record<string, string>>
  }
}

interface MemoryPendingState {
  pending: PendingMemoryWrite[]
  count: number
  write_approval: boolean
}

async function memoryApi(method: string, body: Record<string, string>) {
  const res = await fetch('/api/memory', {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

async function saveMemoryFile(target: string, content: string): Promise<MemoryFileState> {
  const res = await fetch(`/api/memory/files/${target}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

async function saveMemorySettings(settings: Partial<MemorySettingsState>): Promise<MemorySettingsState> {
  const res = await fetch('/api/memory/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

async function setMemoryProvider(provider: string): Promise<MemoryProvidersState> {
  const res = await fetch('/api/memory/providers', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

async function saveMemoryProviderConfig(
  provider: string,
  fields: Record<string, string>,
  selectedMode = ''
): Promise<MemoryProvidersState> {
  const res = await fetch(`/api/memory/providers/${provider}/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode: selectedMode, fields }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

async function checkMemoryProviderStatus(provider: string, selectedMode = ''): Promise<MemoryProviderCheckResult> {
  const res = await fetch('/api/memory/providers/check', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider, mode: selectedMode }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

async function fetchProviderExternalView(provider: string): Promise<MemoryProviderExternalView> {
  const res = await fetch(`/api/memory/providers/${provider}/external`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

async function approvePendingMemory(pendingId: string) {
  const res = await fetch(`/api/memory/pending/${pendingId}/approve`, { method: 'POST' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

async function rejectPendingMemory(pendingId: string) {
  const res = await fetch(`/api/memory/pending/${pendingId}/reject`, { method: 'POST' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

async function fetchMemoryHistory(query = '', limit = 12): Promise<MemoryHistoryState> {
  const params = new URLSearchParams()
  params.set('limit', String(limit))
  if (query.trim()) params.set('q', query.trim())
  const res = await fetch(`/api/memory/history?${params.toString()}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

async function commitMemoryHistoryCandidate(
  target: 'memory' | 'user',
  candidate: MemoryHistoryCandidate
): Promise<MemoryHistoryCommitResult> {
  const res = await fetch('/api/memory/history/commit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      target,
      content: candidate.content || candidate.snippet,
      source_session_id: candidate.session_id,
      source_message_id: candidate.message_id,
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

async function fetchMemoryExport(): Promise<MemoryExportState> {
  const res = await fetch('/api/memory/export')
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

async function createMemoryBackup(): Promise<{ ok: boolean; path: string; generated_at: string; export: MemoryExportState }> {
  const res = await fetch('/api/memory/export', { method: 'POST' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

function MemoryEntry({
  entry,
  target,
  onMutate,
}: {
  entry: any
  target: string
  onMutate: () => void
}) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const startEdit = () => {
    setEditText(entry.text)
    setEditing(true)
    setError('')
  }

  const cancelEdit = () => {
    setEditing(false)
    setError('')
  }

  const saveEdit = async () => {
    const trimmed = editText.trim()
    if (!trimmed || trimmed === entry.text) {
      cancelEdit()
      return
    }
    setBusy(true)
    setError('')
    try {
      await memoryApi('PUT', { target, old_text: entry.text, content: trimmed })
      setEditing(false)
      onMutate()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const deleteEntry = async () => {
    if (!confirming) {
      setConfirming(true)
      return
    }
    setBusy(true)
    setError('')
    try {
      await memoryApi('DELETE', { target, old_text: entry.text })
      onMutate()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
      setConfirming(false)
    }
  }

  return (
    <div
      className="text-[13px] py-1.5 px-2 group"
      style={{ background: 'var(--hud-solid-block)', borderLeft: '2px solid var(--hud-border)' }}
    >
      <div className="flex justify-between mb-0.5">
        <span className="uppercase tracking-wider text-[13px] font-bold" style={{ color: 'var(--hud-primary)' }}>
          {entry.category}
        </span>
        <span className="flex items-center gap-1.5">
          {!editing && (
            <span className="opacity-0 group-hover:opacity-100 flex gap-1">
              <button
                onClick={startEdit}
                className="text-[11px] cursor-pointer px-1"
                style={{ color: 'var(--hud-primary)' }}
                disabled={busy}
              >
                {t('memory.edit')}
              </button>
              <button
                onClick={deleteEntry}
                onMouseLeave={() => setConfirming(false)}
                className="text-[11px] cursor-pointer px-1"
                style={{ color: 'var(--hud-error, #f44)' }}
                disabled={busy}
              >
                {confirming ? t('memory.confirmDelete') : t('memory.delete')}
              </button>
            </span>
          )}
          <span style={{ color: 'var(--hud-text-dim)' }}>{entry.char_count}c</span>
        </span>
      </div>

      {editing ? (
        <div>
          <textarea
            value={editText}
            onChange={e => setEditText(e.target.value)}
            className="w-full text-[13px] p-1.5 outline-none resize-y"
            style={{
              background: 'var(--hud-soft-block)',
              border: '1px solid var(--hud-border)',
              color: 'var(--hud-text)',
              minHeight: '60px',
            }}
            autoFocus
          />
          <div className="flex gap-1 mt-1">
            <button
              onClick={saveEdit}
              disabled={busy}
              className="text-[11px] px-2 py-0.5 cursor-pointer"
              style={{ background: 'var(--hud-primary)', color: 'var(--hud-bg-deep)', border: 'none' }}
            >
              {busy ? '...' : t('memory.save')}
            </button>
            <button
              onClick={cancelEdit}
              disabled={busy}
              className="text-[11px] px-2 py-0.5 cursor-pointer"
              style={{ background: 'var(--hud-soft-block)', color: 'var(--hud-text-dim)', border: '1px solid var(--hud-border)' }}
            >
              {t('memory.cancel')}
            </button>
          </div>
          {error && <div className="text-[11px] mt-1" style={{ color: 'var(--hud-error, #f44)' }}>{error}</div>}
        </div>
      ) : (
        <div style={{ color: 'var(--hud-text)' }}>{entry.text}</div>
      )}
    </div>
  )
}

function AddEntryForm({ target, onMutate }: { target: string; onMutate: () => void }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async () => {
    const trimmed = text.trim()
    if (!trimmed) return
    setBusy(true)
    setError('')
    try {
      await memoryApi('POST', { target, content: trimmed })
      setText('')
      setOpen(false)
      onMutate()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="w-full text-[11px] py-1 mt-1 cursor-pointer"
        style={{ color: 'var(--hud-text-dim)', border: '1px dashed var(--hud-border)', background: 'transparent' }}
      >
        + {t('memory.addNew')}
      </button>
    )
  }

  return (
    <div className="mt-1">
      <textarea
        value={text}
        onChange={e => setText(e.target.value)}
        placeholder={t('memory.addNew')}
        className="w-full text-[13px] p-1.5 outline-none resize-y"
        style={{
          background: 'var(--hud-soft-block)',
          border: '1px solid var(--hud-border)',
          color: 'var(--hud-text)',
          minHeight: '50px',
        }}
        autoFocus
      />
      <div className="flex gap-1 mt-1">
        <button
          onClick={submit}
          disabled={busy || !text.trim()}
          className="text-[11px] px-2 py-0.5 cursor-pointer disabled:opacity-40"
          style={{ background: 'var(--hud-primary)', color: 'var(--hud-bg-deep)', border: 'none' }}
        >
          {busy ? '...' : t('memory.add')}
        </button>
        <button
          onClick={() => { setOpen(false); setText(''); setError('') }}
          className="text-[11px] px-2 py-0.5 cursor-pointer"
          style={{ background: 'var(--hud-soft-block)', color: 'var(--hud-text-dim)', border: '1px solid var(--hud-border)' }}
        >
          {t('memory.cancel')}
        </button>
      </div>
      {error && <div className="text-[11px] mt-1" style={{ color: 'var(--hud-error, #f44)' }}>{error}</div>}
    </div>
  )
}

function MemoryEntries({
  entries,
  target,
  onMutate,
  columns = 1,
}: {
  entries: any[]
  target: string
  onMutate: () => void
  columns?: 1 | 2
}) {
  const { t } = useTranslation()
  if (!entries?.length) return <div className="text-[13px]" style={{ color: 'var(--hud-text-dim)' }}>{t('memory.empty')}</div>
  const entriesClass = columns === 2 ? 'grid grid-cols-1 lg:grid-cols-2 gap-1.5' : 'space-y-1.5'

  return (
    <div className={entriesClass}>
      {entries.map((e: any) => (
        <MemoryEntry key={e.text} entry={e} target={target} onMutate={onMutate} />
      ))}
    </div>
  )
}

function formatTimestamp(value?: string | number) {
  if (!value) return ''
  const parsed = typeof value === 'number' ? new Date(value * 1000) : new Date(value)
  if (Number.isNaN(parsed.getTime())) return String(value)
  return parsed.toLocaleString()
}

function BuiltinMemoryFileCard({
  file,
  title,
  onSaved,
  children,
}: {
  file?: MemoryFileState
  title: string
  onSaved: () => void
  children?: ReactNode
}) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    if (!file || editing) return
    setDraft(file.content || '')
  }, [file?.target, file?.content, editing])

  if (!file) {
    return (
      <div className="p-2 h-full" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-solid-block)' }}>
        <div className="text-[13px]" style={{ color: 'var(--hud-text-dim)' }}>{t('memory.loading')}</div>
      </div>
    )
  }

  const save = async () => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await saveMemoryFile(file.target, draft)
      setEditing(false)
      setNotice(t('memory.fileSaved'))
      onSaved()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="p-2 h-full" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-solid-block)' }}>
      <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
        <div>
          <div className="uppercase tracking-wider text-[10px] mb-1" style={{ color: 'var(--hud-text-dim)' }}>
            {title}
          </div>
          <div className="font-mono text-[11px]" style={{ color: 'var(--hud-text-dim)' }}>
            {file.path}
          </div>
        </div>
        <button
          onClick={() => {
            setDraft(file.content || '')
            setEditing(!editing)
            setError('')
            setNotice('')
          }}
          className="px-2 py-1 text-[11px] cursor-pointer"
          style={{ background: 'var(--hud-soft-block)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)' }}
          type="button"
        >
          {editing ? t('memory.cancel') : t('memory.fullFileEditor')}
        </button>
      </div>

      {file.max_chars > 0 && (
        <CapacityBar value={file.total_chars || 0} max={file.max_chars} label={t('memory.capacity')} />
      )}
      <div className="text-[13px] my-2" style={{ color: 'var(--hud-text-dim)' }}>
        {file.entry_count || 0} {t('memory.entries')}
        {file.modified_at ? ` · ${t('memory.modified')}: ${formatTimestamp(file.modified_at)}` : ''}
      </div>

      {editing ? (
        <div>
          <textarea
            value={draft}
            onChange={event => setDraft(event.target.value)}
            className="w-full text-[12px] p-2 outline-none resize-y font-mono"
            style={{
              background: 'var(--hud-soft-block)',
              border: '1px solid var(--hud-border)',
              color: 'var(--hud-text)',
              minHeight: '220px',
            }}
          />
          <div className="flex justify-end gap-2 mt-2">
            <button
              onClick={() => { setEditing(false); setDraft(file.content || ''); setError('') }}
              disabled={busy}
              className="px-2 py-1 text-[12px] cursor-pointer disabled:opacity-40"
              style={{ background: 'var(--hud-soft-block)', color: 'var(--hud-text-dim)', border: '1px solid var(--hud-border)' }}
              type="button"
            >
              {t('memory.cancel')}
            </button>
            <button
              onClick={save}
              disabled={busy}
              className="px-2 py-1 text-[12px] cursor-pointer disabled:opacity-40"
              style={{ background: 'var(--hud-primary)', color: 'var(--hud-bg-deep)', border: 'none' }}
              type="button"
            >
              {busy ? '...' : t('memory.save')}
            </button>
          </div>
        </div>
      ) : (
        children || (
          <pre
            className="text-[12px] whitespace-pre-wrap p-2 overflow-auto"
            style={{
              background: 'var(--hud-soft-block)',
              border: '1px solid var(--hud-border)',
              color: file.content ? 'var(--hud-text)' : 'var(--hud-text-dim)',
              maxHeight: '280px',
            }}
          >
            {file.content || t('memory.emptyFile')}
          </pre>
        )
      )}
      {notice && <div className="text-[12px] mt-2" style={{ color: 'var(--hud-success)' }}>{notice}</div>}
      {error && <div className="text-[12px] mt-2" style={{ color: 'var(--hud-error, #f44)' }}>{error}</div>}
    </div>
  )
}

function MemorySettingsPanel({
  settings,
  onSaved,
}: {
  settings?: MemorySettingsState
  onSaved: () => void
}) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState<Partial<MemorySettingsState>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    if (!settings) return
    setDraft(settings)
    setError('')
    setNotice('')
  }, [settings])

  const submit = async () => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await saveMemorySettings({
        memory_enabled: !!draft.memory_enabled,
        user_profile_enabled: !!draft.user_profile_enabled,
        memory_char_limit: Number(draft.memory_char_limit || 2200),
        user_char_limit: Number(draft.user_char_limit || 1375),
        write_approval: !!draft.write_approval,
        memory_notifications: draft.memory_notifications || 'on',
      })
      setNotice(t('memory.settingsSaved'))
      onSaved()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="p-2" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-solid-block)' }}>
      <div className="uppercase tracking-wider text-[10px] mb-2" style={{ color: 'var(--hud-text-dim)' }}>
        {t('memory.settings')}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
        <label className="flex items-center gap-2 text-[13px]" style={{ color: 'var(--hud-text)' }}>
          <input
            type="checkbox"
            checked={!!draft.memory_enabled}
            onChange={event => setDraft(prev => ({ ...prev, memory_enabled: event.target.checked }))}
          />
          {t('memory.memoryEnabled')}
        </label>
        <label className="flex items-center gap-2 text-[13px]" style={{ color: 'var(--hud-text)' }}>
          <input
            type="checkbox"
            checked={!!draft.user_profile_enabled}
            onChange={event => setDraft(prev => ({ ...prev, user_profile_enabled: event.target.checked }))}
          />
          {t('memory.userProfileEnabled')}
        </label>
        <label className="block text-[12px]" style={{ color: 'var(--hud-text-dim)' }}>
          {t('memory.memoryCharLimit')}
          <input
            type="number"
            min={1}
            value={draft.memory_char_limit || 2200}
            onChange={event => setDraft(prev => ({ ...prev, memory_char_limit: Number(event.target.value) }))}
            className="w-full mt-1 px-2 py-1 outline-none"
            style={{ background: 'var(--hud-soft-block)', border: '1px solid var(--hud-border)', color: 'var(--hud-text)' }}
          />
        </label>
        <label className="block text-[12px]" style={{ color: 'var(--hud-text-dim)' }}>
          {t('memory.userCharLimit')}
          <input
            type="number"
            min={1}
            value={draft.user_char_limit || 1375}
            onChange={event => setDraft(prev => ({ ...prev, user_char_limit: Number(event.target.value) }))}
            className="w-full mt-1 px-2 py-1 outline-none"
            style={{ background: 'var(--hud-soft-block)', border: '1px solid var(--hud-border)', color: 'var(--hud-text)' }}
          />
        </label>
        <label className="flex items-center gap-2 text-[13px]" style={{ color: 'var(--hud-text)' }}>
          <input
            type="checkbox"
            checked={!!draft.write_approval}
            onChange={event => setDraft(prev => ({ ...prev, write_approval: event.target.checked }))}
          />
          {t('memory.writeApproval')}
        </label>
        <label className="block text-[12px]" style={{ color: 'var(--hud-text-dim)' }}>
          {t('memory.memoryNotifications')}
          <select
            value={draft.memory_notifications || 'on'}
            onChange={event => setDraft(prev => ({ ...prev, memory_notifications: event.target.value as MemorySettingsState['memory_notifications'] }))}
            className="w-full mt-1 px-2 py-1 outline-none"
            style={{ background: 'var(--hud-soft-block)', border: '1px solid var(--hud-border)', color: 'var(--hud-text)' }}
          >
            <option value="off">{t('memory.notificationsOff')}</option>
            <option value="on">{t('memory.notificationsOn')}</option>
            <option value="verbose">{t('memory.notificationsVerbose')}</option>
          </select>
        </label>
      </div>
      <div className="flex justify-end mt-2">
        <button
          onClick={submit}
          disabled={busy}
          className="px-3 py-1.5 text-[12px] cursor-pointer disabled:opacity-40"
          style={{ background: 'var(--hud-primary)', color: 'var(--hud-bg-deep)', border: 'none' }}
          type="button"
        >
          {busy ? '...' : t('memory.saveSettings')}
        </button>
      </div>
      {notice && <div className="text-[12px] mt-2" style={{ color: 'var(--hud-success)' }}>{notice}</div>}
      {error && <div className="text-[12px] mt-2" style={{ color: 'var(--hud-error, #f44)' }}>{error}</div>}
    </div>
  )
}

function PendingMemoryPanel({
  data,
  onMutate,
}: {
  data?: MemoryPendingState
  onMutate: () => void
}) {
  const { t } = useTranslation()
  const [busyId, setBusyId] = useState('')
  const [error, setError] = useState('')

  const run = async (pendingId: string, action: 'approve' | 'reject') => {
    setBusyId(`${action}:${pendingId}`)
    setError('')
    try {
      if (action === 'approve') await approvePendingMemory(pendingId)
      else await rejectPendingMemory(pendingId)
      onMutate()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusyId('')
    }
  }

  return (
    <div className="p-2" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-solid-block)' }}>
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="uppercase tracking-wider text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>
          {t('memory.pendingWrites')}
        </div>
        <div className="text-[12px]" style={{ color: data?.write_approval ? 'var(--hud-success)' : 'var(--hud-text-dim)' }}>
          {t('memory.writeApproval')}: {data?.write_approval ? t('memory.activeState') : t('memory.inactiveState')}
        </div>
      </div>
      {!data?.pending?.length ? (
        <div className="text-[13px]" style={{ color: 'var(--hud-text-dim)' }}>{t('memory.noPendingWrites')}</div>
      ) : (
        <div className="space-y-2">
          {data.pending.map(item => (
            <div key={item.id} className="p-2" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-soft-block)' }}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <div className="font-mono text-[12px]" style={{ color: 'var(--hud-primary)' }}>
                    {item.id} · {item.action || item.payload?.action || 'memory'}
                  </div>
                  <div className="text-[12px]" style={{ color: 'var(--hud-text-dim)' }}>
                    {item.origin}{item.created_at ? ` · ${formatTimestamp(item.created_at)}` : ''}
                  </div>
                </div>
                <div className="flex gap-1.5">
                  <button
                    onClick={() => run(item.id, 'approve')}
                    disabled={!!busyId}
                    className="px-2 py-1 text-[11px] cursor-pointer disabled:opacity-40"
                    style={{ background: 'var(--hud-primary)', color: 'var(--hud-bg-deep)', border: 'none' }}
                    type="button"
                  >
                    {busyId === `approve:${item.id}` ? '...' : t('memory.approve')}
                  </button>
                  <button
                    onClick={() => run(item.id, 'reject')}
                    disabled={!!busyId}
                    className="px-2 py-1 text-[11px] cursor-pointer disabled:opacity-40"
                    style={{ background: 'var(--hud-soft-block)', color: 'var(--hud-warning)', border: '1px solid var(--hud-border)' }}
                    type="button"
                  >
                    {busyId === `reject:${item.id}` ? '...' : t('memory.reject')}
                  </button>
                </div>
              </div>
              <div className="text-[13px] mt-2" style={{ color: 'var(--hud-text)' }}>
                {item.summary || item.payload?.content || t('memory.noStatusOutput')}
              </div>
              {!!item.payload?.old_text && (
                <div className="text-[12px] mt-1" style={{ color: 'var(--hud-text-dim)' }}>
                  {t('memory.oldText')}: {item.payload.old_text}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {error && <div className="text-[12px] mt-2" style={{ color: 'var(--hud-error, #f44)' }}>{error}</div>}
    </div>
  )
}

function MemoryHistoryPanel({ onMutate }: { onMutate: () => void }) {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const [history, setHistory] = useState<MemoryHistoryState | null>(null)
  const [busy, setBusy] = useState(false)
  const [busyId, setBusyId] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const runSearch = async (nextQuery = query) => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      setHistory(await fetchMemoryHistory(nextQuery, 12))
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    runSearch('')
  }, [])

  const saveCandidate = async (candidate: MemoryHistoryCandidate, target: 'memory' | 'user') => {
    setBusyId(`${candidate.message_id}:${target}`)
    setError('')
    setNotice('')
    try {
      const result = await commitMemoryHistoryCandidate(target, candidate)
      setNotice(result.staged ? t('memory.savedToPending') : t('memory.savedToFile'))
      onMutate()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusyId('')
    }
  }

  return (
    <div className="p-2 mt-3" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-solid-block)' }}>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
        <div>
          <div className="uppercase tracking-wider text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>
            {t('memory.historyCandidates')}
          </div>
          <div className="text-[12px]" style={{ color: 'var(--hud-text-dim)' }}>
            {t('memory.historyCandidateHint')}
          </div>
        </div>
        <div className="flex gap-1.5">
          <input
            value={query}
            onChange={event => setQuery(event.target.value)}
            onKeyDown={event => {
              if (event.key === 'Enter') runSearch()
            }}
            placeholder={t('memory.searchHistory')}
            className="text-[12px] px-2 py-1 outline-none"
            style={{ background: 'var(--hud-soft-block)', border: '1px solid var(--hud-border)', color: 'var(--hud-text)' }}
          />
          <button
            onClick={() => runSearch()}
            disabled={busy}
            className="px-2 py-1 text-[12px] cursor-pointer disabled:opacity-40"
            style={{ background: 'var(--hud-soft-block)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)' }}
            type="button"
          >
            {busy ? '...' : t('memory.search')}
          </button>
        </div>
      </div>

      {error && <div className="text-[12px] mb-2" style={{ color: 'var(--hud-error, #f44)' }}>{error}</div>}
      {notice && <div className="text-[12px] mb-2" style={{ color: 'var(--hud-success)' }}>{notice}</div>}
      {!history?.candidates?.length ? (
        <div className="text-[13px]" style={{ color: 'var(--hud-text-dim)' }}>
          {busy ? t('memory.historyLoading') : t('memory.noHistoryCandidates')}
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
          {history.candidates.map(candidate => (
            <div
              key={`${candidate.session_id}:${candidate.message_id}`}
              className="p-2"
              style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-soft-block)' }}
            >
              <div className="flex flex-wrap items-start justify-between gap-2 mb-1">
                <div>
                  <div className="text-[12px]" style={{ color: 'var(--hud-primary)' }}>{candidate.title}</div>
                  <div className="font-mono text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>
                    {candidate.source || 'session'} · {formatTimestamp(candidate.timestamp || candidate.started_at)}
                  </div>
                </div>
                <div className="text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>
                  {candidate.suggested_target === 'user' ? t('memory.userProfile') : t('memory.builtin')}
                </div>
              </div>
              <div className="text-[13px] mb-2" style={{ color: 'var(--hud-text)' }}>
                {candidate.snippet}
              </div>
              <div className="flex flex-wrap justify-end gap-1.5">
                <button
                  onClick={() => saveCandidate(candidate, 'memory')}
                  disabled={!!busyId}
                  className="px-2 py-1 text-[11px] cursor-pointer disabled:opacity-40"
                  style={{ background: 'var(--hud-soft-block)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)' }}
                  type="button"
                >
                  {busyId === `${candidate.message_id}:memory` ? '...' : t('memory.saveToMemory')}
                </button>
                <button
                  onClick={() => saveCandidate(candidate, 'user')}
                  disabled={!!busyId}
                  className="px-2 py-1 text-[11px] cursor-pointer disabled:opacity-40"
                  style={{ background: 'var(--hud-primary)', color: 'var(--hud-bg-deep)', border: 'none' }}
                  type="button"
                >
                  {busyId === `${candidate.message_id}:user` ? '...' : t('memory.saveToUser')}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function MemoryExportPanel() {
  const { t } = useTranslation()
  const [data, setData] = useState<MemoryExportState | null>(null)
  const [backupPath, setBackupPath] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const loadExport = async () => {
    setBusy(true)
    setError('')
    try {
      setData(await fetchMemoryExport())
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    loadExport()
  }, [])

  const createBackup = async () => {
    setBusy(true)
    setError('')
    setBackupPath('')
    try {
      const result = await createMemoryBackup()
      setData(result.export)
      setBackupPath(result.path)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const files = Object.values(data?.files || {})
  const providerCount = Object.keys(data?.provider.providers || {}).length
  const redactionCount = data?.provider.redactions.length || 0

  return (
    <div className="p-2" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-solid-block)' }}>
      <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
        <div>
          <div className="uppercase tracking-wider text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>
            {t('memory.exportBackup')}
          </div>
          <div className="text-[12px]" style={{ color: 'var(--hud-text-dim)' }}>
            {t('memory.exportBackupHint')}
          </div>
        </div>
        <div className="flex gap-1.5">
          <button
            onClick={loadExport}
            disabled={busy}
            className="px-2 py-1 text-[11px] cursor-pointer disabled:opacity-40"
            style={{ background: 'var(--hud-soft-block)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)' }}
            type="button"
          >
            {busy ? '...' : t('memory.previewExport')}
          </button>
          <button
            onClick={createBackup}
            disabled={busy}
            className="px-2 py-1 text-[11px] cursor-pointer disabled:opacity-40"
            style={{ background: 'var(--hud-primary)', color: 'var(--hud-bg-deep)', border: 'none' }}
            type="button"
          >
            {busy ? '...' : t('memory.createBackup')}
          </button>
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-1.5">
        <div className="px-2 py-1" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-soft-block)' }}>
          <div className="text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>{t('memory.files')}</div>
          <div className="text-[12px]" style={{ color: 'var(--hud-primary)' }}>{files.length}</div>
        </div>
        <div className="px-2 py-1" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-soft-block)' }}>
          <div className="text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>{t('memory.externalProvider')}</div>
          <div className="text-[12px]" style={{ color: data?.provider.active_provider ? 'var(--hud-primary)' : 'var(--hud-text-dim)' }}>
            {data?.provider.active_provider || t('memory.noneExternal')}
          </div>
        </div>
        <div className="px-2 py-1" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-soft-block)' }}>
          <div className="text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>{t('memory.configuredProviders')}</div>
          <div className="text-[12px]" style={{ color: 'var(--hud-text)' }}>{providerCount}</div>
        </div>
        <div className="px-2 py-1" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-soft-block)' }}>
          <div className="text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>{t('memory.redactedFields')}</div>
          <div className="text-[12px]" style={{ color: redactionCount ? 'var(--hud-warning)' : 'var(--hud-success)' }}>{redactionCount}</div>
        </div>
      </div>
      {!!backupPath && (
        <div className="font-mono text-[11px] mt-2" style={{ color: 'var(--hud-success)' }}>
          {t('memory.backupPath')}: {backupPath}
        </div>
      )}
      {error && <div className="text-[12px] mt-2" style={{ color: 'var(--hud-error, #f44)' }}>{error}</div>}
    </div>
  )
}

function MemoryGovernancePanel({
  settings,
  pending,
  onSettingsSaved,
  onPendingMutate,
}: {
  settings?: MemorySettingsState
  pending?: MemoryPendingState
  onSettingsSaved: () => void
  onPendingMutate: () => void
}) {
  const { t } = useTranslation()

  return (
    <div className="mt-3">
      <div className="uppercase tracking-wider text-[10px] mb-2" style={{ color: 'var(--hud-text-dim)' }}>
        {t('memory.governance')}
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <MemorySettingsPanel settings={settings} onSaved={onSettingsSaved} />
        <PendingMemoryPanel data={pending} onMutate={onPendingMutate} />
      </div>
      <div className="mt-3">
        <MemoryExportPanel />
      </div>
    </div>
  )
}

function CapabilityMatrix({
  capabilities,
  schemaSource,
}: {
  capabilities?: MemoryProviderCapabilities
  schemaSource?: MemoryProviderSchemaSource
}) {
  const { t } = useTranslation()
  const yesNo = (value?: boolean) => value ? t('memory.yes') : t('memory.no')
  const capabilityItems = [
    { key: 'external_read_mode', label: t('memory.externalRead'), value: capabilities?.external_read ? capabilities.external_read_mode : t('memory.no') },
    { key: 'direct_hud_config', label: t('memory.directHudConfig'), value: yesNo(capabilities?.direct_hud_config) },
    { key: 'requires_network', label: t('memory.requiresNetwork'), value: yesNo(capabilities?.requires_network) },
    { key: 'local_storage', label: t('memory.localStorage'), value: yesNo(capabilities?.local_storage) },
    { key: 'supports_auto_recall', label: t('memory.autoRecall'), value: yesNo(capabilities?.supports_auto_recall) },
    { key: 'supports_session_ingest', label: t('memory.sessionIngest'), value: yesNo(capabilities?.supports_session_ingest) },
    { key: 'supports_manual_write', label: t('memory.manualWrite'), value: yesNo(capabilities?.supports_manual_write) },
    { key: 'supports_tools', label: t('memory.tools'), value: yesNo(capabilities?.supports_tools) },
  ]
  const hooks = capabilities?.hooks || []
  const schemaLabel = schemaSource?.kind === 'official_schema' ? t('memory.officialSchema') : t('memory.hudMetadata')

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-2">
      <div className="lg:col-span-2">
        <div className="uppercase tracking-wider text-[10px] mb-2" style={{ color: 'var(--hud-text-dim)' }}>
          {t('memory.capabilityMatrix')}
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-1.5">
          {capabilityItems.map(item => (
            <div
              key={item.key}
              className="px-2 py-1"
              style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-soft-block)' }}
            >
              <div className="text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>{item.label}</div>
              <div className="text-[12px]" style={{ color: 'var(--hud-text)' }}>{item.value}</div>
            </div>
          ))}
        </div>
        {!!hooks.length && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            <span className="text-[11px]" style={{ color: 'var(--hud-text-dim)' }}>{t('memory.hooks')}</span>
            {hooks.map(hook => (
              <span
                key={hook}
                className="text-[11px] px-1.5 py-0.5 font-mono"
                style={{ border: '1px solid var(--hud-border)', color: 'var(--hud-primary)' }}
              >
                {hook}
              </span>
            ))}
          </div>
        )}
      </div>
      <div>
        <div className="uppercase tracking-wider text-[10px] mb-2" style={{ color: 'var(--hud-text-dim)' }}>
          {t('memory.schemaSource')}
        </div>
        <div className="px-2 py-1.5" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-soft-block)' }}>
          <div className="text-[12px]" style={{ color: schemaSource?.fallback ? 'var(--hud-warning)' : 'var(--hud-success)' }}>
            {schemaLabel}
          </div>
          <div className="text-[11px] font-mono mt-1" style={{ color: 'var(--hud-text-dim)' }}>
            {schemaSource?.method || schemaSource?.source || 'HUD'}
          </div>
        </div>
      </div>
    </div>
  )
}

function ExternalMemoryViewPanel({
  provider,
  externalView,
  busy,
  error,
  onRefresh,
}: {
  provider: MemoryProviderInfo
  externalView: MemoryProviderExternalView | null
  busy: boolean
  error: string
  onRefresh: () => void
}) {
  const { t } = useTranslation()
  const meta = provider.external_view
  const categories = externalView?.summary.categories || {}
  const items = externalView?.items || []
  const summaryOnly = externalView?.reason === 'summary_only'
    || externalView?.reason === 'provider_summary'
  const unavailableReason = externalView?.reason || meta.reason || t('memory.externalUnavailable')

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
        <div className="uppercase tracking-wider text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>
          {t('memory.externalView')}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px]" style={{ color: 'var(--hud-text-dim)' }}>
            {t('memory.readOnly')}
          </span>
          {meta.available && (
            <button
              onClick={onRefresh}
              disabled={busy}
              className="px-2 py-1 text-[11px] cursor-pointer disabled:opacity-40"
              style={{ background: 'var(--hud-soft-block)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)' }}
              type="button"
            >
              {busy ? '...' : t('memory.refreshExternal')}
            </button>
          )}
        </div>
      </div>

      {!meta.available ? (
        <div className="text-[12px] p-2" style={{ border: '1px solid var(--hud-border)', color: 'var(--hud-text-dim)' }}>
          {t('memory.externalUnavailable')}: {unavailableReason}
        </div>
      ) : (
        <div className="space-y-2">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-1.5">
            <div className="px-2 py-1" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-soft-block)' }}>
              <div className="text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>{t('memory.entries')}</div>
              <div className="text-[12px]" style={{ color: 'var(--hud-primary)' }}>{externalView?.summary.total ?? 0}</div>
            </div>
            <div className="px-2 py-1 md:col-span-2" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-soft-block)' }}>
              <div className="text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>{t('memory.externalCategories')}</div>
              <div className="text-[12px]" style={{ color: 'var(--hud-text)' }}>
                {Object.keys(categories).length
                  ? Object.entries(categories).map(([name, count]) => `${name}: ${count}`).join(' · ')
                  : t('memory.empty')}
              </div>
            </div>
          </div>

          {busy && <div className="text-[12px]" style={{ color: 'var(--hud-text-dim)' }}>{t('memory.externalLoading')}</div>}
          {error && <div className="text-[12px]" style={{ color: 'var(--hud-error, #f44)' }}>{error}</div>}
          {externalView?.available === false && (
            <div className="text-[12px]" style={{ color: 'var(--hud-warning)' }}>
              {t('memory.externalUnavailable')}: {unavailableReason}
            </div>
          )}

          {!busy && summaryOnly && (
            <div className="text-[12px] p-2" style={{ border: '1px solid var(--hud-border)', color: 'var(--hud-text-dim)' }}>
              {t('memory.externalSummaryOnly')}
            </div>
          )}
          {!busy && !items.length ? (
            <div className="text-[12px] p-2" style={{ border: '1px solid var(--hud-border)', color: 'var(--hud-text-dim)' }}>
              {t('memory.externalNoItems')}
            </div>
          ) : !!items.length && (
            <div className="space-y-1.5">
              {items.map(item => (
                <div
                  key={item.id}
                  className="p-2"
                  style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-soft-block)' }}
                >
                  <div className="flex flex-wrap items-start justify-between gap-2 mb-1">
                    <div>
                      <span className="font-mono text-[11px]" style={{ color: 'var(--hud-primary)' }}>
                        {item.category || 'general'}
                      </span>
                      {!!item.tags?.length && (
                        <span className="text-[11px] ml-2" style={{ color: 'var(--hud-text-dim)' }}>
                          {item.tags.join(', ')}
                        </span>
                      )}
                    </div>
                    <div className="font-mono text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>
                      {t('memory.externalTrust')}: {item.trust_score}
                      {' · '}
                      {t('memory.externalRetrievals')}: {item.retrieval_count}
                      {' · '}
                      {t('memory.externalHelpful')}: {item.helpful_count}
                    </div>
                  </div>
                  <div className="text-[13px]" style={{ color: 'var(--hud-text)' }}>{item.content}</div>
                  <div className="text-[10px] mt-1" style={{ color: 'var(--hud-text-dim)' }}>
                    {item.updated_at || item.created_at || item.id}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

type MemoryProviderConfigField = MemoryProviderInfo['config_fields'][number]
type MemoryProviderConsoleTab = 'overview' | 'config' | 'diagnostics' | 'external' | 'install'

const providerConsoleTabs: Array<{ id: MemoryProviderConsoleTab; labelKey: TranslationKey }> = [
  { id: 'overview', labelKey: 'memory.providerOverview' },
  { id: 'config', labelKey: 'memory.configureProvider' },
  { id: 'diagnostics', labelKey: 'memory.providerDiagnostics' },
  { id: 'external', labelKey: 'memory.externalView' },
  { id: 'install', labelKey: 'memory.installGuide' },
]

function providerGroups(providers: MemoryProviderInfo[]): Array<{ id: string; labelKey: TranslationKey; providers: MemoryProviderInfo[] }> {
  const groups: Array<{ id: string; labelKey: TranslationKey; providers: MemoryProviderInfo[] }> = [
    {
      id: 'official',
      labelKey: 'memory.officialProviders',
      providers: providers.filter(provider => provider.group !== 'community'),
    },
    {
      id: 'community',
      labelKey: 'memory.communityProviders',
      providers: providers.filter(provider => provider.group === 'community'),
    },
  ]
  return groups.filter(group => group.providers.length)
}

function ProviderPicker({
  providers,
  selectedId,
  activeId,
  busy,
  onSelect,
  readinessText,
}: {
  providers: MemoryProviderInfo[]
  selectedId: string
  activeId: string
  busy: boolean
  onSelect: (provider: string) => void
  readinessText: (provider?: MemoryProviderInfo) => string
}) {
  const { t } = useTranslation()
  const groups = providerGroups(providers)
  const providerPickerOptionStyle = {
    background: 'var(--hud-bg-panel)',
    color: 'var(--hud-text)',
  }

  return (
    <label className="block">
      <span className="uppercase tracking-wider text-[10px] mb-1 block" style={{ color: 'var(--hud-text-dim)' }}>
        {t('memory.selectProvider')}
      </span>
      <select
        value={selectedId}
        onChange={event => onSelect(event.target.value)}
        disabled={busy || !providers.length}
        className="w-full text-[12px] px-2 py-1.5 outline-none"
        style={{
          background: 'var(--hud-soft-block)',
          border: '1px solid var(--hud-border)',
          color: 'var(--hud-text)',
        }}
      >
        {!providers.length && <option value="" style={providerPickerOptionStyle}>{t('memory.notConfigured')}</option>}
        {groups.map(group => (
          <optgroup key={group.id} label={t(group.labelKey)} style={providerPickerOptionStyle}>
            {group.providers.map(item => {
              const status = item.id === activeId
                ? t('memory.activeProvider')
                : item.configured ? t('memory.providerConfiguredSuffix') : readinessText(item)
              return (
                <option key={item.id} value={item.id} style={providerPickerOptionStyle}>
                  {item.label} - {status}
                </option>
              )
            })}
          </optgroup>
        ))}
      </select>
    </label>
  )
}

function ProviderStatusCards({
  provider,
  activeHealth,
  readinessText,
  healthColor,
  healthText,
}: {
  provider?: MemoryProviderInfo
  activeHealth?: MemoryProviderHealth | null
  readinessText: (provider?: MemoryProviderInfo) => string
  healthColor: (ok: boolean | null | undefined) => string
  healthText: (ok: boolean | null | undefined) => string
}) {
  const { t } = useTranslation()

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-1.5">
      <div className="px-2 py-1" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-soft-block)' }}>
        <div className="text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>{t('memory.externalProvider')}</div>
        <div className="text-[12px]" style={{ color: provider ? 'var(--hud-primary)' : 'var(--hud-text-dim)' }}>
          {provider?.label || t('memory.noneExternal')}
        </div>
      </div>
      <div className="px-2 py-1" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-soft-block)' }}>
        <div className="text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>{t('memory.configured')}</div>
        <div className="text-[12px]" style={{ color: provider?.configured ? 'var(--hud-success)' : 'var(--hud-warning)' }}>
          {readinessText(provider)}
        </div>
      </div>
      <div className="px-2 py-1" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-soft-block)' }}>
        <div className="text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>{t('memory.healthDependencies')}</div>
        <div className="text-[12px]" style={{ color: healthColor(activeHealth?.dependencies.ok) }}>
          {healthText(activeHealth?.dependencies.ok)}
        </div>
      </div>
      <div className="px-2 py-1" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-soft-block)' }}>
        <div className="text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>{t('memory.activeProvider')}</div>
        <div className="text-[12px]" style={{ color: activeHealth?.active ? 'var(--hud-success)' : 'var(--hud-text-dim)' }}>
          {activeHealth?.active ? t('memory.activeState') : t('memory.inactiveState')}
        </div>
      </div>
    </div>
  )
}

function CapabilitySummary({ capabilities }: { capabilities?: MemoryProviderCapabilities }) {
  const { t } = useTranslation()
  const enabled = [
    capabilities?.supports_auto_recall && t('memory.autoRecall'),
    capabilities?.supports_session_ingest && t('memory.sessionIngest'),
    capabilities?.supports_tools && t('memory.tools'),
    capabilities?.external_read && t('memory.externalRead'),
    capabilities?.supports_manual_write && t('memory.manualWrite'),
  ].filter(Boolean)

  return (
    <div>
      <div className="uppercase tracking-wider text-[10px] mb-2" style={{ color: 'var(--hud-text-dim)' }}>
        {t('memory.capabilitySummary')}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {enabled.length ? enabled.map(item => (
          <span
            key={String(item)}
            className="text-[11px] px-1.5 py-0.5"
            style={{ border: '1px solid var(--hud-border)', color: 'var(--hud-primary)' }}
          >
            {item}
          </span>
        )) : (
          <span className="text-[12px]" style={{ color: 'var(--hud-text-dim)' }}>{t('memory.no')}</span>
        )}
      </div>
    </div>
  )
}

function ProviderOverviewTab({
  provider,
  activeProvider,
  activeHealth,
  statusCommand,
  busy,
  readinessText,
  healthColor,
  healthText,
  onEnable,
  onDisable,
}: {
  provider?: MemoryProviderInfo
  activeProvider?: MemoryProviderInfo
  activeHealth?: MemoryProviderHealth | null
  statusCommand: string
  busy: boolean
  readinessText: (provider?: MemoryProviderInfo) => string
  healthColor: (ok: boolean | null | undefined) => string
  healthText: (ok: boolean | null | undefined) => string
  onEnable: () => void
  onDisable: () => void
}) {
  const { t } = useTranslation()

  return (
    <div className="space-y-3">
      <ProviderStatusCards
        provider={provider}
        activeHealth={activeHealth}
        readinessText={readinessText}
        healthColor={healthColor}
        healthText={healthText}
      />
      <CapabilitySummary capabilities={provider?.capabilities} />
      <div className="text-[12px]" style={{ color: 'var(--hud-text-dim)' }}>
        {t('memory.oneExternalOnly')}
      </div>
      <div className="font-mono text-[12px]" style={{ color: 'var(--hud-text-dim)' }}>
        {provider?.config_command || statusCommand}
      </div>
      <div className="flex flex-wrap justify-end gap-2">
        {!!activeProvider && (
          <button
            onClick={onDisable}
            disabled={busy}
            className="px-3 py-1.5 text-[12px] cursor-pointer disabled:opacity-40"
            style={{ background: 'var(--hud-soft-block)', color: 'var(--hud-warning)', border: '1px solid var(--hud-border)' }}
            type="button"
          >
            {busy ? '...' : t('memory.turnOffExternal')}
          </button>
        )}
        <button
          onClick={onEnable}
          disabled={busy || !provider || provider.active}
          className="px-3 py-1.5 text-[12px] cursor-pointer disabled:opacity-40"
          style={{ background: 'var(--hud-primary)', color: 'var(--hud-bg-deep)', border: 'none' }}
          type="button"
        >
          {busy ? '...' : provider?.active ? t('memory.activeProvider') : t('memory.setProvider')}
        </button>
      </div>
    </div>
  )
}

function providerFieldLabel(provider: MemoryProviderInfo, fieldName: string) {
  return provider.config_fields.find(field => field.name === fieldName)?.label || fieldName
}

function modeRequirementLabels(provider: MemoryProviderInfo, mode?: MemoryProviderConfigMode) {
  if (!mode) return []
  const required = mode.required_fields
    .filter(name => name !== 'mode')
    .map(name => providerFieldLabel(provider, name))
  const requiredAny = mode.required_any
    .map(group => group
      .filter(name => name !== 'mode')
      .map(name => providerFieldLabel(provider, name))
      .join(' / '))
    .filter(Boolean)
  return [...required, ...requiredAny]
}

function modeDependencyLabels(dependencies: MemoryProviderDependency[] = []) {
  return dependencies.map(dependency => `${dependency.kind}:${dependency.name}`)
}

function modeInstallCommands(
  provider: MemoryProviderInfo,
  mode: MemoryProviderConfigMode,
  setupCommand: string,
  statusCommand: string,
  offCommand: string
) {
  return [
    { labelKey: 'memory.installCommand' as TranslationKey, command: mode.setup_command || provider.setup_command || setupCommand },
    { labelKey: 'memory.configCommand' as TranslationKey, command: provider.config_command || setupCommand },
    { labelKey: 'memory.statusCommand' as TranslationKey, command: mode.status_command || statusCommand },
    { labelKey: 'memory.offCommand' as TranslationKey, command: offCommand },
  ].filter(item => item.command)
}

function ProviderConfigTab({
  provider,
  activeMode,
  selectedMode,
  statusCommand,
  visibleConfigFields,
  configDraft,
  requiredConfigIssues,
  busy,
  onModeSelect,
  onDraftChange,
  onSave,
  fieldIsRequired,
}: {
  provider: MemoryProviderInfo
  activeMode?: MemoryProviderConfigMode
  selectedMode: string
  statusCommand: string
  visibleConfigFields: MemoryProviderConfigField[]
  configDraft: Record<string, string>
  requiredConfigIssues: string[]
  busy: boolean
  onModeSelect: (mode: string) => void
  onDraftChange: (field: string, value: string) => void
  onSave: () => void
  fieldIsRequired: (field: MemoryProviderConfigField) => boolean
}) {
  const { t } = useTranslation()
  const configModeRequirements = modeRequirementLabels(provider, activeMode)

  return (
    <div className="space-y-3">
      {!!provider.config_modes?.length && (
        <div>
          <div className="uppercase tracking-wider text-[10px] mb-2" style={{ color: 'var(--hud-text-dim)' }}>
            {t('memory.configMode')}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {provider.config_modes.map(mode => {
              const selectedConfigMode = selectedMode === mode.id
              return (
                <button
                  key={mode.id}
                  onClick={() => onModeSelect(mode.id)}
                  disabled={busy}
                  className="px-2 py-1 text-[12px] cursor-pointer disabled:opacity-40"
                  style={{
                    background: selectedConfigMode ? 'var(--hud-primary)' : 'var(--hud-bg-hover)',
                    color: selectedConfigMode ? 'var(--hud-bg-deep)' : 'var(--hud-text)',
                    border: '1px solid var(--hud-border)',
                  }}
                  type="button"
                  title={mode.description || mode.storage}
                >
                  {mode.label}
                </button>
              )
            })}
          </div>
          {!!activeMode?.description && (
            <div className="text-[11px] mt-1" style={{ color: 'var(--hud-text-dim)' }}>
              {activeMode.description}
            </div>
          )}
          {activeMode && (
            <div className="text-[11px] mt-1 font-mono" style={{ color: 'var(--hud-text-dim)' }}>
              {t('memory.minimumConfig')}: {configModeRequirements.length ? configModeRequirements.join(' + ') : t('memory.noMinimumConfig')}
            </div>
          )}
        </div>
      )}

      <div>
        <div className="uppercase tracking-wider text-[10px] mb-2" style={{ color: 'var(--hud-text-dim)' }}>
          {t('memory.configureProvider')}
        </div>
        {visibleConfigFields.length ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {visibleConfigFields.map(field => {
              const current = provider.config_values?.[field.name]
              return (
                <label key={field.name} className="block">
                  <span className="flex flex-wrap items-center gap-1.5 text-[11px] mb-1">
                    <span style={{ color: 'var(--hud-text-dim)' }}>
                      {field.label}
                      {fieldIsRequired(field) && (
                        <span style={{ color: 'var(--hud-error, #f44)' }}> {t('memory.requiredMarker')}</span>
                      )}
                    </span>
                    {field.secret && current?.configured && (
                      <span style={{ color: 'var(--hud-success)' }}>{t('memory.secretConfigured')}</span>
                    )}
                  </span>
                  {field.control === 'boolean' ? (
                    <span
                      className="flex items-center gap-2 w-full text-[12px] px-2 py-1.5"
                      style={{
                        background: 'var(--hud-soft-block)',
                        border: '1px solid var(--hud-border)',
                        color: 'var(--hud-text)',
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={configDraft[field.name] === 'true'}
                        onChange={event => onDraftChange(field.name, event.target.checked ? 'true' : 'false')}
                      />
                      <span>{configDraft[field.name] === 'true' ? t('memory.yes') : t('memory.no')}</span>
                    </span>
                  ) : (
                    <input
                      value={configDraft[field.name] ?? ''}
                      type={field.secret ? 'password' : 'text'}
                      onChange={event => onDraftChange(field.name, event.target.value)}
                      placeholder={field.secret && current?.configured ? t('memory.replaceSecret') : field.help}
                      className="w-full text-[12px] px-2 py-1.5 outline-none"
                      style={{
                        background: 'var(--hud-soft-block)',
                        border: '1px solid var(--hud-border)',
                        color: 'var(--hud-text)',
                      }}
                    />
                  )}
                  <span className="block text-[10px] mt-0.5 font-mono" style={{ color: 'var(--hud-text-dim)' }}>
                    {current?.source || field.path || field.storage}
                  </span>
                </label>
              )
            })}
          </div>
        ) : (
          <div className="text-[12px]" style={{ color: 'var(--hud-text-dim)' }}>
            {t('memory.noConfigFields')}
          </div>
        )}
      </div>

      {!!requiredConfigIssues.length && (
        <div className="text-[12px]" style={{ color: 'var(--hud-error, #f44)' }}>
          {t('memory.requiredConfigMissing')}: {requiredConfigIssues.join(', ')}
        </div>
      )}

      <div className="text-[11px]" style={{ color: 'var(--hud-text-dim)' }}>
        {t('memory.configNextStep')}: {t('memory.checkStatus')}
        <span className="font-mono"> · {statusCommand}</span>
      </div>

      <div className="flex justify-end">
        <button
          onClick={onSave}
          disabled={busy || !provider.config_fields?.length || !!requiredConfigIssues.length}
          className="px-3 py-1.5 text-[12px] cursor-pointer disabled:opacity-40"
          style={{ background: 'var(--hud-soft-block)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)' }}
          type="button"
        >
          {busy ? '...' : t('memory.saveProviderConfig')}
        </button>
      </div>
    </div>
  )
}

function ProviderDiagnosticsTab({
  provider,
  activeHealth,
  statusResult,
  statusOutput,
  busy,
  checkedAtText,
  healthColor,
  healthText,
  onCheck,
  onOpenStatusModal,
}: {
  provider: MemoryProviderInfo
  activeHealth?: MemoryProviderHealth | null
  statusResult: MemoryProviderCheckResult | null
  statusOutput: string
  busy: boolean
  checkedAtText: (value?: string) => string
  healthColor: (ok: boolean | null | undefined) => string
  healthText: (ok: boolean | null | undefined) => string
  onCheck: () => void
  onOpenStatusModal: () => void
}) {
  const { t } = useTranslation()

  return (
    <div className="space-y-3">
      <CapabilityMatrix
        capabilities={provider.capabilities}
        schemaSource={provider.schema_source}
      />

      {activeHealth && (
        <div>
          <div className="uppercase tracking-wider text-[10px] mb-1" style={{ color: 'var(--hud-text-dim)' }}>
            {t('memory.healthChecks')}
          </div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-1.5">
            <div className="px-2 py-1" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-soft-block)' }}>
              <div className="text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>{t('memory.healthConfig')}</div>
              <div className="text-[12px]" style={{ color: healthColor(activeHealth.required_config.ok) }}>
                {healthText(activeHealth.required_config.ok)}
              </div>
            </div>
            <div className="px-2 py-1" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-soft-block)' }}>
              <div className="text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>{t('memory.healthDependencies')}</div>
              <div className="text-[12px]" style={{ color: healthColor(activeHealth.dependencies.ok) }}>
                {healthText(activeHealth.dependencies.ok)}
              </div>
            </div>
            <div className="px-2 py-1" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-soft-block)' }}>
              <div className="text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>{t('memory.activeProvider')}</div>
              <div className="text-[12px]" style={{ color: activeHealth.active ? 'var(--hud-success)' : 'var(--hud-text-dim)' }}>
                {activeHealth.active ? t('memory.activeState') : t('memory.inactiveState')}
              </div>
            </div>
            <div className="px-2 py-1" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-soft-block)' }}>
              <div className="text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>{t('memory.healthRuntime')}</div>
              <div className="text-[12px]" style={{ color: healthColor(activeHealth.runtime?.ok) }}>
                {healthText(activeHealth.runtime?.ok)}
              </div>
            </div>
            <div className="px-2 py-1" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-soft-block)' }}>
              <div className="text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>{t('memory.healthStatus')}</div>
              <div className="text-[12px]" style={{ color: healthColor(activeHealth.status_command?.ok) }}>
                {healthText(activeHealth.status_command?.ok)}
              </div>
            </div>
          </div>
          {!!activeHealth.config_files.length && (
            <div className="mt-2">
              <div className="text-[10px] mb-1" style={{ color: 'var(--hud-text-dim)' }}>
                {t('memory.healthConfigFiles')}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {activeHealth.config_files.map(file => (
                  <span
                    key={file.path}
                    className="text-[11px] px-1.5 py-0.5 font-mono"
                    style={{
                      border: '1px solid var(--hud-border)',
                      color: file.exists ? 'var(--hud-success)' : 'var(--hud-text-dim)',
                    }}
                  >
                    {file.path}: {file.exists ? t('memory.present') : t('memory.fileMissing')}
                  </span>
                ))}
              </div>
            </div>
          )}
          <div className="text-[10px] mt-2" style={{ color: 'var(--hud-text-dim)' }}>
            {t('memory.lastChecked')}: {checkedAtText(activeHealth.checked_at)}
          </div>
        </div>
      )}

      {!!provider.checks?.length && (
        <div>
          <div className="uppercase tracking-wider text-[10px] mb-1" style={{ color: 'var(--hud-text-dim)' }}>
            {t('memory.dependencyChecks')}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {provider.checks.map(check => (
              <span
                key={`${check.kind}:${check.name}`}
                className="text-[11px] px-1.5 py-0.5"
                style={{
                  border: '1px solid var(--hud-border)',
                  color: check.ok ? 'var(--hud-success)' : 'var(--hud-warning)',
                }}
              >
                {check.name}: {check.ok ? t('memory.present') : t('memory.missingDependency')}
              </span>
            ))}
          </div>
        </div>
      )}

      {!!provider.notes?.length && (
        <div className="text-[12px] font-mono" style={{ color: 'var(--hud-text-dim)' }}>
          {provider.notes.join(' · ')}
        </div>
      )}

      <div className="flex justify-end">
        <button
          onClick={onCheck}
          disabled={busy}
          className="px-3 py-1.5 text-[12px] cursor-pointer disabled:opacity-40"
          style={{ background: 'var(--hud-soft-block)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)' }}
          type="button"
        >
          {busy ? '...' : t('memory.checkStatus')}
        </button>
      </div>

      {statusResult && (
        <div>
          <div className="uppercase tracking-wider text-[10px] mb-1" style={{ color: 'var(--hud-text-dim)' }}>
            {t('memory.statusOutput')}
          </div>
          <textarea
            readOnly
            aria-readonly="true"
            aria-multiline="true"
            tabIndex={0}
            aria-label={t('memory.statusOutput')}
            value={statusOutput}
            onClick={onOpenStatusModal}
            onKeyDown={event => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                onOpenStatusModal()
              }
            }}
            className="w-full resize-y text-[11px] whitespace-pre-wrap p-2 overflow-auto cursor-pointer outline-none font-mono"
            style={{
              background: 'var(--hud-soft-block)',
              border: '1px solid var(--hud-border)',
              color: statusResult.status_command.ok ? 'var(--hud-text)' : 'var(--hud-warning)',
              maxHeight: '280px',
              minHeight: '180px',
            }}
          />
        </div>
      )}
    </div>
  )
}

function ProviderExternalDataTab({
  provider,
  externalView,
  busy,
  error,
  onRefresh,
}: {
  provider: MemoryProviderInfo
  externalView: MemoryProviderExternalView | null
  busy: boolean
  error: string
  onRefresh: () => void
}) {
  return (
    <ExternalMemoryViewPanel
      provider={provider}
      externalView={externalView}
      busy={busy}
      error={error}
      onRefresh={onRefresh}
    />
  )
}

function ProviderInstallGuideTab({
  provider,
  setupCommand,
  statusCommand,
  offCommand,
}: {
  provider: MemoryProviderInfo
  setupCommand: string
  statusCommand: string
  offCommand: string
}) {
  const { t } = useTranslation()
  const commands = [
    { label: t('memory.installCommand'), command: provider.setup_command || setupCommand },
    { label: t('memory.configCommand'), command: provider.config_command || setupCommand },
    { label: t('memory.statusCommand'), command: statusCommand },
    { label: t('memory.offCommand'), command: offCommand },
  ].filter(item => item.command)
  const modeCommands = provider.config_modes?.length
    ? provider.config_modes.map(mode => ({ mode, commands: modeInstallCommands(provider, mode, setupCommand, statusCommand, offCommand) }))
    : []

  return (
    <div className="space-y-2">
      <div className="text-[12px]" style={{ color: 'var(--hud-text-dim)' }}>
        {t('memory.installGuideHint')}
      </div>
      {modeCommands.length ? (
        <div className="space-y-2">
          {modeCommands.map(item => {
            const requirements = modeRequirementLabels(provider, item.mode)
            const dependencies = modeDependencyLabels(item.mode.dependencies)
            return (
              <div key={item.mode.id} className="p-2 space-y-2" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-soft-block)' }}>
                <div>
                  <div className="text-[12px]" style={{ color: 'var(--hud-primary)' }}>{item.mode.label}</div>
                  {!!item.mode.description && (
                    <div className="text-[11px]" style={{ color: 'var(--hud-text-dim)' }}>{item.mode.description}</div>
                  )}
                  <div className="text-[11px] mt-1 font-mono" style={{ color: 'var(--hud-text-dim)' }}>
                    {t('memory.minimumConfig')}: {requirements.length ? requirements.join(' + ') : t('memory.noMinimumConfig')}
                  </div>
                  {!!dependencies.length && (
                    <div className="text-[11px] mt-1 font-mono" style={{ color: 'var(--hud-text-dim)' }}>
                      {t('memory.modeDependencies')}: {dependencies.join(' + ')}
                    </div>
                  )}
                  {!!item.mode.next_steps && (
                    <div className="text-[11px] mt-1" style={{ color: 'var(--hud-text-dim)' }}>
                      {t('memory.nextSteps')}: {item.mode.next_steps}
                    </div>
                  )}
                </div>
                <div className="grid grid-cols-1 gap-1.5">
                  {item.commands.map(command => (
                    <div key={`${item.mode.id}:${command.labelKey}:${command.command}`}>
                      <div className="uppercase tracking-wider text-[10px] mb-1" style={{ color: 'var(--hud-text-dim)' }}>
                        {t(command.labelKey)}
                      </div>
                      <code className="text-[12px] break-all" style={{ color: 'var(--hud-text)' }}>{command.command}</code>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      ) : commands.map(item => (
        <div key={`${item.label}:${item.command}`} className="p-2" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-soft-block)' }}>
          <div className="uppercase tracking-wider text-[10px] mb-1" style={{ color: 'var(--hud-text-dim)' }}>
            {item.label}
          </div>
          <code className="text-[12px] break-all" style={{ color: 'var(--hud-text)' }}>{item.command}</code>
        </div>
      ))}
      <div className="text-[11px]" style={{ color: 'var(--hud-warning)' }}>
        {t('memory.installGuideRisk')}
      </div>
    </div>
  )
}

function MemoryProvidersPanel({
  data,
  onMutate,
}: {
  data?: MemoryProvidersState
  onMutate: () => void
}) {
  const { t, lang } = useTranslation()
  const [selected, setSelected] = useState('')
  const [selectedModes, setSelectedModes] = useState<Record<string, string>>({})
  const [configDraft, setConfigDraft] = useState<Record<string, string>>({})
  const [activeProviderTab, setActiveProviderTab] = useState<MemoryProviderConsoleTab>('overview')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [statusResult, setStatusResult] = useState<MemoryProviderCheckResult | null>(null)
  const [statusModalOpen, setStatusModalOpen] = useState(false)
  const [externalView, setExternalView] = useState<MemoryProviderExternalView | null>(null)
  const [externalViewBusy, setExternalViewBusy] = useState(false)
  const [externalViewError, setExternalViewError] = useState('')

  const providers = Object.values(data?.providers || {})
  const active = data?.active_provider || ''
  const selectedProvider = providers.find(provider => provider.id === selected)
  const activeProvider = providers.find(provider => provider.id === active)
  const detailProvider = selectedProvider || activeProvider || providers[0]
  const selectedProviderId = detailProvider?.id || ''
  const externalMemoryTitleContext = activeProvider?.label || t('memory.notConfigured')
  const externalMemoryTitle = lang === 'zh'
    ? `${t('memory.externalMemory')}（${externalMemoryTitleContext}）`
    : `${t('memory.externalMemory')} (${externalMemoryTitleContext})`
  const selectedMode = detailProvider
    ? selectedModes[detailProvider.id] || detailProvider.current_mode || detailProvider.default_mode || detailProvider.config_modes?.[0]?.id || ''
    : ''
  const activeMode = detailProvider?.config_modes?.find(mode => mode.id === selectedMode)
  const modeFieldNames = new Set(
    (detailProvider?.config_fields || [])
      .filter(field => field.name === 'mode' && !!detailProvider?.config_modes?.length)
      .map(field => field.name)
  )
  const visibleConfigFields = detailProvider
    ? (detailProvider.config_fields || []).filter(field => {
      if (modeFieldNames.has(field.name)) return false
      if (!selectedMode || !field.mode_ids?.length) return true
      return field.mode_ids.includes(selectedMode)
    })
    : []

  useEffect(() => {
    if (!detailProvider) return
    const nextDraft: Record<string, string> = {}
    for (const field of detailProvider.config_fields || []) {
      const current = detailProvider.config_values?.[field.name]
      nextDraft[field.name] = field.secret ? '' : current?.value || ''
    }
    setConfigDraft(nextDraft)
    setError('')
    setNotice('')
    setStatusResult(null)
    setStatusModalOpen(false)
  }, [detailProvider?.id, data?.active_provider])

  useEffect(() => {
    if (!detailProvider) return
    const defaultMode = detailProvider.current_mode || detailProvider.default_mode || detailProvider.config_modes?.[0]?.id || ''
    if (!defaultMode) return
    setSelectedModes(prev => prev[detailProvider.id] ? prev : { ...prev, [detailProvider.id]: defaultMode })
  }, [detailProvider?.id, detailProvider?.current_mode, detailProvider?.default_mode])

  useEffect(() => {
    setExternalView(null)
    setExternalViewError('')
    if (!detailProvider || !detailProvider.external_view?.available) {
      setExternalViewBusy(false)
      return
    }

    let cancelled = false
    setExternalViewBusy(true)
    fetchProviderExternalView(detailProvider.id)
      .then(result => {
        if (!cancelled) setExternalView(result)
      })
      .catch((e: any) => {
        if (!cancelled) setExternalViewError(e.message)
      })
      .finally(() => {
        if (!cancelled) setExternalViewBusy(false)
      })

    return () => { cancelled = true }
  }, [detailProvider?.id, detailProvider?.external_view?.available])

  const readinessText = (provider?: MemoryProviderInfo) => {
    if (!provider) return t('memory.notConfigured')
    if (provider.readiness === 'ready') return t('memory.verified')
    if (provider.readiness === 'selected') return t('memory.selectedNotVerified')
    if (provider.readiness === 'configured') return t('memory.configured')
    return t('memory.missingConfig')
  }

  const fieldHasValue = (
    provider: MemoryProviderInfo,
    field: MemoryProviderConfigField,
    modeId = ''
  ) => {
    if (field.name === 'mode' && modeId) return true
    const draftValue = (configDraft[field.name] || '').trim()
    const current = provider.config_values?.[field.name]
    return !!draftValue || !!current?.configured
  }

  const validateRequiredConfig = (provider?: MemoryProviderInfo, modeId = '') => {
    if (!provider) return []
    const fieldsByName = new Map(provider.config_fields.map(field => [field.name, field]))
    const configMode = provider.config_modes?.find(mode => mode.id === modeId)
    const requiredFields = configMode
      ? configMode.required_fields
      : provider.config_fields.filter(field => field.requirement === 'required').map(field => field.name)
    const requiredGroups = configMode
      ? configMode.required_any
      : provider.config_fields
        .filter(field => field.requirement === 'required_any' && field.required_group?.length)
        .map(field => field.required_group)
    const missingRequired = requiredFields
      .map(name => fieldsByName.get(name))
      .filter((field): field is MemoryProviderConfigField => !!field)
      .filter(field => !fieldHasValue(provider, field, modeId))
      .filter(field => !modeFieldNames.has(field.name))
      .map(field => field.label || field.name)
    const groupKeys = new Set<string>()
    const missingGroups: string[] = []
    for (const group of requiredGroups) {
      if (!group?.length) continue
      const key = group.join('|')
      if (groupKeys.has(key)) continue
      groupKeys.add(key)
      const satisfied = group.some(name => {
        const groupField = fieldsByName.get(name)
        return groupField ? fieldHasValue(provider, groupField, modeId) : false
      })
      if (!satisfied) {
        const label = group
          .filter(name => !modeFieldNames.has(name))
          .map(name => fieldsByName.get(name)?.label || name)
          .join(' / ')
        if (label) missingGroups.push(label)
      }
    }
    return [...missingRequired, ...missingGroups]
  }

  const requiredConfigIssues = validateRequiredConfig(detailProvider, selectedMode)
  const activeHealth = statusResult?.health || detailProvider?.health

  const healthColor = (ok: boolean | null | undefined) => {
    if (ok === true) return 'var(--hud-success)'
    if (ok === false) return 'var(--hud-warning)'
    return 'var(--hud-text-dim)'
  }

  const healthText = (ok: boolean | null | undefined) => {
    if (ok === true) return t('memory.ok')
    if (ok === false) return t('memory.missingConfig')
    return t('memory.statusNotRun')
  }

  const checkedAtText = (value?: string) => {
    if (!value) return t('memory.statusNotRun')
    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime())) return value
    return parsed.toLocaleString()
  }

  const formatRuntimeOutput = (health?: MemoryProviderHealth | null) => {
    const runtime = health?.runtime
    if (!runtime || runtime.reason === 'not_run') return ''
    const lines = [
      `${t('memory.healthRuntime')}: ${healthText(runtime.ok)}${runtime.mode ? ` (${runtime.mode})` : ''}`,
    ]
    if (runtime.reason) lines.push(`reason: ${runtime.reason}`)
    for (const check of runtime.checks || []) {
      const pieces = [
        `${check.name}: ${healthText(check.ok)}`,
        check.url || '',
        check.command || '',
        check.status_code ? `HTTP ${check.status_code}` : '',
        check.error || '',
      ].filter(Boolean)
      lines.push(pieces.join(' · '))
    }
    return lines.join('\n')
  }

  const statusOutput = [
    statusResult?.status_command.output || statusResult?.status_command.error || t('memory.noStatusOutput'),
    formatRuntimeOutput(activeHealth),
  ].filter(Boolean).join('\n\n')

  const fieldIsRequired = (field: MemoryProviderConfigField) => {
    if (activeMode) {
      return activeMode.required_fields.includes(field.name)
        || activeMode.required_any.some(group => group.includes(field.name))
    }
    return field.requirement !== 'optional'
  }

  const submit = async (provider: string) => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await setMemoryProvider(provider)
      onMutate()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const saveConfig = async () => {
    if (!detailProvider) return
    const issues = validateRequiredConfig(detailProvider, selectedMode)
    if (issues.length) {
      setError(`${t('memory.requiredConfigMissing')}: ${issues.join(', ')}`)
      setNotice('')
      return
    }
    const fields: Record<string, string> = {}
    for (const field of visibleConfigFields) {
      const value = (configDraft[field.name] || '').trim()
      if (value) fields[field.name] = value
    }
    if (selectedMode && modeFieldNames.has('mode')) fields.mode = selectedMode
    if (!Object.keys(fields).length) {
      setError(t('memory.noConfigValues'))
      setNotice('')
      return
    }
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await saveMemoryProviderConfig(detailProvider.id, fields, selectedMode)
      setConfigDraft(prev => {
        const next = { ...prev }
        for (const field of detailProvider.config_fields || []) {
          if (field.secret) next[field.name] = ''
        }
        return next
      })
      setNotice(t('memory.configSaved'))
      onMutate()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const runStatusCheck = async () => {
    if (!detailProvider) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const result = await checkMemoryProviderStatus(detailProvider.id, selectedMode)
      setStatusResult(result)
      onMutate()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const refreshExternalView = async () => {
    if (!detailProvider?.external_view?.available) return
    setExternalViewBusy(true)
    setExternalViewError('')
    try {
      const result = await fetchProviderExternalView(detailProvider.id)
      setExternalView(result)
    } catch (e: any) {
      setExternalViewError(e.message)
    } finally {
      setExternalViewBusy(false)
    }
  }

  const renderProviderTab = () => {
    if (!detailProvider) {
      return <div className="text-[12px]" style={{ color: 'var(--hud-text-dim)' }}>{t('memory.selectProvider')}</div>
    }
    if (activeProviderTab === 'config') {
      return (
        <ProviderConfigTab
          provider={detailProvider}
          activeMode={activeMode}
          selectedMode={selectedMode}
          statusCommand={data?.status_command || 'hermes memory status'}
          visibleConfigFields={visibleConfigFields}
          configDraft={configDraft}
          requiredConfigIssues={requiredConfigIssues}
          busy={busy}
          onModeSelect={mode => setSelectedModes(prev => ({ ...prev, [detailProvider.id]: mode }))}
          onDraftChange={(field, value) => setConfigDraft(prev => ({ ...prev, [field]: value }))}
          onSave={saveConfig}
          fieldIsRequired={fieldIsRequired}
        />
      )
    }
    if (activeProviderTab === 'diagnostics') {
      return (
        <ProviderDiagnosticsTab
          provider={detailProvider}
          activeHealth={activeHealth}
          statusResult={statusResult}
          statusOutput={statusOutput}
          busy={busy}
          checkedAtText={checkedAtText}
          healthColor={healthColor}
          healthText={healthText}
          onCheck={runStatusCheck}
          onOpenStatusModal={() => setStatusModalOpen(true)}
        />
      )
    }
    if (activeProviderTab === 'external') {
      return (
        <ProviderExternalDataTab
          provider={detailProvider}
          externalView={externalView}
          busy={externalViewBusy}
          error={externalViewError}
          onRefresh={refreshExternalView}
        />
      )
    }
    if (activeProviderTab === 'install') {
      return (
        <ProviderInstallGuideTab
          provider={detailProvider}
          setupCommand={data?.setup_command || 'hermes memory setup'}
          statusCommand={data?.status_command || 'hermes memory status'}
          offCommand={data?.off_command || 'hermes memory off'}
        />
      )
    }
    return (
      <ProviderOverviewTab
        provider={detailProvider}
        activeProvider={activeProvider}
        activeHealth={activeHealth}
        statusCommand={data?.status_command || 'hermes memory status'}
        busy={busy}
        readinessText={readinessText}
        healthColor={healthColor}
        healthText={healthText}
        onEnable={() => detailProvider && submit(detailProvider.id)}
        onDisable={() => submit('')}
      />
    )
  }

  return (
    <div className="p-2 h-full" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-solid-block)' }}>
      <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
        <div>
          <div className="uppercase tracking-wider text-[10px] mb-1" style={{ color: 'var(--hud-text-dim)' }}>
            {externalMemoryTitle}
          </div>
          <div className="text-[13px]" style={{ color: activeProvider ? 'var(--hud-primary)' : 'var(--hud-text-dim)' }}>
            {activeProvider ? readinessText(activeProvider) : t('memory.notConfigured')}
          </div>
        </div>
        <div className="font-mono text-[11px]" style={{ color: 'var(--hud-text-dim)' }}>
          {data?.status_command || 'hermes memory status'}
        </div>
      </div>

      <ProviderPicker
        providers={providers}
        selectedId={selectedProviderId}
        activeId={active}
        busy={busy}
        onSelect={setSelected}
        readinessText={readinessText}
      />

      <div className="flex flex-wrap gap-1.5 my-3">
        {providerConsoleTabs.map(tab => {
          const activeTab = activeProviderTab === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => setActiveProviderTab(tab.id)}
              className="px-2 py-1 text-[12px] cursor-pointer"
              style={{
                background: activeTab ? 'var(--hud-primary)' : 'var(--hud-bg-hover)',
                color: activeTab ? 'var(--hud-bg-deep)' : 'var(--hud-text)',
                border: '1px solid var(--hud-border)',
              }}
              type="button"
            >
              {t(tab.labelKey)}
            </button>
          )
        })}
      </div>

      <div className="text-[13px]">
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="font-bold" style={{ color: 'var(--hud-primary)' }}>
            {detailProvider?.label || t('memory.selectProvider')}
          </span>
          {detailProvider && (
            <span style={{ color: 'var(--hud-text-dim)' }}>
              {t('memory.storage')}: {detailProvider.storage}
            </span>
          )}
          {detailProvider && (
            <span style={{ color: detailProvider.configured ? 'var(--hud-success)' : 'var(--hud-warning)' }}>
              {readinessText(detailProvider)}
            </span>
          )}
        </div>

        {renderProviderTab()}

        {notice && <div className="text-[12px] mt-2" style={{ color: 'var(--hud-success)' }}>{notice}</div>}
        {error && <div className="text-[12px] mt-2" style={{ color: 'var(--hud-error, #f44)' }}>{error}</div>}
      </div>

      {statusModalOpen && statusResult && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0, 0, 0, 0.62)' }}
        >
          <div
            className="w-full max-w-5xl"
            style={{ background: 'var(--hud-solid-block)', border: '1px solid var(--hud-border)' }}
          >
            <div
              className="flex items-center justify-between gap-2 px-3 py-2"
              style={{ borderBottom: '1px solid var(--hud-border)' }}
            >
              <div>
                <div className="uppercase tracking-wider text-[10px]" style={{ color: 'var(--hud-text-dim)' }}>
                  {t('memory.statusOutput')}
                </div>
                <div className="text-[13px]" style={{ color: statusResult.status_command.ok ? 'var(--hud-success)' : 'var(--hud-warning)' }}>
                  {statusResult.status_command.command}
                </div>
              </div>
              <button
                onClick={() => setStatusModalOpen(false)}
                className="px-2 py-1 text-[12px] cursor-pointer"
                style={{ background: 'var(--hud-soft-block)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)' }}
                type="button"
              >
                {t('memory.closeStatusModal')}
              </button>
            </div>
            <pre
              className="text-[12px] whitespace-pre-wrap p-3 overflow-auto"
              style={{
                background: 'var(--hud-soft-block)',
                color: statusResult.status_command.ok ? 'var(--hud-text)' : 'var(--hud-warning)',
                maxHeight: '70vh',
                minHeight: '50vh',
              }}
            >
              {statusOutput}
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}

export default function MemoryPanel() {
  const { t } = useTranslation()
  const { data, isLoading, mutate } = useApi('/memory', 30000)
  const { data: providerData, mutate: mutateProviders } = useApi<MemoryProvidersState>('/memory/providers', 30000)
  const { data: filesData, mutate: mutateFiles } = useApi<MemoryFilesState>('/memory/files', 30000)
  const { data: settingsData, mutate: mutateSettings } = useApi<MemorySettingsState>('/memory/settings', 30000)
  const { data: pendingData, mutate: mutatePending } = useApi<MemoryPendingState>('/memory/pending', 30000)

  if (isLoading && !data) {
    return <Panel title={t('memory.title')}><div className="glow text-[13px] animate-pulse">{t('memory.loading')}</div></Panel>
  }

  const { memory, user } = data
  const files = filesData?.files
  const memoryFile = files?.memory
  const userFile = files?.user
  const refreshMemoryState = () => {
    mutate()
    mutateFiles()
    mutateSettings()
    mutatePending()
  }

  return (
    <>
      <Panel title={t('memory.title')}>
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
          <BuiltinMemoryFileCard
            file={memoryFile}
            title={t('memory.builtinMemoryTitle')}
            onSaved={refreshMemoryState}
          >
            <MemoryEntries entries={memory?.entries || files?.memory?.entries || []} target="memory" onMutate={refreshMemoryState} />
            <AddEntryForm target="memory" onMutate={refreshMemoryState} />
          </BuiltinMemoryFileCard>

          <MemoryProvidersPanel data={providerData} onMutate={mutateProviders} />
        </div>
        <MemoryHistoryPanel onMutate={refreshMemoryState} />
        <MemoryGovernancePanel
          settings={settingsData || filesData?.settings}
          pending={pendingData}
          onSettingsSaved={() => {
            mutateSettings()
            mutateFiles()
          }}
          onPendingMutate={refreshMemoryState}
        />
      </Panel>

      <Panel title={t('memory.userProfile')}>
        <div className="grid grid-cols-1 gap-3">
          <BuiltinMemoryFileCard
            file={userFile}
            title={t('memory.userProfile')}
            onSaved={refreshMemoryState}
          >
            <MemoryEntries entries={user?.entries || files?.user?.entries || []} target="user" onMutate={refreshMemoryState} columns={2} />
            <AddEntryForm target="user" onMutate={refreshMemoryState} />
          </BuiltinMemoryFileCard>
        </div>
      </Panel>
    </>
  )
}
