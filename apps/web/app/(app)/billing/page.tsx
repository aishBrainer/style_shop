'use client'

/** §40 credits + §41 usage. Billing itself is inactive — the ledger is not. */

import { useQuery } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { useSession } from '@/lib/hooks'
import { formatBytes, formatRelative, titleCase } from '@/lib/utils'
import { Badge, Card, Skeleton } from '@/components/ui'

interface CreditTransaction {
  id: string
  amount: number
  balance_after: number
  reason: string
  description: string | null
  created_at: string
}

export default function BillingPage() {
  const { data: session } = useSession()

  const { data: credits, isLoading } = useQuery({
    queryKey: ['credits'],
    queryFn: () => api.studio.credits(),
  })

  const { data: usage } = useQuery({
    queryKey: ['usage', 30],
    queryFn: () => api.studio.usage(30),
  })

  const transactions = (credits?.transactions ?? []) as CreditTransaction[]
  const org = session?.organization

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Billing &amp; usage</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Credits, storage and generation history for this workspace.
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <p className="text-xs uppercase tracking-wider text-ink-faint">Credits</p>
          <p className="mt-2 text-3xl font-semibold">{org?.credit_balance ?? '—'}</p>
          <Badge tone="accent" className="mt-2 capitalize">{org?.plan ?? ''} plan</Badge>
        </Card>

        <Card>
          <p className="text-xs uppercase tracking-wider text-ink-faint">Used (30d)</p>
          <p className="mt-2 text-3xl font-semibold">{credits?.consumed_30d ?? '—'}</p>
          <p className="mt-2 text-xs text-ink-faint">{credits?.granted_30d ?? 0} granted</p>
        </Card>

        <Card>
          <p className="text-xs uppercase tracking-wider text-ink-faint">Storage</p>
          <p className="mt-2 text-3xl font-semibold">
            {org ? formatBytes(org.storage_used_bytes) : '—'}
          </p>
          {org && (
            <>
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full rounded-full bg-accent"
                  style={{
                    width: `${Math.min(
                      100,
                      (org.storage_used_bytes / (org.storage_quota_mb * 1024 * 1024)) * 100,
                    )}%`,
                  }}
                />
              </div>
              <p className="mt-1.5 text-xs text-ink-faint">
                of {(org.storage_quota_mb / 1024).toFixed(0)} GB
              </p>
            </>
          )}
        </Card>
      </div>

      {usage && (
        <Card>
          <h2 className="text-sm font-medium">Last 30 days</h2>
          <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Metric label="Generations" value={String(usage.generations_total ?? 0)} />
            <Metric label="Succeeded" value={String(usage.generations_succeeded ?? 0)} />
            <Metric label="Failed" value={String(usage.generations_failed ?? 0)} />
            <Metric
              label="Avg time"
              value={
                usage.avg_duration_ms
                  ? `${((usage.avg_duration_ms as number) / 1000).toFixed(1)}s`
                  : '—'
              }
            />
          </dl>
        </Card>
      )}

      <Card>
        <h2 className="text-sm font-medium">Credit history</h2>

        {isLoading ? (
          <div className="mt-4 space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-10" />
            ))}
          </div>
        ) : !transactions.length ? (
          <p className="mt-4 text-sm text-ink-muted">No transactions yet.</p>
        ) : (
          <ul className="mt-4 divide-y divide-edge">
            {transactions.map((tx) => (
              <li key={tx.id} className="flex items-center justify-between gap-4 py-2.5">
                <div className="min-w-0">
                  <p className="truncate text-sm">
                    {tx.description ?? titleCase(tx.reason)}
                  </p>
                  <p className="text-[11px] text-ink-faint">{formatRelative(tx.created_at)}</p>
                </div>
                <div className="text-right">
                  <p
                    className={
                      tx.amount > 0 ? 'text-sm text-success' : 'text-sm text-ink-muted'
                    }
                  >
                    {tx.amount > 0 ? '+' : ''}
                    {tx.amount}
                  </p>
                  <p className="text-[11px] text-ink-faint">{tx.balance_after} left</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <p className="text-xs text-ink-faint">
        Paid plans are not active yet. Credits are granted monthly and refunded automatically
        whenever a generation fails.
      </p>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-ink-faint">{label}</dt>
      <dd className="mt-1 text-xl font-semibold">{value}</dd>
    </div>
  )
}
