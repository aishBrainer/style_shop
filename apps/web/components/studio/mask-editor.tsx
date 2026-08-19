'use client'

/**
 * §13 — manual mask editor.
 *
 * Canvas-based brush/eraser with undo, redo, zoom, pan and reset. The mask is
 * kept at the source image's native resolution in an offscreen canvas so that
 * zooming never degrades it; the visible canvas is only a viewport onto it.
 *
 * Auto Mask is server-side (SAM 2 or rembg, §13) — the button posts the source
 * asset and paints the returned mask in.
 */

import {
  Brush,
  Eraser,
  Loader2,
  RotateCcw,
  Redo2,
  Sparkles,
  Undo2,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { api } from '@/lib/api'
import type { Asset } from '@/lib/types'
import { cn } from '@/lib/utils'
import { Button, Slider } from '@/components/ui'
import { useToast } from '@/components/ui/toast'

type Tool = 'brush' | 'eraser'

const MAX_HISTORY = 24

export function MaskEditor({
  source,
  onSave,
  onCancel,
}: {
  source: Asset
  onSave: (maskAssetId: string) => void
  onCancel: () => void
}) {
  const toast = useToast()
  const viewportRef = useRef<HTMLDivElement>(null)
  const displayRef = useRef<HTMLCanvasElement>(null)
  // The authoritative mask, at the source image's own pixel dimensions.
  const maskRef = useRef<HTMLCanvasElement | null>(null)
  const imageRef = useRef<HTMLImageElement | null>(null)

  const [tool, setTool] = useState<Tool>('brush')
  const [brushSize, setBrushSize] = useState(40)
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [ready, setReady] = useState(false)
  const [saving, setSaving] = useState(false)
  const [autoMasking, setAutoMasking] = useState(false)

  const history = useRef<ImageData[]>([])
  const future = useRef<ImageData[]>([])
  const drawing = useRef(false)
  const panning = useRef(false)
  const lastPoint = useRef<{ x: number; y: number } | null>(null)

  // --- load the source image -------------------------------------------
  useEffect(() => {
    const url = source.preview_url ?? source.url
    if (!url) return

    const img = new Image()
    // Signed URLs are same-origin-ish but cross-origin in practice (MinIO);
    // without this the canvas is tainted and toDataURL throws.
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      imageRef.current = img

      const mask = document.createElement('canvas')
      mask.width = img.naturalWidth
      mask.height = img.naturalHeight
      maskRef.current = mask

      setReady(true)
    }
    img.onerror = () => toast.error('Could not load the image for editing')
    img.src = url
  }, [source, toast])

  // --- render ------------------------------------------------------------
  const render = useCallback(() => {
    const canvas = displayRef.current
    const image = imageRef.current
    const mask = maskRef.current
    if (!canvas || !image || !mask) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.save()
    ctx.translate(pan.x, pan.y)
    ctx.scale(zoom, zoom)

    ctx.drawImage(image, 0, 0, canvas.width, canvas.height)

    // Tint the mask so the user can see what they painted over the photo.
    ctx.globalAlpha = 0.5
    ctx.globalCompositeOperation = 'source-over'
    ctx.drawImage(mask, 0, 0, canvas.width, canvas.height)
    ctx.globalAlpha = 1

    ctx.restore()
  }, [pan, zoom])

  useEffect(() => {
    if (ready) render()
  }, [ready, render])

  // --- history -----------------------------------------------------------
  const snapshot = useCallback(() => {
    const mask = maskRef.current
    if (!mask) return
    const ctx = mask.getContext('2d')
    if (!ctx) return

    history.current.push(ctx.getImageData(0, 0, mask.width, mask.height))
    if (history.current.length > MAX_HISTORY) history.current.shift()
    // Any new stroke invalidates the redo branch.
    future.current = []
  }, [])

  const restore = useCallback(
    (from: React.MutableRefObject<ImageData[]>, to: React.MutableRefObject<ImageData[]>) => {
      const mask = maskRef.current
      const ctx = mask?.getContext('2d')
      if (!mask || !ctx) return

      const state = from.current.pop()
      if (!state) return

      to.current.push(ctx.getImageData(0, 0, mask.width, mask.height))
      ctx.putImageData(state, 0, 0)
      render()
    },
    [render],
  )

  // --- painting ----------------------------------------------------------
  function toMaskCoords(event: React.PointerEvent): { x: number; y: number } | null {
    const canvas = displayRef.current
    const mask = maskRef.current
    if (!canvas || !mask) return null

    const rect = canvas.getBoundingClientRect()
    // Screen → canvas → (undo pan/zoom) → mask pixel space.
    const cx = ((event.clientX - rect.left) * (canvas.width / rect.width) - pan.x) / zoom
    const cy = ((event.clientY - rect.top) * (canvas.height / rect.height) - pan.y) / zoom

    return {
      x: (cx / canvas.width) * mask.width,
      y: (cy / canvas.height) * mask.height,
    }
  }

  function paint(from: { x: number; y: number } | null, to: { x: number; y: number }) {
    const mask = maskRef.current
    const ctx = mask?.getContext('2d')
    if (!mask || !ctx) return

    // Scale the brush so it feels the same size regardless of image resolution.
    const scale = mask.width / (displayRef.current?.width ?? mask.width)
    ctx.lineWidth = brushSize * scale
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.strokeStyle = '#7c5cff'
    ctx.globalCompositeOperation = tool === 'brush' ? 'source-over' : 'destination-out'

    ctx.beginPath()
    ctx.moveTo(from?.x ?? to.x, from?.y ?? to.y)
    ctx.lineTo(to.x, to.y)
    ctx.stroke()

    ctx.globalCompositeOperation = 'source-over'
    render()
  }

  function handlePointerDown(event: React.PointerEvent) {
    // Space/middle-drag pans; everything else paints.
    if (event.button === 1 || event.shiftKey) {
      panning.current = true
      lastPoint.current = { x: event.clientX, y: event.clientY }
      return
    }

    const point = toMaskCoords(event)
    if (!point) return

    snapshot()
    drawing.current = true
    lastPoint.current = point
    paint(null, point)
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  function handlePointerMove(event: React.PointerEvent) {
    if (panning.current && lastPoint.current) {
      setPan((p) => ({
        x: p.x + (event.clientX - lastPoint.current!.x),
        y: p.y + (event.clientY - lastPoint.current!.y),
      }))
      lastPoint.current = { x: event.clientX, y: event.clientY }
      return
    }

    if (!drawing.current) return
    const point = toMaskCoords(event)
    if (!point) return
    paint(lastPoint.current, point)
    lastPoint.current = point
  }

  function handlePointerUp() {
    drawing.current = false
    panning.current = false
    lastPoint.current = null
  }

  // --- actions -----------------------------------------------------------
  function reset() {
    const mask = maskRef.current
    const ctx = mask?.getContext('2d')
    if (!mask || !ctx) return
    snapshot()
    ctx.clearRect(0, 0, mask.width, mask.height)
    setZoom(1)
    setPan({ x: 0, y: 0 })
    render()
  }

  async function autoMask() {
    setAutoMasking(true)
    try {
      // Reuses the same server-side segmentation the pipelines use, so the
      // starting mask matches what an auto-generation would have produced.
      const job = await api.generate.removeBackground({
        image_asset_id: source.id,
        background: 'transparent',
      })
      toast.info('Auto mask queued', 'It will appear here in a few seconds.')

      const result = await pollJob(job.job_id)
      const output = result?.outputs?.[0]
      if (!output?.url) throw new Error('no output')

      await paintFromUrl(output.url)
      toast.success('Auto mask applied', 'Refine it with the brush if needed.')
    } catch {
      toast.error('Auto mask failed', 'Paint the region manually instead.')
    } finally {
      setAutoMasking(false)
    }
  }

  async function paintFromUrl(url: string) {
    const mask = maskRef.current
    const ctx = mask?.getContext('2d')
    if (!mask || !ctx) return

    const cutout = new Image()
    cutout.crossOrigin = 'anonymous'
    await new Promise<void>((resolve, reject) => {
      cutout.onload = () => resolve()
      cutout.onerror = () => reject(new Error('load failed'))
      cutout.src = url
    })

    snapshot()
    ctx.clearRect(0, 0, mask.width, mask.height)
    ctx.drawImage(cutout, 0, 0, mask.width, mask.height)
    // Recolour the cut-out's alpha into the mask tint.
    ctx.globalCompositeOperation = 'source-in'
    ctx.fillStyle = '#7c5cff'
    ctx.fillRect(0, 0, mask.width, mask.height)
    ctx.globalCompositeOperation = 'source-over'
    render()
  }

  async function save() {
    const mask = maskRef.current
    if (!mask) return

    setSaving(true)
    try {
      // The API expects a plain white-on-black mask, not the tinted overlay.
      const flat = document.createElement('canvas')
      flat.width = mask.width
      flat.height = mask.height
      const ctx = flat.getContext('2d')
      if (!ctx) throw new Error('canvas unavailable')

      ctx.fillStyle = '#000000'
      ctx.fillRect(0, 0, flat.width, flat.height)
      ctx.drawImage(mask, 0, 0)
      ctx.globalCompositeOperation = 'source-in'
      ctx.fillStyle = '#ffffff'
      ctx.fillRect(0, 0, flat.width, flat.height)

      const asset = await api.assets.uploadMask(flat.toDataURL('image/png'))
      onSave(asset.id)
    } catch {
      toast.error('Could not save the mask')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1.5 rounded-xl border border-edge bg-canvas-raised p-2">
        <ToolButton active={tool === 'brush'} onClick={() => setTool('brush')} label="Brush">
          <Brush className="h-4 w-4" />
        </ToolButton>
        <ToolButton active={tool === 'eraser'} onClick={() => setTool('eraser')} label="Eraser">
          <Eraser className="h-4 w-4" />
        </ToolButton>

        <span className="mx-1 h-5 w-px bg-edge" />

        <ToolButton onClick={() => restore(history, future)} label="Undo">
          <Undo2 className="h-4 w-4" />
        </ToolButton>
        <ToolButton onClick={() => restore(future, history)} label="Redo">
          <Redo2 className="h-4 w-4" />
        </ToolButton>

        <span className="mx-1 h-5 w-px bg-edge" />

        <ToolButton onClick={() => setZoom((z) => Math.min(4, z * 1.25))} label="Zoom in">
          <ZoomIn className="h-4 w-4" />
        </ToolButton>
        <ToolButton onClick={() => setZoom((z) => Math.max(0.5, z / 1.25))} label="Zoom out">
          <ZoomOut className="h-4 w-4" />
        </ToolButton>
        <ToolButton onClick={reset} label="Reset">
          <RotateCcw className="h-4 w-4" />
        </ToolButton>

        <Button size="sm" variant="secondary" className="ml-auto" onClick={autoMask} loading={autoMasking}>
          <Sparkles className="h-3.5 w-3.5" /> Auto Mask
        </Button>
      </div>

      <div className="w-56">
        <Slider label="Brush size" value={brushSize} onChange={setBrushSize} min={4} max={160} />
      </div>

      <div
        ref={viewportRef}
        className="checkerboard relative overflow-hidden rounded-xl border border-edge"
      >
        {!ready ? (
          <div className="flex aspect-square items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-accent" />
          </div>
        ) : (
          <canvas
            ref={displayRef}
            width={768}
            height={1024}
            className="block w-full cursor-crosshair touch-none"
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerLeave={handlePointerUp}
          />
        )}
      </div>

      <p className="text-xs text-ink-faint">
        Paint over the area to replace. Hold Shift and drag to pan.
      </p>

      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button onClick={save} loading={saving} disabled={!ready}>Use this mask</Button>
      </div>
    </div>
  )
}

function ToolButton({
  active,
  onClick,
  label,
  children,
}: {
  active?: boolean
  onClick: () => void
  label: string
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      aria-pressed={active}
      className={cn(
        'grid h-8 w-8 place-items-center rounded-lg transition',
        active ? 'bg-accent-muted text-accent' : 'text-ink-muted hover:bg-canvas-overlay hover:text-ink',
      )}
    >
      {children}
    </button>
  )
}

/** Small local poller — the mask editor needs one result, not a subscription. */
async function pollJob(jobId: string, timeoutMs = 90_000) {
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    const job = await api.jobs.get(jobId)
    if (job.status === 'completed') return job
    if (job.status === 'failed' || job.status === 'cancelled') return null
    await new Promise((r) => setTimeout(r, 1500))
  }
  return null
}
