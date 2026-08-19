'use client'

/** §24 enhance, §25 generative fill, §26 magic eraser, §27 upscale, §24 expand. */

import { useQueryClient } from '@tanstack/react-query'
import { Eraser, Maximize2, Sliders, Sparkles, Wand2 } from 'lucide-react'
import { useState } from 'react'

import { ApiError, api } from '@/lib/api'
import { useSession } from '@/lib/hooks'
import type { Asset } from '@/lib/types'
import { cn } from '@/lib/utils'
import { Button, Card, Field, Slider, Switch, Textarea } from '@/components/ui'
import { useToast } from '@/components/ui/toast'
import { GenerationPanel } from '@/components/studio/generation-panel'
import { MaskEditor } from '@/components/studio/mask-editor'
import { UploadZone } from '@/components/studio/upload-zone'

type Tool = 'enhance' | 'fill' | 'erase' | 'upscale' | 'expand'

const TOOLS: { key: Tool; label: string; icon: typeof Sliders }[] = [
  { key: 'enhance', label: 'Adjust', icon: Sliders },
  { key: 'fill', label: 'Generative fill', icon: Wand2 },
  { key: 'erase', label: 'Magic eraser', icon: Eraser },
  { key: 'upscale', label: 'Upscale', icon: Maximize2 },
  { key: 'expand', label: 'Expand', icon: Maximize2 },
]

