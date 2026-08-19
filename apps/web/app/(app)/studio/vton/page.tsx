'use client'

/**
 * §90 — the first vertical slice, and the thing the whole product hangs on:
 * upload garment → pick model → mask → generate → result → download.
 */

import { useQueryClient } from '@tanstack/react-query'
import { Sparkles, SlidersHorizontal, Wand2 } from 'lucide-react'
import { useState } from 'react'

import { ApiError, api } from '@/lib/api'
import { useSession, useStudioOptions } from '@/lib/hooks'
import type { Asset, GarmentCategory, ModelProfile } from '@/lib/types'
import { titleCase } from '@/lib/utils'
import { Badge, Button, Card, Field, Select, Slider, Switch } from '@/components/ui'
import { useToast } from '@/components/ui/toast'
import { GenerationPanel } from '@/components/studio/generation-panel'
import { MaskEditor } from '@/components/studio/mask-editor'
import { ModelPicker } from '@/components/studio/model-picker'
import { UploadZone } from '@/components/studio/upload-zone'

export default function VirtualTryOnPage() {
  const toast = useToast()
  const queryClient = useQueryClient()
  const { data: session } = useSession()
  const { data: options } = useStudioOptions()

  const [garment, setGarment] = useState<Asset | null>(null)
  const [model, setModel] = useState<ModelProfile | null>(null)
  const [maskAssetId, setMaskAssetId] = useState<string | null>(null)
  const [editingMask, setEditingMask] = useState(false)

  const [category, setCategory] = useState<GarmentCategory | ''>('')
  const [hd, setHd] = useState(false)
  const [numImages, setNumImages] = useState(1)
  const [steps, setSteps] = useState(30)
  const [preserveFace, setPreserveFace] = useState(true)
  const [seed, setSeed] = useState<string>('')
  const [showAdvanced, setShowAdvanced] = useState(false)

  const [jobId, setJobId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const featureOff = options && options.features.VTON_ENABLED === false
  const canGenerate = Boolean(garment && model) && !submitting && !featureOff

  // §40 — show the price before the click, not after.
  const cost = (options?.credit_costs.vton ?? 1) * (hd ? 2 : 1) * numImages
  const balance = session?.organization.credit_balance ?? 0
  const affordable = balance >= cost

  async function generate() {
    if (!garment || !model) return
    setSubmitting(true)

    try {
      const created = await api.generate.vton({
        garment_asset_id: garment.id,
        model_profile_id: model.id,
        mask_asset_id: maskAssetId ?? undefined,
        category: category || undefined,
        hd,
        num_images: numImages,
        steps,
        preserve_face: preserveFace,
        seed: seed ? Number(seed) : undefined,
      })

      setJobId(created.job_id)
      // The balance changed server-side; refresh so the header is honest.
      queryClient.invalidateQueries({ queryKey: ['session'] })

      toast.info(
        'Generation queued',
        created.queue_position
          ? `Position #${created.queue_position} · about ${created.estimated_seconds}s`
          : 'Starting now.',
      )
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : 'Could not start the generation',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-[1600px]">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Virtual Try-On</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Put a garment on any model. Results are AI-generated and vary with input quality.
          </p>
        </div>
        {featureOff && <Badge tone="warning">Temporarily unavailable</Badge>}
      </header>

      {/* §9 studio layout: tools left, canvas right. */}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,420px)_1fr]">
        <div className="space-y-4">
          <Card>
            <SectionTitle step={1} title="Garment" />
            <UploadZone
              label="Upload the product photo"
              assetType="product"
              value={garment}
              onChange={(asset) => {
                setGarment(asset)
                setMaskAssetId(null)
              }}
              className="mt-3"
            />

            {garment && (
              <div className="mt-3 space-y-3">
                <Field label="Category" hint="Detected automatically when left on Auto.">
                  <Select
                    value={category}
                    onChange={(e) => setCategory(e.target.value as GarmentCategory | '')}
                  >
                    <option value="">Auto-detect</option>
                    {(options?.garment_categories ?? []).map((c) => (
                      <option key={c.key} value={c.key}>{c.label}</option>
                    ))}
                  </Select>
                </Field>

                <div className="flex items-center gap-2">
                  <Button size="sm" variant="secondary" onClick={() => setEditingMask((v) => !v)}>
                    <Wand2 className="h-3.5 w-3.5" />
                    {maskAssetId ? 'Edit mask' : 'Add mask'}
                  </Button>
                  {maskAssetId && (
                    <>
                      <Badge tone="accent">Mask applied</Badge>
                      <button
                        onClick={() => setMaskAssetId(null)}
                        className="text-xs text-ink-faint transition hover:text-ink"
                      >
                        Clear
                      </button>
                    </>
                  )}
                </div>
              </div>
            )}
          </Card>

          {editingMask && garment && (
            <Card>
              <SectionTitle title="Mask editor" />
              <div className="mt-3">
                <MaskEditor
                  source={garment}
                  onSave={(id) => {
                    setMaskAssetId(id)
                    setEditingMask(false)
                    toast.success('Mask applied')
                  }}
                  onCancel={() => setEditingMask(false)}
                />
              </div>
            </Card>
          )}

          <Card>
            <SectionTitle step={2} title="Model" />
            <div className="mt-3">
              <ModelPicker
                value={model}
                onChange={setModel}
                filterOptions={options?.model_filters}
              />
            </div>
          </Card>

          <Card>
            <div className="flex items-center justify-between">
              <SectionTitle step={3} title="Settings" />
              <button
                onClick={() => setShowAdvanced((v) => !v)}
                className="flex items-center gap-1.5 text-xs text-ink-muted transition hover:text-ink"
              >
                <SlidersHorizontal className="h-3.5 w-3.5" />
                {showAdvanced ? 'Hide' : 'Advanced'}
              </button>
            </div>

            <div className="mt-4 space-y-4">
              <Switch
                checked={hd}
                onChange={setHd}
                label="HD output"
                hint={`Higher resolution · +${options?.credit_costs.vton ?? 1} credit per image`}
              />

              <Slider
                label="Variations"
                value={numImages}
                onChange={setNumImages}
                min={1}
                max={4}
              />

              {showAdvanced && (
                <div className="space-y-4 border-t border-edge pt-4">
                  <Slider
                    label="Quality steps"
                    value={steps}
                    onChange={setSteps}
                    min={10}
                    max={60}
                    format={(v) => `${v} steps`}
                  />

                  <Switch
                    checked={preserveFace}
                    onChange={setPreserveFace}
                    label="Preserve face"
                    hint="Keeps the model's head from the original photo."
                  />

                  {/* §67 — a fixed seed makes a result reproducible. */}
                  <Field label="Seed" hint="Leave blank for a random seed.">
                    <input
                      className="field"
                      inputMode="numeric"
                      value={seed}
                      onChange={(e) => setSeed(e.target.value.replace(/\D/g, ''))}
                      placeholder="Random"
                    />
                  </Field>
                </div>
              )}
            </div>
          </Card>

          <div className="sticky bottom-4 z-10">
            <Card className="flex items-center justify-between gap-4 !p-4">
              <div>
                <p className="text-sm font-medium">
                  {cost} credit{cost === 1 ? '' : 's'}
                </p>
                <p className="text-xs text-ink-faint">{balance} available</p>
              </div>
              <Button
                size="lg"
                onClick={generate}
                loading={submitting}
                disabled={!canGenerate || !affordable}
              >
                <Sparkles className="h-4 w-4" />
                {affordable ? 'Generate' : 'Not enough credits'}
              </Button>
            </Card>
          </div>
        </div>

        <div className="min-w-0">
          <GenerationPanel
            jobId={jobId}
            originalUrl={model?.image?.preview_url ?? null}
            onClear={() => setJobId(null)}
          />
        </div>
      </div>
    </div>
  )
}

function SectionTitle({ step, title }: { step?: number; title: string }) {
  return (
    <div className="flex items-center gap-2.5">
      {step !== undefined && (
        <span className="grid h-6 w-6 place-items-center rounded-full bg-accent-muted font-mono text-xs text-accent">
          {step}
        </span>
      )}
      <h2 className="text-sm font-medium">{title}</h2>
    </div>
  )
}
