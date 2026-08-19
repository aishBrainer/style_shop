'use client'

import { ImagePlus, Loader2, X } from 'lucide-react'
import { useCallback, useState } from 'react'
import { useDropzone, type FileRejection } from 'react-dropzone'

import { ApiError, api } from '@/lib/api'
import type { Asset, AssetType } from '@/lib/types'
import { cn, formatBytes } from '@/lib/utils'

const MAX_MB = Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_MB ?? 20)
const ACCEPT = {
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/png': ['.png'],
  'image/webp': ['.webp'],
}

export function UploadZone({
  label,
  assetType = 'product',
  projectId,
  value,
  onChange,
  className,
}: {
  label: string
  assetType?: AssetType
  projectId?: string
  value: Asset | null
  onChange: (asset: Asset | null) => void
  className?: string
}) {
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const onDrop = useCallback(
    async (accepted: File[], rejected: FileRejection[]) => {
      setError(null)

      if (rejected.length) {
        const reason = rejected[0].errors[0]
        setError(
          reason.code === 'file-too-large'
            ? `That file is larger than ${MAX_MB} MB.`
            : 'Only JPG, PNG and WebP images are supported.',
        )
        return
      }

      const file = accepted[0]
      if (!file) return

      setUploading(true)
      try {
        onChange(await api.assets.upload(file, assetType, projectId))
      } catch (err) {
        // The server does its own validation on the actual bytes (§58), so its
        // message is more accurate than anything we could guess client-side.
        setError(err instanceof ApiError ? err.message : 'Upload failed. Please try again.')
      } finally {
        setUploading(false)
      }
    },
    [assetType, onChange, projectId],
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPT,
    maxFiles: 1,
    maxSize: MAX_MB * 1024 * 1024,
    disabled: uploading,
  })

  if (value) {
    return (
      <div className={cn('relative overflow-hidden rounded-xl border border-edge', className)}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={value.preview_url ?? value.url ?? ''}
          alt={value.filename}
          className="checkerboard aspect-square w-full object-contain"
        />
        <button
          onClick={() => onChange(null)}
          className="absolute right-2 top-2 rounded-lg bg-plum/70 p-1.5 text-white/75 backdrop-blur transition hover:text-white"
          aria-label={`Remove ${label}`}
        >
          <X className="h-4 w-4" />
        </button>
        <div className="border-t border-edge bg-canvas-raised px-3 py-2">
          <p className="truncate text-xs text-ink">{value.filename}</p>
          <p className="text-[11px] text-ink-faint">
            {value.width}×{value.height} · {formatBytes(value.size_bytes)}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className={className}>
      <div
        {...getRootProps()}
        className={cn(
          'flex aspect-square cursor-pointer flex-col items-center justify-center gap-2.5',
          'rounded-xl border border-dashed p-6 text-center transition',
          isDragActive
            ? 'border-accent bg-accent-muted'
            : 'border-edge hover:border-edge-strong hover:bg-canvas-overlay',
          uploading && 'pointer-events-none opacity-60',
        )}
      >
        <input {...getInputProps()} />
        {uploading ? (
          <>
            <Loader2 className="h-6 w-6 animate-spin text-accent" />
            <p className="text-sm text-ink-muted">Uploading…</p>
          </>
        ) : (
          <>
            <ImagePlus className="h-6 w-6 text-ink-faint" />
            <p className="text-sm font-medium">{label}</p>
            <p className="text-xs text-ink-faint">
              Drop an image or click · JPG, PNG, WebP · up to {MAX_MB} MB
            </p>
          </>
        )}
      </div>
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
    </div>
  )
}
