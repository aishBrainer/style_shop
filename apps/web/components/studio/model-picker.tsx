'use client'

/** §11 model library + §12 custom upload, in one picker. */

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Check, Upload, Users } from 'lucide-react'
import { useState } from 'react'

import { api } from '@/lib/api'
import type { Asset, ModelProfile } from '@/lib/types'
import { cn, titleCase } from '@/lib/utils'
import { Button, EmptyState, Select, Skeleton } from '@/components/ui'
import { useToast } from '@/components/ui/toast'
import { UploadZone } from './upload-zone'

type Filters = { gender?: string; body_type?: string; pose?: string; custom_only?: boolean }

export function ModelPicker({
  value,
  onChange,
  filterOptions,
}: {
  value: ModelProfile | null
  onChange: (model: ModelProfile | null) => void
  filterOptions?: Record<string, string[]>
}) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const [filters, setFilters] = useState<Filters>({})
  const [uploading, setUploading] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['models', filters],
    queryFn: () => api.models.list({ ...filters, page_size: 40 }),
  })

  async function handleCustomUpload(asset: Asset | null) {
    if (!asset) return
    try {
      const profile = await api.models.create({
        name: asset.filename.replace(/\.[^.]+$/, ''),
        image_asset_id: asset.id,
      })
      // §12: the profile is created inactive and a CPU job validates the photo.
      // Selecting it now would produce a confusing rejection at generate time.
      toast.info(
        'Checking your model photo',
        'We are validating framing and focus. It will appear in the library shortly.',
      )
      queryClient.invalidateQueries({ queryKey: ['models'] })
      setUploading(false)
    } catch {
      toast.error('Could not add that model')
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Select
          className="h-8 w-auto py-1 text-xs"
          value={filters.gender ?? ''}
          onChange={(e) => setFilters((f) => ({ ...f, gender: e.target.value || undefined }))}
        >
          <option value="">Any gender</option>
          {(filterOptions?.gender ?? []).map((v) => (
            <option key={v} value={v}>{titleCase(v)}</option>
          ))}
        </Select>

        <Select
          className="h-8 w-auto py-1 text-xs"
          value={filters.body_type ?? ''}
          onChange={(e) => setFilters((f) => ({ ...f, body_type: e.target.value || undefined }))}
        >
          <option value="">Any body type</option>
          {(filterOptions?.body_type ?? []).map((v) => (
            <option key={v} value={v}>{titleCase(v)}</option>
          ))}
        </Select>

        <Select
          className="h-8 w-auto py-1 text-xs"
          value={filters.pose ?? ''}
          onChange={(e) => setFilters((f) => ({ ...f, pose: e.target.value || undefined }))}
        >
          <option value="">Any pose</option>
          {(filterOptions?.pose ?? []).map((v) => (
            <option key={v} value={v}>{titleCase(v)}</option>
          ))}
        </Select>

        <button
          onClick={() => setFilters((f) => ({ ...f, custom_only: !f.custom_only }))}
          className={cn(
            'h-8 rounded-xl border px-3 text-xs transition',
            filters.custom_only
              ? 'border-accent/40 bg-accent-muted text-accent'
              : 'border-edge text-ink-muted hover:text-ink',
          )}
        >
          My models
        </button>

        <Button size="sm" variant="secondary" className="ml-auto" onClick={() => setUploading((v) => !v)}>
          <Upload className="h-3.5 w-3.5" /> Upload
        </Button>
      </div>

      {uploading && (
        <div className="rounded-xl border border-edge bg-canvas p-3">
          <UploadZone
            label="Upload a model photo"
            assetType="model"
            value={null}
            onChange={handleCustomUpload}
            className="max-w-xs"
          />
          <p className="mt-2 text-xs text-ink-faint">
            Use a full-body or 3/4-body image with the subject clearly visible.
          </p>
        </div>
      )}

      {isLoading ? (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="aspect-[3/4]" />
          ))}
        </div>
      ) : !data?.items.length ? (
        <EmptyState
          icon={<Users className="h-8 w-8" />}
          title="No models match these filters"
          description="Clear a filter, or upload your own model photo."
        />
      ) : (
        <div className="grid max-h-[420px] grid-cols-3 gap-2 overflow-y-auto sm:grid-cols-4">
          {data.items.map((model) => {
            const selected = value?.id === model.id
            const warning = model.validation && model.validation.acceptable === false

            return (
              <button
                key={model.id}
                onClick={() => onChange(selected ? null : model)}
                className={cn(
                  'group relative overflow-hidden rounded-xl border transition',
                  selected ? 'border-accent shadow-glow' : 'border-edge hover:border-edge-strong',
                )}
                title={warning ? model.validation?.message ?? undefined : model.name}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={model.image?.thumbnail_url ?? model.image?.preview_url ?? ''}
                  alt={model.name}
                  className="aspect-[3/4] w-full object-cover"
                  loading="lazy"
                />

                {selected && (
                  <span className="absolute right-1.5 top-1.5 grid h-5 w-5 place-items-center rounded-full bg-accent text-white">
                    <Check className="h-3 w-3" />
                  </span>
                )}

                {warning && (
                  <span className="absolute left-1.5 top-1.5 grid h-5 w-5 place-items-center rounded-full bg-warning/90 text-black">
                    <AlertTriangle className="h-3 w-3" />
                  </span>
                )}

                <span className="absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/85 to-transparent px-2 pb-1.5 pt-5 text-left text-[11px]">
                  {model.name}
                </span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
