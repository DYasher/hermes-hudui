import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import Panel, { CapacityBar } from './Panel'
import { useTranslation } from '../i18n'

interface MemoryProviderInfo {
  id: string
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
    help: string
  }>
  config_values: Record<string, {
    configured: boolean
    secret: boolean
    source: string
    value: string
  }>
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
  status_command: {
    ok: boolean
    exit_code: number | null
    output: string
    error: string
    command: string
  }
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
  fields: Record<string, string>
): Promise<MemoryProvidersState> {
  const res = await fetch(`/api/memory/providers/${provider}/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fields }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

async function checkMemoryProviderStatus(provider: string): Promise<MemoryProviderCheckResult> {
  const res = await fetch('/api/memory/providers/check', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider }),
  })
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
      style={{ background: 'var(--hud-bg-panel)', borderLeft: '2px solid var(--hud-border)' }}
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
              background: 'var(--hud-bg-deep)',
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
              style={{ background: 'var(--hud-bg-hover)', color: 'var(--hud-text-dim)', border: '1px solid var(--hud-border)' }}
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
          background: 'var(--hud-bg-deep)',
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
          style={{ background: 'var(--hud-bg-hover)', color: 'var(--hud-text-dim)', border: '1px solid var(--hud-border)' }}
        >
          {t('memory.cancel')}
        </button>
      </div>
      {error && <div className="text-[11px] mt-1" style={{ color: 'var(--hud-error, #f44)' }}>{error}</div>}
    </div>
  )
}

function MemoryEntries({ entries, target, onMutate }: { entries: any[]; target: string; onMutate: () => void }) {
  const { t } = useTranslation()
  if (!entries?.length) return <div className="text-[13px]" style={{ color: 'var(--hud-text-dim)' }}>{t('memory.empty')}</div>

  return (
    <div className="space-y-1.5">
      {entries.map((e: any) => (
        <MemoryEntry key={e.text} entry={e} target={target} onMutate={onMutate} />
      ))}
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
  const { t } = useTranslation()
  const [selected, setSelected] = useState('')
  const [configDraft, setConfigDraft] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [statusResult, setStatusResult] = useState<MemoryProviderCheckResult | null>(null)

  const providers = Object.values(data?.providers || {})
  const active = data?.active_provider || ''
  const selectedProvider = providers.find(provider => provider.id === selected)
  const activeProvider = providers.find(provider => provider.id === active)
  const detailProvider = selectedProvider || activeProvider || providers[0]

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
  }, [detailProvider?.id, data?.active_provider])

  const readinessText = (provider?: MemoryProviderInfo) => {
    if (!provider) return t('memory.notConfigured')
    if (provider.readiness === 'ready') return t('memory.verified')
    if (provider.readiness === 'selected') return t('memory.selectedNotVerified')
    if (provider.readiness === 'configured') return t('memory.configured')
    return t('memory.missingConfig')
  }

  const missingConfig = (provider?: MemoryProviderInfo) => {
    if (!provider) return []
    return [
      ...(provider.missing_fields || []),
      ...(provider.missing_any || []).map(group => group.join(' / ')),
    ]
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
    const fields: Record<string, string> = {}
    for (const field of detailProvider.config_fields || []) {
      const value = (configDraft[field.name] || '').trim()
      if (value) fields[field.name] = value
    }
    if (!Object.keys(fields).length) {
      setError(t('memory.noConfigValues'))
      setNotice('')
      return
    }
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await saveMemoryProviderConfig(detailProvider.id, fields)
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
      const result = await checkMemoryProviderStatus(detailProvider.id)
      setStatusResult(result)
      onMutate()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel title={t('memory.providers')} className="col-span-full">
      <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-3">
        <div className="space-y-2 text-[13px]">
          <div className="p-2" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-bg-panel)' }}>
            <div className="uppercase tracking-wider text-[10px] mb-1" style={{ color: 'var(--hud-text-dim)' }}>
              {t('memory.builtin')}
            </div>
            <div style={{ color: 'var(--hud-success)' }}>{t('memory.alwaysOn')}</div>
            <div className="font-mono text-[12px] mt-1" style={{ color: 'var(--hud-text-dim)' }}>
              {(data?.builtin.sources || ['MEMORY.md', 'USER.md']).join(' + ')}
            </div>
          </div>
          <div className="p-2" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-bg-panel)' }}>
            <div className="uppercase tracking-wider text-[10px] mb-1" style={{ color: 'var(--hud-text-dim)' }}>
              {t('memory.externalProvider')}
            </div>
            <div style={{ color: activeProvider ? 'var(--hud-primary)' : 'var(--hud-text-dim)' }}>
              {activeProvider ? activeProvider.label : t('memory.noneExternal')}
            </div>
            <div className="text-[12px] mt-1" style={{ color: activeProvider?.configured ? 'var(--hud-success)' : 'var(--hud-warning)' }}>
              {activeProvider ? readinessText(activeProvider) : t('memory.notConfigured')}
            </div>
            <div className="font-mono text-[12px] mt-1" style={{ color: 'var(--hud-text-dim)' }}>
              {activeProvider ? activeProvider.config_command : data?.setup_command || 'hermes memory setup'}
            </div>
            {active && (
              <button
                onClick={() => submit('')}
                disabled={busy}
                className="mt-2 px-2 py-1 text-[11px] cursor-pointer disabled:opacity-40"
                style={{ background: 'var(--hud-bg-hover)', color: 'var(--hud-warning)', border: '1px solid var(--hud-border)' }}
                type="button"
              >
                {busy ? '...' : t('memory.turnOffExternal')}
              </button>
            )}
          </div>
        </div>

        <div>
          <div className="flex flex-wrap gap-2 mb-3">
            {providers.map(provider => {
              const isSelected = selected === provider.id
              const isActive = provider.active
              return (
                <button
                  key={provider.id}
                  onClick={() => setSelected(provider.id)}
                  disabled={busy}
                  className="px-2 py-1 text-[12px] cursor-pointer disabled:opacity-40"
                  style={{
                    background: isActive || isSelected ? 'var(--hud-primary)' : 'var(--hud-bg-hover)',
                    color: isActive || isSelected ? 'var(--hud-bg-deep)' : 'var(--hud-text)',
                    border: '1px solid var(--hud-border)',
                  }}
                  type="button"
                  title={readinessText(provider)}
                >
                  {provider.label}{provider.configured ? ' *' : ''}
                </button>
              )
            })}
          </div>

          <div className="p-3 text-[13px]" style={{ border: '1px solid var(--hud-border)', background: 'var(--hud-bg-panel)' }}>
            <div className="flex flex-wrap items-center gap-2 mb-2">
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
            <div style={{ color: 'var(--hud-text-dim)' }}>
              {t('memory.oneExternalOnly')}
            </div>
            <div className="font-mono text-[12px] mt-2" style={{ color: 'var(--hud-text-dim)' }}>
              {detailProvider?.config_command || data?.setup_command || 'hermes memory setup'}
            </div>

            {detailProvider && (
              <div className="mt-3">
                <div className="uppercase tracking-wider text-[10px] mb-2" style={{ color: 'var(--hud-text-dim)' }}>
                  {t('memory.configureProvider')}
                </div>
                {detailProvider.config_fields?.length ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    {detailProvider.config_fields.map(field => {
                      const current = detailProvider.config_values?.[field.name]
                      return (
                        <label key={field.name} className="block">
                          <span className="block text-[11px] mb-1" style={{ color: 'var(--hud-text-dim)' }}>
                            {field.label}
                            {field.secret && current?.configured ? ` · ${t('memory.secretConfigured')}` : ''}
                          </span>
                          <input
                            value={configDraft[field.name] ?? ''}
                            type={field.secret ? 'password' : 'text'}
                            onChange={e => setConfigDraft(prev => ({ ...prev, [field.name]: e.target.value }))}
                            placeholder={field.secret && current?.configured ? t('memory.replaceSecret') : field.help}
                            className="w-full text-[12px] px-2 py-1.5 outline-none"
                            style={{
                              background: 'var(--hud-bg-deep)',
                              border: '1px solid var(--hud-border)',
                              color: 'var(--hud-text)',
                            }}
                          />
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
            )}

            {!!missingConfig(detailProvider).length && (
              <div className="mt-3 text-[12px]" style={{ color: 'var(--hud-warning)' }}>
                {t('memory.missingConfig')}: {missingConfig(detailProvider).join(', ')}
              </div>
            )}

            {!!detailProvider?.checks?.length && (
              <div className="mt-3">
                <div className="uppercase tracking-wider text-[10px] mb-1" style={{ color: 'var(--hud-text-dim)' }}>
                  {t('memory.dependencyChecks')}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {detailProvider.checks.map(check => (
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

            {!!detailProvider?.notes?.length && (
              <div className="mt-3 text-[12px] font-mono" style={{ color: 'var(--hud-text-dim)' }}>
                {detailProvider.notes.join(' · ')}
              </div>
            )}

            <div className="flex flex-wrap justify-end gap-2 mt-3">
              <button
                onClick={saveConfig}
                disabled={busy || !detailProvider || !detailProvider.config_fields?.length}
                className="px-3 py-1.5 text-[12px] cursor-pointer disabled:opacity-40"
                style={{ background: 'var(--hud-bg-hover)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)' }}
                type="button"
              >
                {busy ? '...' : t('memory.saveProviderConfig')}
              </button>
              <button
                onClick={runStatusCheck}
                disabled={busy || !detailProvider}
                className="px-3 py-1.5 text-[12px] cursor-pointer disabled:opacity-40"
                style={{ background: 'var(--hud-bg-hover)', color: 'var(--hud-text)', border: '1px solid var(--hud-border)' }}
                type="button"
              >
                {busy ? '...' : t('memory.checkStatus')}
              </button>
              <button
                onClick={() => detailProvider && submit(detailProvider.id)}
                disabled={busy || !detailProvider || detailProvider.id === active}
                className="px-3 py-1.5 text-[12px] cursor-pointer disabled:opacity-40"
                style={{ background: 'var(--hud-primary)', color: 'var(--hud-bg-deep)', border: 'none' }}
                type="button"
              >
                {busy ? '...' : detailProvider?.id === active ? t('memory.activeProvider') : t('memory.setProvider')}
              </button>
            </div>
            {notice && <div className="text-[12px] mt-2" style={{ color: 'var(--hud-success)' }}>{notice}</div>}
            {error && <div className="text-[12px] mt-2" style={{ color: 'var(--hud-error, #f44)' }}>{error}</div>}

            {statusResult && (
              <div className="mt-3">
                <div className="uppercase tracking-wider text-[10px] mb-1" style={{ color: 'var(--hud-text-dim)' }}>
                  {t('memory.statusOutput')}
                </div>
                <pre
                  className="text-[11px] whitespace-pre-wrap p-2 max-h-32 overflow-auto"
                  style={{
                    background: 'var(--hud-bg-deep)',
                    border: '1px solid var(--hud-border)',
                    color: statusResult.status_command.ok ? 'var(--hud-text)' : 'var(--hud-warning)',
                  }}
                >
                  {statusResult.status_command.output || statusResult.status_command.error || t('memory.noStatusOutput')}
                </pre>
              </div>
            )}
          </div>
        </div>
      </div>
    </Panel>
  )
}

export default function MemoryPanel() {
  const { t } = useTranslation()
  const { data, isLoading, mutate } = useApi('/memory', 30000)
  const { data: providerData, mutate: mutateProviders } = useApi<MemoryProvidersState>('/memory/providers', 30000)

  if (isLoading && !data) {
    return <Panel title={t('memory.title')} className="col-span-full"><div className="glow text-[13px] animate-pulse">{t('memory.loading')}</div></Panel>
  }

  const { memory, user } = data

  return (
    <>
      <MemoryProvidersPanel data={providerData} onMutate={mutateProviders} />

      <Panel title={t('memory.title')} className="col-span-1">
        <CapacityBar value={memory?.total_chars || 0} max={memory?.max_chars || 2200} label={t('memory.capacity')} />
        <div className="text-[13px] my-2" style={{ color: 'var(--hud-text-dim)' }}>
          {memory?.entry_count || 0} {t('memory.entries')} · {Object.entries(memory?.count_by_category || {}).map(([k,v]) => `${k}(${v})`).join(' ')}
        </div>
        <MemoryEntries entries={memory?.entries || []} target="memory" onMutate={mutate} />
        <AddEntryForm target="memory" onMutate={mutate} />
      </Panel>

      <Panel title={t('memory.userProfile')} className="col-span-1">
        <CapacityBar value={user?.total_chars || 0} max={user?.max_chars || 1375} label={t('memory.capacity')} />
        <div className="text-[13px] my-2" style={{ color: 'var(--hud-text-dim)' }}>
          {user?.entry_count || 0} {t('memory.entries')}
        </div>
        <MemoryEntries entries={user?.entries || []} target="user" onMutate={mutate} />
        <AddEntryForm target="user" onMutate={mutate} />
      </Panel>
    </>
  )
}
