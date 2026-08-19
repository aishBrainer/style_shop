'use client'

/** §21 — AI product photography. */

import { useQueryClient } from '@tanstack/react-query'
import { Camera, Sparkles } from 'lucide-react'
import { useState } from 'react'

import { ApiError, api } from '@/lib/api'
import { useSession, useStudioOptions } from '@/lib/hooks'
import type { Asset } from '@/lib/types'
import { Button, Card, Field, Select, Textarea } from '@/components/ui'
import { useToast } from '@/components/ui/toast'
import { GenerationPanel } from '@/components/studio/generation-panel'
import { UploadZone } from '@/components/studio/upload-zone'

export default function ProductPhotographyPage() {
  const toast = useToast()
  const queryClient = useQueryClient()
  const { data: session } = useSession()
  const { data: options } = useStudioOptions()

  const [source, setSource] = useState<Asset | null>(null)
  const [background, setBackground] = useState('studio')
  const [lighting, setLighting] = useState('studio')
  const [camera, setCamera] = useState('medium')
  const [composition, setComposition] = useState('center')
  const [prompt, setPrompt] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const cost = options?.credit_costs.product_photography ?? 1
  const balance = session?.organization.credit_balance ?? 0

  async function generate() {
    if (!source) return
    setSubmitting(true)
    try {
      const created = await api.generate.photography({
        image_asset_id: source.id,
        background,
        lighting,
        camera,
        composition,
        prompt: prompt.trim() || undefined,
      })
      setJobId(created.job_id)
      queryClient.invalidateQueries({ queryKey: ['session'] })
      toast.info('Generation queued')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not start the generation')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-[1600px]">
      <header className="mb-6">
        <h1 className="text-xl font-semibold">Product Photography</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Turn a plain product shot into a styled studio image.
        </p>
      </header>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,420px)_1fr]">
        <div className="space-y-4">
          <Card>
            <h2 className="text-sm font-medium">Product</h2>
            <UploadZone
              label="Upload the product photo"
              assetType="product"
              value={source}
              onChange={setSource}
              className="mt-3"
            />
          </Card>

          <Card className="space-y-4">
            <h2 className="text-sm font-medium">Look</h2>

            <Field label="Background">
              <Select value={background} onChange={(e) => setBackground(e.target.value)}>
                {(options?.background_presets ?? []).map((p) => (
                  <option key={p.key} value={p.key}>{p.label}</option>
                ))}
              </Select>
            </Field>

            <Field label="Lighting">
              <Select value={lighting} onChange={(e) => setLighting(e.target.value)}>
                {(options?.lighting ?? []).map((p) => (
                  <option key={p.key} value={p.key}>{p.label}</option>
                ))}
              </Select>
            </Field>

            <Field label="Camera">
              <Select value={camera} onChange={(e) => setCamera(e.target.value)}>
                {(options?.camera ?? []).map((p) => (
                  <option key={p.key} value={p.key}>{p.label}</option>
                ))}
              </Select>
            </Field>

            <Field label="Composition">
              <Select value={composition} onChange={(e) => setComposition(e.target.value)}>
                {(options?.composition ?? []).map((p) => (
                  <option key={p.key} value={p.key}>{p.label}</option>
                ))}
              </Select>
            </Field>

            <Field
              label="Custom prompt"
              hint="Overrides the background preset when set."
            >
              <Textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Luxury marble fashion studio with soft sunlight."
                rows={3}
              />
            </Field>
          </Card>

          <div className="sticky bottom-4">
            <Card className="flex items-center justify-between gap-4 !p-4">
              <div>
                <p className="text-sm font-medium">{cost} credit{cost === 1 ? '' : 's'}</p>
                <p className="text-xs text-ink-faint">{balance} available</p>
              </div>
              <Button size="lg" onClick={generate} loading={submitting} disabled={!source || balance < cost}>
                <Camera className="h-4 w-4" /> Generate
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
