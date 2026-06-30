import { useApi } from '../hooks/useApi'
import { useTranslation } from '../i18n'
import Panel from './Panel'

type SafetyStatus = 'ok' | 'warning' | 'blocked'

type SafetyCheck = {
  name: string
  status: SafetyStatus
  detail: string
  recommendation?: string
  evidence?: string[]
}

type RuntimeSurface = {
  path: string
  present: boolean
  status: SafetyStatus
  policy: string
  detail: string
}

type OperationPolicy = {
  name: string
  policy: string
  status: SafetyStatus
  detail: string
}

type SafetyMatch = {
  rule: string
  kind: string
  field: string
  redacted_value: string
  severity: string
}

type SafetyState = {
  hermes_dir: string
  hermes_dir_exists: boolean
  environment_class: string
  write_policy: string
  ok_count: number
  warning_count: number
  blocked_count: number
  sensitive_present_count: number
  checks: SafetyCheck[]
  runtime_surface: RuntimeSurface[]
  operation_policies: OperationPolicy[]
  prod_matches: SafetyMatch[]
}

const STATUS_COLOR: Record<SafetyStatus, string> = {
  ok: 'var(--hud-success)',
  warning: 'var(--hud-warning)',
  blocked: 'var(--hud-error)',
}

function statusLabel(status: SafetyStatus) {
  if (status === 'ok') return 'OK'
  if (status === 'warning') return 'WARN'
  return 'BLOCK'
}

function StatusBadge({ status }: { status: SafetyStatus }) {
  return (
    <span className="text-[11px] font-bold uppercase" style={{ color: STATUS_COLOR[status] }}>
      {statusLabel(status)}
    </span>
  )
}

function CheckList({ items }: { items: SafetyCheck[] }) {
  if (!items.length) return <div className="text-[13px]" style={{ color: 'var(--hud-text-dim)' }}>-</div>
  return (
    <div className="space-y-2">
      {items.map((item) => (
        <div key={item.name} className="py-1.5" style={{ borderBottom: '1px solid var(--hud-border)' }}>
          <div className="flex items-start justify-between gap-3 text-[13px]">
            <div className="min-w-0">
              <div>{item.name}</div>
              <div className="text-[11px]" style={{ color: 'var(--hud-text-dim)' }}>{item.detail}</div>
            </div>
            <StatusBadge status={item.status} />
          </div>
          {item.recommendation && (
            <div className="mt-1 text-[11px]" style={{ color: 'var(--hud-primary)' }}>
              {item.recommendation}
            </div>
          )}
          {item.evidence && item.evidence.length > 0 && (
            <div className="mt-1 text-[11px] truncate" style={{ color: 'var(--hud-text-dim)' }}>
              {item.evidence.join(' · ')}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export default function SafetyPanel() {
  const { t } = useTranslation()
  const { data, isLoading } = useApi<SafetyState>('/safety', 30000)

  if (isLoading && !data) {
    return <Panel title={t('safety.title')} className="col-span-full"><div className="glow text-[13px] animate-pulse">{t('safety.loading')}</div></Panel>
  }
  if (!data) {
    return <Panel title={t('safety.title')} className="col-span-full"><div className="text-[13px]" style={{ color: 'var(--hud-text-dim)' }}>{t('safety.unavailable')}</div></Panel>
  }

  return (
    <>
      <Panel title={t('safety.posture')} className="col-span-full">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-[13px]">
          {[
            [t('safety.environment'), data.environment_class, data.environment_class === 'prod_like' ? 'var(--hud-error)' : 'var(--hud-primary)'],
            [t('safety.writePolicy'), data.write_policy, data.write_policy === 'blocked' ? 'var(--hud-error)' : 'var(--hud-warning)'],
            [t('safety.ok'), data.ok_count, 'var(--hud-success)'],
            [t('safety.warnings'), data.warning_count, 'var(--hud-warning)'],
            [t('safety.blocked'), data.blocked_count, 'var(--hud-error)'],
          ].map(([label, value, color]) => (
            <div key={String(label)} className="py-2 px-2 border" style={{ borderColor: 'var(--hud-border)' }}>
              <div className="text-[11px] uppercase tracking-widest" style={{ color: 'var(--hud-text-dim)' }}>{label}</div>
              <div className="font-bold truncate" style={{ color: String(color) }}>{value}</div>
            </div>
          ))}
        </div>
        <div className="mt-3 text-[12px] min-w-0">
          <span style={{ color: 'var(--hud-text-dim)' }}>{t('safety.hermesHome')}:</span>{' '}
          <span className="break-all">{data.hermes_dir}</span>
        </div>
      </Panel>

      <Panel title={t('safety.guardrails')} className="col-span-full lg:col-span-1">
        <CheckList items={data.checks} />
      </Panel>

      <Panel title={t('safety.operations')} className="col-span-full lg:col-span-1">
        <div className="space-y-2">
          {data.operation_policies.map((item) => (
            <div key={item.name} className="py-1.5" style={{ borderBottom: '1px solid var(--hud-border)' }}>
              <div className="flex items-start justify-between gap-3 text-[13px]">
                <div className="min-w-0">
                  <div>{item.name}</div>
                  <div className="text-[11px]" style={{ color: 'var(--hud-primary)' }}>{item.policy}</div>
                </div>
                <StatusBadge status={item.status} />
              </div>
              <div className="mt-1 text-[11px]" style={{ color: 'var(--hud-text-dim)' }}>{item.detail}</div>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title={t('safety.runtimeSurface')} className="col-span-full">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-1 text-[12px]">
          {data.runtime_surface.map((item) => (
            <div key={item.path} className="flex items-start justify-between gap-3 py-1" style={{ borderBottom: '1px solid var(--hud-border)' }}>
              <div className="min-w-0">
                <div className="font-mono truncate">{item.path}</div>
                <div className="text-[11px]" style={{ color: 'var(--hud-text-dim)' }}>
                  {item.present ? item.policy : t('safety.notPresent')} · {item.detail}
                </div>
              </div>
              <span className="text-[11px] shrink-0" style={{ color: item.present ? 'var(--hud-warning)' : 'var(--hud-text-dim)' }}>
                {item.present ? t('safety.present') : t('safety.absent')}
              </span>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title={t('safety.prodMatches')} className="col-span-full">
        {data.prod_matches.length === 0 ? (
          <div className="text-[13px]" style={{ color: 'var(--hud-text-dim)' }}>{t('safety.noProdMatches')}</div>
        ) : (
          <div className="space-y-1 text-[12px]">
            {data.prod_matches.map((match, index) => (
              <div key={`${match.rule}:${match.field}:${index}`} className="flex flex-wrap items-center gap-2 py-1" style={{ borderBottom: '1px solid var(--hud-border)' }}>
                <span className="font-bold" style={{ color: 'var(--hud-error)' }}>{match.rule}</span>
                <span style={{ color: 'var(--hud-text-dim)' }}>{match.kind}</span>
                <span>{match.field}</span>
                <span className="font-mono" style={{ color: 'var(--hud-text-dim)' }}>{match.redacted_value}</span>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </>
  )
}