export default function ImageEditorPage() {
  const toast = useToast()
  const queryClient = useQueryClient()
  const { data: session } = useSession()

  const [tool, setTool] = useState<Tool>('enhance')
  const [source, setSource] = useState<Asset | null>(null)
  const [maskAssetId, setMaskAssetId] = useState<string | null>(null)
  const [editingMask, setEditingMask] = useState(false)

  const [auto, setAuto] = useState(true)
  const [brightness, setBrightness] = useState(1)
  const [contrast, setContrast] = useState(1)
  const [saturation, setSaturation] = useState(1)
  const [sharpness, setSharpness] = useState(1)

  const [prompt, setPrompt] = useState('')
  const [scale, setScale] = useState(2)
  const [expand, setExpand] = useState({ left: 0, right: 0, top: 0, bottom: 0 })

  const [jobId, setJobId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const needsMask = tool === 'fill' || tool === 'erase'
  const ready =
    Boolean(source) &&
    (!needsMask || Boolean(maskAssetId)) &&
    (tool !== 'fill' || prompt.trim().length > 0) &&
    (tool !== 'expand' || Object.values(expand).some((v) => v > 0))

  async function run() {
    if (!source) return
    setSubmitting(true)

    try {
      let created
      switch (tool) {
        case 'enhance':
          created = await api.generate.enhance({
            image_asset_id: source.id,
            auto,
            brightness,
            contrast,
            saturation,
            sharpness,
          })
          break
        case 'fill':
          created = await api.generate.inpaint({
            image_asset_id: source.id,
            mask_asset_id: maskAssetId,
            prompt: prompt.trim(),
          })
          break
        case 'erase':
          created = await api.generate.removeObject({
            image_asset_id: source.id,
            mask_asset_id: maskAssetId,
          })
          break
        case 'upscale':
          created = await api.generate.upscale({ image_asset_id: source.id, scale })
          break
        case 'expand':
          created = await api.generate.expand({
            image_asset_id: source.id,
            ...expand,
            prompt: prompt.trim() || undefined,
          })
          break
      }

      setJobId(created.job_id)
      queryClient.invalidateQueries({ queryKey: ['session'] })
      toast.info('Queued')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not start the job')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-[1600px]">
      <header className="mb-6">
        <h1 className="display text-2xl">Image Editor</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Retouch, fill, erase, upscale and expand your generated images.
        </p>
      </header>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,420px)_1fr]">
        <div className="space-y-4">
          <div className="flex flex-wrap gap-1.5 rounded-xl border border-edge bg-canvas-raised p-1">
            {TOOLS.map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                onClick={() => setTool(key)}
                className={cn(
                  'flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition',
                  tool === key ? 'bg-accent-muted text-accent' : 'text-ink-muted hover:text-ink',
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {label}
              </button>
            ))}
          </div>

          <Card>
            <h2 className="text-sm font-medium">Image</h2>
            <UploadZone
              label="Upload an image"
              assetType="product"
              value={source}
              onChange={(asset) => {
                setSource(asset)
                setMaskAssetId(null)
              }}
              className="mt-3"
            />
          </Card>

          {needsMask && source && (
            <Card>
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-medium">
                  {tool === 'fill' ? 'Area to fill' : 'Area to erase'}
                </h2>
                <Button size="sm" variant="secondary" onClick={() => setEditingMask((v) => !v)}>
                  {maskAssetId ? 'Edit' : 'Draw'}
                </Button>
              </div>
              {maskAssetId && !editingMask && (
                <p className="mt-2 text-xs text-success">Mask ready.</p>
              )}
              {editingMask && (
                <div className="mt-3">
                  <MaskEditor
                    source={source}
                    onSave={(id) => {
                      setMaskAssetId(id)
                      setEditingMask(false)
                    }}
                    onCancel={() => setEditingMask(false)}
                  />
                </div>
              )}
            </Card>
          )}

          <Card className="space-y-4">
            {tool === 'enhance' && (
              <>
                <Switch
                  checked={auto}
                  onChange={setAuto}
                  label="Auto enhance"
                  hint="Applies safe defaults that flatter most product photography."
                />
                {!auto && (
                  <div className="space-y-4 border-t border-edge pt-4">
                    <Slider label="Brightness" value={brightness} onChange={setBrightness} min={0.5} max={1.8} step={0.02} format={(v) => v.toFixed(2)} />
                    <Slider label="Contrast" value={contrast} onChange={setContrast} min={0.5} max={1.8} step={0.02} format={(v) => v.toFixed(2)} />
                    <Slider label="Saturation" value={saturation} onChange={setSaturation} min={0} max={2} step={0.02} format={(v) => v.toFixed(2)} />
                    <Slider label="Sharpness" value={sharpness} onChange={setSharpness} min={0} max={2.5} step={0.05} format={(v) => v.toFixed(2)} />
                  </div>
                )}
              </>
            )}

            {tool === 'fill' && (
              <Field label="What should appear there?">
                <Textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="A luxury handbag beside the model."
                  rows={3}
                />
              </Field>
            )}

            {tool === 'erase' && (
              <p className="text-sm text-ink-muted">
                Paint over the object you want gone. The area is filled with plausible background.
              </p>
            )}

            {tool === 'upscale' && (
              <div className="grid grid-cols-2 gap-2">
                {[2, 4].map((factor) => (
                  <button
                    key={factor}
                    onClick={() => setScale(factor)}
                    className={cn(
                      'rounded-xl border px-3 py-3 text-sm transition',
                      scale === factor
                        ? 'border-accent bg-accent-muted text-accent'
                        : 'border-edge text-ink-muted hover:text-ink',
                    )}
                  >
                    {factor}×
                  </button>
                ))}
              </div>
            )}

            {tool === 'expand' && (
              <>
                <div className="grid grid-cols-2 gap-4">
                  {(['top', 'bottom', 'left', 'right'] as const).map((side) => (
                    <Slider
                      key={side}
                      label={side}
                      value={expand[side]}
                      onChange={(v) => setExpand((e) => ({ ...e, [side]: v }))}
                      min={0}
                      max={512}
                      step={32}
                      format={(v) => `${v}px`}
                    />
                  ))}
                </div>
                <Field label="Describe the new area" hint="Optional.">
                  <Textarea
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    placeholder="Seamless continuation of the studio backdrop."
                    rows={2}
                  />
                </Field>
              </>
            )}
          </Card>

          <div className="sticky bottom-4">
            <Card className="flex items-center justify-between gap-4 !p-4">
              <p className="text-xs text-ink-faint">
                {session?.organization.credit_balance ?? 0} credits available
              </p>
              <Button size="lg" onClick={run} loading={submitting} disabled={!ready}>
                <Sparkles className="h-4 w-4" /> Apply
              </Button>
            </Card>
          </div>
        </div>

        <GenerationPanel
          jobId={jobId}
          originalUrl={source?.preview_url ?? null}
          onClear={() => setJobId(null)}
        />
      </div>
    </div>
  )
}
