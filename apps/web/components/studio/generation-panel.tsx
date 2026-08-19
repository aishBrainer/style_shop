'use client'

/** §46 live progress + §36 result card + §38 download. */

import { AlertCircle, Download, Loader2, RefreshCw, Star, X } from 'lucide-react'
import { useState } from 'react'

import { api } from '@/lib/api'
import { useJob } from '@/lib/hooks'
import type { Asset, Job } from '@/lib/types'
import { cn, downloadFile, formatDuration } from '@/lib/utils'
import { Badge, Button, EmptyState } from '@/components/ui'
import { useToast } from '@/components/ui/toast'
import { BeforeAfter } from '@/components/before-after'

export function GenerationPanel({
  jobId,
  originalUrl,
  onClear,
}: {
  jobId: string | null
  originalUrl?: string | null
  onClear?: () => void
}) {
  const toast = useToast()
  const { data: job } = useJob(jobId)
  const [compare, setCompare] = useState(false)

  if (!jobId || !job) {
    return (
      <EmptyState
        title="Nothing generated yet"
        description="Set up your inputs on the left, then hit Generate. Results appear here."
      />
    )
  }

  if (job.status === 'failed') return <FailureCard job={job} />
  if (job.status === 'cancelled') {
    return <EmptyState title="Generation cancelled" description="Your credit was refunded." />
  }

  const done = job.status === 'completed'
  if (!done) return <ProgressCard job={job} />

  const primary = job.outputs[0]
  if (!primary) {
    return <EmptyState title="Generation finished" description="No output image was returned." />
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Badge tone="success">Completed</Badge>
          <span className="text-xs text-ink-faint">
            {formatDuration(job.duration_ms)}
            {job.seed !== null && ` · seed ${job.seed}`}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          {originalUrl && (
            <Button size="sm" variant="ghost" onClick={() => setCompare((v) => !v)}>
              {compare ? 'Result' : 'Compare'}
            </Button>
          )}
          {onClear && (
            <Button size="sm" variant="ghost" onClick={onClear} aria-label="Clear result">
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      {compare && originalUrl ? (
        <BeforeAfter before={originalUrl} after={primary.preview_url ?? primary.url ?? ''} />
      ) : (
        <div className="checkerboard overflow-hidden rounded-2xl border border-edge">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={primary.preview_url ?? primary.url ?? ''}
            alt="Generated result"
            className="block w-full"
          />
        </div>
      )}

      {job.outputs.length > 1 && (
        <div className="grid grid-cols-4 gap-2">
          {job.outputs.map((asset) => (
            <ResultThumb key={asset.id} asset={asset} />
          ))}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <Button onClick={() => download(primary, toast)}>
          <Download className="h-4 w-4" /> Download
        </Button>
        <Button variant="secondary" onClick={() => upscale(primary, toast)}>
          Upscale 2x
        </Button>
        <Button
          variant="ghost"
          onClick={async () => {
            await api.assets.update(primary.id, { is_favourite: !primary.is_favourite })
            toast.success(primary.is_favourite ? 'Removed from favourites' : 'Added to favourites')
          }}
        >
          <Star className={cn('h-4 w-4', primary.is_favourite && 'fill-current text-warning')} />
        </Button>
      </div>

      {primary.has_watermark && (
        <p className="text-xs text-ink-faint">
          Free plan downloads include a watermark. Upgrade for clean HD exports.
        </p>
      )}
    </div>
  )
}

function ProgressCard({ job }: { job: Job }) {
  const toast = useToast()

  return (
    <div className="panel p-6">
      <div className="flex items-center gap-3">
        <Loader2 className="h-5 w-5 animate-spin text-accent" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">{job.stage_label ?? 'Working…'}</p>
          <p className="text-xs text-ink-faint">
            {job.status === 'queued' && job.queue_position
              ? `Position #${job.queue_position}`
              : job.estimated_seconds
                ? `About ${job.estimated_seconds}s remaining`
                : 'Estimating…'}
          </p>
        </div>
        <span className="font-mono text-sm text-ink-muted">{job.progress}%</span>
      </div>

      <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-white/10">
        <div
          className="h-full rounded-full bg-accent transition-all duration-500"
          style={{ width: `${Math.max(3, job.progress)}%` }}
        />
      </div>

      <Button
        size="sm"
        variant="ghost"
        className="mt-4"
        onClick={async () => {
          try {
            await api.jobs.cancel(job.id)
            toast.info('Generation cancelled')
          } catch {
            toast.error('Could not cancel — it may have already finished')
          }
        }}
      >
        Cancel
      </Button>
    </div>
  )
}

function FailureCard({ job }: { job: Job }) {
  const toast = useToast()
  const [retrying, setRetrying] = useState(false)

  return (
    <div className="panel border-danger/30 p-6">
      <div className="flex items-start gap-3">
        <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-danger" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">Generation failed</p>
          {/* §64 — this is the user-safe message the API produced, never a traceback. */}
          <p className="mt-1 text-sm text-ink-muted">
            {job.error_message ?? 'Something went wrong. Please try again.'}
          </p>
          {job.credits_cost > 0 && (
            <p className="mt-2 text-xs text-ink-faint">
              {job.credits_cost} credit{job.credits_cost === 1 ? '' : 's'} refunded.
            </p>
          )}
        </div>
      </div>

      <Button
        size="sm"
        variant="secondary"
        className="mt-4"
        loading={retrying}
        onClick={async () => {
          setRetrying(true)
          try {
            await api.jobs.retry(job.id)
            toast.info('Retrying')
          } catch (err) {
            toast.error('Could not retry this generation')
          } finally {
            setRetrying(false)
          }
        }}
      >
        <RefreshCw className="h-3.5 w-3.5" /> Try again
      </Button>
    </div>
  )
}

function ResultThumb({ asset }: { asset: Asset }) {
  return (
    <div className="checkerboard overflow-hidden rounded-lg border border-edge">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={asset.thumbnail_url ?? asset.preview_url ?? ''}
        alt={asset.filename}
        className="aspect-square w-full object-cover"
        loading="lazy"
      />
    </div>
  )
}

async function download(asset: Asset, toast: ReturnType<typeof useToast>) {
  try {
    // §97 — the bytes come straight from storage via a signed URL; they never
    // stream through the API.
    const { url, filename } = await api.assets.downloadUrl(asset.id, 'original')
    downloadFile(url, filename)
  } catch {
    toast.error('Download failed')
  }
}

async function upscale(asset: Asset, toast: ReturnType<typeof useToast>) {
  try {
    await api.generate.upscale({ image_asset_id: asset.id, scale: 2 })
    toast.success('Upscale queued', 'It will appear in Creations when ready.')
  } catch {
    toast.error('Could not queue the upscale')
  }
}
