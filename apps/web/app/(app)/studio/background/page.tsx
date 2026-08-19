'use client'

/** §22 background removal + §23 background replacement. */

import { useQueryClient } from '@tanstack/react-query'
import { Layers, Scissors } from 'lucide-react'
import { useState } from 'react'

import { ApiError, api } from '@/lib/api'
import { useSession, useStudioOptions } from '@/lib/hooks'
import type { Asset } from '@/lib/types'
import { cn } from '@/lib/utils'
import { Button, Card, Field, Input, Textarea } from '@/components/ui'
import { useToast } from '@/components/ui/toast'
import { GenerationPanel } from '@/components/studio/generation-panel'
import { UploadZone } from '@/components/studio/upload-zone'

type Mode = 'remove' | 'replace'

export default function BackgroundStudioPage() {
  const toast = useToast()
  const queryClient = useQueryClient()
  const { data: session } = useSession()
  const { data: options } = useStudioOptions()

  const [mode, setMode] = useState<Mode>('remove')
  const [source, setSource] = useState<Asset | null>(null)

  const [removeStyle, setRemoveStyle] = useState<'transparent' | 'white' | 'color'>('transparent')
  const [color, setColor] = useState('#FFFFFF')

  const [preset, setPreset] = useState<string | null>('studio')
  const [prompt, setPrompt] = useState('')

  const [jobId, setJobId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Removal is CPU-only, so it is free (§40).
  const cost = mode === 'remove' ? 0 : options?.credit_costs.background_replace ?? 1
  const balance = session?.organization.credit_balance ?? 0

  async function generate() {
    if (!source) return
    setSubmitting(true)

    try {
      const created =
        mode === 'remove'
          ? await api.generate.removeBackground({
              image_asset_id: source.id,
              background: removeStyle,
              background_color: color,
            })
          : await api.generate.replaceBackground({
              image_asset_id: source.id,
              preset: prompt.trim() ? undefined : preset,
              prompt: prompt.trim() || undefined,
            })

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
        <h1 className="display text-2xl">Background Studio</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Cut out the subject, or drop it into a new scene.
        </p>
      </header>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,420px)_1fr]">
        <div className="space-y-4">
          <div className="flex gap-2 rounded-xl border border-edge bg-canvas-raised p-1">
            <ModeTab active={mode === 'remove'} onClick={() => setMode('remove')} icon={<Scissors className="h-3.5 w-3.5" />}>
              Remove
            </ModeTab>
            <ModeTab active={mode === 'replace'} onClick={() => setMode('replace')} icon={<Layers className="h-3.5 w-3.5" />}>
              Replace
            </ModeTab>
          </div>

          <Card>
            <h2 className="text-sm font-medium">Image</h2>
            <UploadZone
              label="Upload an image"
              assetType="product"
              value={source}
              onChange={setSource}
              className="mt-3"
            />
          </Card>

          {mode === 'remove' ? (
            <Card className="space-y-4">
              <h2 className="text-sm font-medium">Output background</h2>
              <div className="grid grid-cols-3 gap-2">
                {(['transparent', 'white', 'color'] as const).map((style) => (
                  <button
                    key={style}
                    onClick={() => setRemoveStyle(style)}
                    className={cn(
                      'rounded-xl border px-3 py-2.5 text-xs capitalize transition',
                      removeStyle === style
                        ? 'border-accent bg-accent-muted text-accent'
                        : 'border-edge text-ink-muted hover:text-ink',
                    )}
                  >
                    {style}
                  </button>
                ))}
              </div>

              {removeStyle === 'color' && (
                <Field label="Colour">
                  <div className="flex items-center gap-2">
                    <input
                      type="color"
                      value={color}
                      onChange={(e) => setColor(e.target.value.toUpperCase())}
                      className="h-10 w-14 cursor-pointer rounded-lg border border-edge bg-canvas"
                    />
                    <Input
                      value={color}
                      onChange={(e) => setColor(e.target.value.toUpperCase())}
                      pattern="#[0-9A-Fa-f]{6}"
                    />
                  </div>
                </Field>
              )}

              <p className="text-xs text-ink-faint">
                Transparent output is delivered as a PNG. Removal does not cost credits.
              </p>
            </Card>
          ) : (
            <Card className="space-y-4">
              <h2 className="text-sm font-medium">New background</h2>

              <div className="grid grid-cols-3 gap-2">
                {(options?.background_presets ?? []).map((p) => (
                  <button
                    key={p.key}
                    onClick={() => {
                      setPreset(p.key)
                      setPrompt('')
                    }}
                    className={cn(
                      'rounded-xl border px-2.5 py-2 text-[11px] transition',
                      preset === p.key && !prompt
                        ? 'border-accent bg-accent-muted text-accent'
                        : 'border-edge text-ink-muted hover:text-ink',
                    )}
                  >
                    {p.label}
                  </button>
                ))}
              </div>

              <Field label="Or describe it" hint="A prompt overrides the preset above.">
                <Textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Luxury marble fashion studio with soft sunlight."
                  rows={3}
                />
              </Field>
            </Card>
          )}

          <div className="sticky bottom-4">
            <Card className="flex items-center justify-between gap-4 !p-4">
              <div>
                <p className="text-sm font-medium">
                  {cost === 0 ? 'Free' : `${cost} credit${cost === 1 ? '' : 's'}`}
                </p>
                <p className="text-xs text-ink-faint">{balance} available</p>
              </div>
              <Button size="lg" onClick={generate} loading={submitting} disabled={!source || balance < cost}>
                Generate
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

function ModeTab({
  active,
  onClick,
  icon,
  children,
}: {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition',
        active ? 'bg-accent-muted text-accent' : 'text-ink-muted hover:text-ink',
      )}
    >
      {icon}
      {children}
    </button>
  )
}
