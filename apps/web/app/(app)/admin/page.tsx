'use client'

/** §63 admin dashboard: stats, GPU workers, model registry, jobs, flags. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Cpu, ShieldCheck } from 'lucide-react'
import { useState } from 'react'

import { ApiError, api } from '@/lib/api'
import { cn, formatBytes, formatRelative, titleCase } from '@/lib/utils'
import { Badge, Button, Card, Skeleton, Switch } from '@/components/ui'
import { useToast } from '@/components/ui/toast'

type Tab = 'overview' | 'workers' | 'models' | 'jobs' | 'flags'

const TABS: { key: Tab; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'workers', label: 'GPU workers' },
  { key: 'models', label: 'AI models' },
  { key: 'jobs', label: 'Failed jobs' },
  { key: 'flags', label: 'Feature flags' },
]

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>('overview')

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6">
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <ShieldCheck className="h-5 w-5 text-accent" /> Admin
        </h1>
        <p className="mt-1 text-sm text-ink-muted">Platform health and configuration.</p>
      </header>

      <div className="mb-6 flex flex-wrap gap-1.5 rounded-xl border border-edge bg-canvas-raised p-1">
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={cn(
              'rounded-lg px-3 py-2 text-xs font-medium transition',
              tab === key ? 'bg-accent-muted text-accent' : 'text-ink-muted hover:text-ink',
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'overview' && <Overview />}
      {tab === 'workers' && <Workers />}
      {tab === 'models' && <Models />}
      {tab === 'jobs' && <FailedJobs />}
      {tab === 'flags' && <Flags />}
    </div>
  )
}

function Overview() {
  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'stats'],
    queryFn: () => api.admin.stats(),
    refetchInterval: 30_000,
  })

  if (isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
    )
  }

  const queues = (data?.queue_depths ?? {}) as Record<string, number>

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Users" value={String(data?.users_total ?? 0)} hint={`${data?.users_active_30d ?? 0} active`} />
        <Stat label="Organizations" value={String(data?.organizations_total ?? 0)} />
        <Stat label="Jobs today" value={String(data?.jobs_today ?? 0)} hint={`${data?.jobs_failed_today ?? 0} failed`} />
        <Stat
          label="Success rate"
          value={`${Math.round(((data?.success_rate as number) ?? 0) * 100)}%`}
          hint="All time"
        />
        <Stat label="In progress" value={String(data?.jobs_in_progress ?? 0)} />
        <Stat
          label="Avg duration"
          value={data?.avg_duration_ms ? `${(((data.avg_duration_ms as number) / 1000)).toFixed(1)}s` : '—'}
        />
        <Stat label="Storage" value={formatBytes((data?.storage_bytes as number) ?? 0)} />
        <Stat label="Credits today" value={String(data?.credits_consumed_today ?? 0)} />
      </div>

      <Card>
        <h2 className="text-sm font-medium">Queue depth</h2>
        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
          {Object.entries(queues).map(([queue, depth]) => (
            <div key={queue}>
              <p className="text-xs uppercase tracking-wider text-ink-faint">{queue}</p>
              <p className={cn('mt-1 text-xl font-semibold', depth > 20 && 'text-warning')}>
                {depth}
              </p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}

function Workers() {
  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'workers'],
    queryFn: () => api.admin.workers(),
    refetchInterval: 15_000,
  })

  if (isLoading) return <Skeleton className="h-40" />
  if (!data?.length) {
    return (
      <Card>
        <p className="text-sm text-ink-muted">
          No workers have reported in. Start them with{' '}
          <code className="text-accent">docker compose up worker-vton worker-image worker-cpu</code>.
        </p>
      </Card>
    )
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {data.map((worker) => {
        const vramTotal = worker.vram_total_mb as number | null
        const vramUsed = worker.vram_used_mb as number | null
        const online = worker.online as boolean

        return (
          <Card key={worker.worker_name as string}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="flex items-center gap-2 truncate text-sm font-medium">
                  <Cpu className="h-4 w-4 shrink-0 text-accent" />
                  {worker.worker_name as string}
                </p>
                <p className="mt-0.5 text-xs text-ink-faint">
                  {(worker.queues as string[] | null)?.join(', ') || 'no queues'} ·{' '}
                  {(worker.device as string) ?? 'cpu'}
                </p>
              </div>
              <Badge tone={online ? 'success' : 'danger'}>{online ? 'Online' : 'Offline'}</Badge>
            </div>

            {worker.gpu_name ? (
              <div className="mt-4">
                <p className="text-xs text-ink-muted">{worker.gpu_name as string}</p>
                {vramTotal && vramUsed !== null && (
                  <>
                    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
                      <div
                        className="h-full rounded-full bg-accent"
                        style={{ width: `${(vramUsed / vramTotal) * 100}%` }}
                      />
                    </div>
                    <p className="mt-1.5 text-xs text-ink-faint">
                      VRAM {(vramUsed / 1024).toFixed(1)} / {(vramTotal / 1024).toFixed(1)} GB
                      {worker.gpu_utilization !== null &&
                        ` · ${worker.gpu_utilization as number}% utilisation`}
                    </p>
                  </>
                )}
              </div>
            ) : (
              <p className="mt-4 text-xs text-ink-faint">CPU worker — no GPU attached.</p>
            )}

            <p className="mt-3 text-[11px] text-ink-faint">
              Models: {(worker.loaded_models as string[] | null)?.join(', ') || 'none loaded'}
            </p>
            <p className="text-[11px] text-ink-faint">
              Last seen {formatRelative(worker.last_seen_at as string)}
            </p>
          </Card>
        )
      })}
    </div>
  )
}

function Models() {
  const toast = useToast()
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'models'],
    queryFn: () => api.admin.models(),
  })

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      api.admin.toggleModel(id, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'models'] })
      toast.success('Model updated')
    },
    // §72 — the API refuses to enable a non-commercial checkpoint. Surface
    // that reason verbatim; it is the whole point of the guard.
    onError: (err) =>
      toast.error(
        'Cannot enable this model',
        err instanceof ApiError ? err.message : undefined,
      ),
  })

  if (isLoading) return <Skeleton className="h-64" />

  return (
    <div className="space-y-3">
      {data?.map((model) => {
        const commercial = model.commercial_use as string
        const blocked = commercial !== 'allowed'

        return (
          <Card key={model.id as string}>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <p className="flex items-center gap-2 text-sm font-medium">
                  {model.name as string}
                  <Badge>{titleCase(model.type as string)}</Badge>
                </p>
                <p className="mt-1 text-xs text-ink-faint">
                  key: {model.key as string} · v{model.version as string} ·{' '}
                  {model.framework as string}
                  {model.vram_requirement_mb
                    ? ` · ${((model.vram_requirement_mb as number) / 1024).toFixed(1)} GB VRAM`
                    : ''}
                </p>

                <div className="mt-2.5 flex flex-wrap items-center gap-2">
                  <Badge tone={blocked ? 'danger' : 'success'}>
                    {blocked && <AlertTriangle className="h-3 w-3" />}
                    {model.license as string}
                  </Badge>
                  <span className="text-[11px] text-ink-faint">
                    Commercial use: {titleCase(commercial)}
                  </span>
                </div>

                {model.license_notes ? (
                  <p className="mt-2 max-w-xl text-xs text-ink-muted">
                    {model.license_notes as string}
                  </p>
                ) : null}
              </div>

              <div className="shrink-0">
                <Switch
                  checked={model.enabled as boolean}
                  onChange={(enabled) =>
                    toggle.mutate({ id: model.id as string, enabled })
                  }
                  label={model.enabled ? 'Enabled' : 'Disabled'}
                />
              </div>
            </div>
          </Card>
        )
      })}
    </div>
  )
}

function FailedJobs() {
  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'jobs', 'failed'],
    queryFn: () => api.admin.jobs({ failed_only: true, page_size: 50 }),
    refetchInterval: 30_000,
  })

  if (isLoading) return <Skeleton className="h-64" />
  if (!data?.items.length) {
    return (
      <Card>
        <p className="text-sm text-ink-muted">No failed jobs. That is a good sign.</p>
      </Card>
    )
  }

  return (
    <Card className="!p-0">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-edge text-left text-xs uppercase tracking-wider text-ink-faint">
            <tr>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Error</th>
              <th className="px-4 py-3">Worker</th>
              <th className="px-4 py-3">Retries</th>
              <th className="px-4 py-3">When</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-edge">
            {data.items.map((job) => (
              <tr key={job.id as string}>
                <td className="px-4 py-3">{titleCase(job.type as string)}</td>
                <td className="px-4 py-3">
                  <Badge tone="danger">{job.error_code as string}</Badge>
                  <p className="mt-1 max-w-md truncate text-xs text-ink-muted">
                    {job.error_message as string}
                  </p>
                </td>
                <td className="px-4 py-3 text-xs text-ink-muted">
                  {(job.worker_name as string) ?? '—'}
                </td>
                <td className="px-4 py-3 text-xs">{job.retry_count as number}</td>
                <td className="px-4 py-3 text-xs text-ink-faint">
                  {formatRelative(job.created_at as string)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function Flags() {
  const toast = useToast()
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'flags'],
    queryFn: () => api.admin.flags(),
  })

  const update = useMutation({
    mutationFn: ({ key, enabled }: { key: string; enabled: boolean }) =>
      api.admin.updateFlag(key, { enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'flags'] })
      toast.success('Flag updated')
    },
  })

  if (isLoading) return <Skeleton className="h-64" />

  return (
    <Card className="space-y-4">
      {data?.map((flag) => (
        <Switch
          key={flag.key as string}
          checked={flag.enabled as boolean}
          onChange={(enabled) => update.mutate({ key: flag.key as string, enabled })}
          label={flag.key as string}
          hint={(flag.description as string) ?? undefined}
        />
      ))}
    </Card>
  )
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card>
      <p className="text-xs uppercase tracking-wider text-ink-faint">{label}</p>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-ink-faint">{hint}</p>}
    </Card>
  )
}
