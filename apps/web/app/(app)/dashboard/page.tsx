'use client'

import { useQuery } from '@tanstack/react-query'
import Link from 'next/link'
import {
  ArrowRight,
  Image as ImageIcon,
  Layers,
  Shirt,
  Sparkles,
  Wand2,
} from 'lucide-react'

import { api } from '@/lib/api'
import { useSession } from '@/lib/hooks'
import { formatBytes, formatRelative } from '@/lib/utils'
import { Badge, Card, EmptyState, Skeleton } from '@/components/ui'

const TOOLS = [
  { href: '/studio/vton', icon: Shirt, title: 'Virtual Try-On', body: 'Garment onto a model.' },
  { href: '/studio/photography', icon: ImageIcon, title: 'Product Photography', body: 'Studio packshots.' },
  { href: '/studio/background', icon: Layers, title: 'Background Studio', body: 'Remove or replace.' },
  { href: '/studio/editor', icon: Wand2, title: 'Image Editor', body: 'Retouch, expand, upscale.' },
]

export default function DashboardPage() {
  const { data: session } = useSession()

  const { data: usage } = useQuery({
    queryKey: ['usage'],
    queryFn: () => api.studio.usage(30),
  })

  const { data: creations, isLoading } = useQuery({
    queryKey: ['creations', { page: 1 }],
    queryFn: () => api.jobs.creations({ page: 1 }),
  })

  const firstName = session?.user.full_name?.split(' ')[0]

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <header>
        <h1 className="text-xl font-semibold">
          {firstName ? `Welcome back, ${firstName}` : 'Welcome back'}
        </h1>
        <p className="mt-1 text-sm text-ink-muted">
          Pick a tool and turn a product photo into something you can sell with.
        </p>
      </header>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {TOOLS.map(({ href, icon: Icon, title, body }) => (
          <Link key={href} href={href}>
            <Card className="group h-full transition hover:border-edge-strong hover:bg-canvas-overlay">
              <div className="mb-3 inline-flex rounded-xl bg-accent-muted p-2.5 text-accent">
                <Icon className="h-5 w-5" />
              </div>
              <h2 className="flex items-center gap-1.5 text-sm font-medium">
                {title}
                <ArrowRight className="h-3.5 w-3.5 opacity-0 transition group-hover:translate-x-0.5 group-hover:opacity-100" />
              </h2>
              <p className="mt-1 text-sm text-ink-muted">{body}</p>
            </Card>
          </Link>
        ))}
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Credits"
          value={String(session?.organization.credit_balance ?? '—')}
          hint={`${session?.organization.plan ?? ''} plan`}
        />
        <Stat
          label="Generations"
          value={String(usage?.generations_total ?? '—')}
          hint="Last 30 days"
        />
        <Stat
          label="Success rate"
          value={
            typeof usage?.success_rate === 'number'
              ? `${Math.round((usage.success_rate as number) * 100)}%`
              : '—'
          }
          hint="Completed vs started"
        />
        <Stat
          label="Storage"
          value={
            session ? formatBytes(session.organization.storage_used_bytes) : '—'
          }
          hint={session ? `of ${session.organization.storage_quota_mb / 1024} GB` : ''}
        />
      </section>

      <section>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-medium">Recent creations</h2>
          <Link href="/creations" className="text-xs text-accent transition hover:text-accent-hover">
            View all
          </Link>
        </div>

        {isLoading ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="aspect-square" />
            ))}
          </div>
        ) : !creations?.items.length ? (
          <EmptyState
            icon={<Sparkles className="h-8 w-8" />}
            title="No creations yet"
            description="Start with Virtual Try-On — upload a garment and pick a model."
            action={
              <Link href="/studio/vton" className="text-sm text-accent hover:text-accent-hover">
                Open the studio →
              </Link>
            }
          />
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
            {creations.items.slice(0, 12).map((job) => {
              const asset = job.outputs[0]
              if (!asset) return null
              return (
                <Link
                  key={job.id}
                  href={`/creations?job=${job.id}`}
                  className="group overflow-hidden rounded-xl border border-edge transition hover:border-edge-strong"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={asset.thumbnail_url ?? asset.preview_url ?? ''}
                    alt={asset.filename}
                    className="checkerboard aspect-square w-full object-cover"
                    loading="lazy"
                  />
                  <div className="px-2.5 py-2">
                    <p className="truncate text-[11px] text-ink-muted">
                      {job.type.replace(/_/g, ' ')}
                    </p>
                    <p className="text-[11px] text-ink-faint">{formatRelative(job.created_at)}</p>
                  </div>
                </Link>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card>
      <p className="text-xs uppercase tracking-wider text-ink-faint">{label}</p>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
      {hint && <p className="mt-0.5 text-xs capitalize text-ink-faint">{hint}</p>}
    </Card>
  )
}
