'use client'

/** §36 masonry gallery + §37 compare + §38 download. */

import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Images, Star, Trash2 } from 'lucide-react'
import { useState } from 'react'

import { api } from '@/lib/api'
import type { Asset, Job } from '@/lib/types'
import { cn, downloadFile, formatRelative, titleCase } from '@/lib/utils'
import { Badge, Button, EmptyState, Modal, Skeleton } from '@/components/ui'
import { useToast } from '@/components/ui/toast'

export default function CreationsPage() {
  const toast = useToast()
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<{ job: Job; asset: Asset } | null>(null)

  const { data, isLoading, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery({
    queryKey: ['creations', 'gallery'],
    queryFn: ({ pageParam }) => api.jobs.creations({ page: pageParam }),
    initialPageParam: 1,
    getNextPageParam: (last) =>
      last.page * last.page_size < last.total ? last.page + 1 : undefined,
  })

  // Flatten every output of every completed job into one gallery stream.
  const cards = (data?.pages ?? []).flatMap((page) =>
    page.items.flatMap((job) => job.outputs.map((asset) => ({ job, asset }))),
  )

  return (
    <div className="mx-auto max-w-7xl">
      <header className="mb-6">
        <h1 className="text-xl font-semibold">Creations</h1>
        <p className="mt-1 text-sm text-ink-muted">Everything you have generated.</p>
      </header>

      {isLoading ? (
        <div className="columns-2 gap-4 sm:columns-3 lg:columns-4">
          {Array.from({ length: 12 }).map((_, i) => (
            <Skeleton key={i} className="mb-4 h-64 w-full" />
          ))}
        </div>
      ) : !cards.length ? (
        <EmptyState
          icon={<Images className="h-8 w-8" />}
          title="Nothing here yet"
          description="Your generated images will appear in this gallery."
        />
      ) : (
        <>
          {/* Masonry via CSS columns — no layout library, no reflow jank. */}
          <div className="columns-2 gap-4 sm:columns-3 lg:columns-4">
            {cards.map(({ job, asset }) => (
              <button
                key={asset.id}
                onClick={() => setSelected({ job, asset })}
                className="group mb-4 block w-full overflow-hidden rounded-xl border border-edge text-left transition hover:border-edge-strong"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={asset.thumbnail_url ?? asset.preview_url ?? ''}
                  alt={asset.filename}
                  className="checkerboard w-full"
                  loading="lazy"
                />
                <div className="flex items-center justify-between gap-2 px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-xs">{titleCase(job.type)}</p>
                    <p className="text-[11px] text-ink-faint">{formatRelative(job.created_at)}</p>
                  </div>
                  {asset.is_favourite && <Star className="h-3.5 w-3.5 fill-current text-warning" />}
                </div>
              </button>
            ))}
          </div>

          {hasNextPage && (
            <div className="mt-6 flex justify-center">
              <Button variant="secondary" loading={isFetchingNextPage} onClick={() => fetchNextPage()}>
                Load more
              </Button>
            </div>
          )}
        </>
      )}

      <Modal
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title={selected ? titleCase(selected.job.type) : ''}
        footer={
          selected && (
            <>
              <Button
                variant="ghost"
                onClick={async () => {
                  await api.assets.remove(selected.asset.id)
                  queryClient.invalidateQueries({ queryKey: ['creations'] })
                  setSelected(null)
                  toast.success('Deleted')
                }}
              >
                <Trash2 className="h-4 w-4" /> Delete
              </Button>
              <Button
                variant="secondary"
                onClick={async () => {
                  await api.assets.update(selected.asset.id, {
                    is_favourite: !selected.asset.is_favourite,
                  })
                  queryClient.invalidateQueries({ queryKey: ['creations'] })
                  toast.success('Updated')
                }}
              >
                <Star className={cn('h-4 w-4', selected.asset.is_favourite && 'fill-current')} />
                Favourite
              </Button>
              <Button
                onClick={async () => {
                  const { url, filename } = await api.assets.downloadUrl(selected.asset.id)
                  downloadFile(url, filename)
                }}
              >
                <Download className="h-4 w-4" /> Download
              </Button>
            </>
          )
        }
      >
        {selected && (
          <div className="space-y-3">
            <div className="checkerboard overflow-hidden rounded-xl border border-edge">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={selected.asset.preview_url ?? selected.asset.url ?? ''}
                alt={selected.asset.filename}
                className="block w-full"
              />
            </div>

            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
              <Detail label="Dimensions" value={`${selected.asset.width}×${selected.asset.height}`} />
              <Detail label="Model" value={selected.asset.ai_model_key ?? '—'} />
              {/* §66/§67 — the parameters that reproduce this exact image. */}
              <Detail label="Seed" value={selected.job.seed !== null ? String(selected.job.seed) : '—'} />
              <Detail label="Created" value={formatRelative(selected.asset.created_at)} />
            </dl>

            {selected.asset.has_watermark && (
              <Badge tone="warning">Watermarked — free plan</Badge>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-ink-faint">{label}</dt>
      <dd className="mt-0.5 font-mono text-ink-muted">{value}</dd>
    </div>
  )
}
