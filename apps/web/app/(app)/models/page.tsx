'use client'

import { useState } from 'react'

import { useStudioOptions } from '@/lib/hooks'
import { ModelPicker } from '@/components/studio/model-picker'
import type { ModelProfile } from '@/lib/types'
import { Card } from '@/components/ui'

export default function ModelsPage() {
  const { data: options } = useStudioOptions()
  const [selected, setSelected] = useState<ModelProfile | null>(null)

  return (
    <div className="mx-auto max-w-5xl">
      <header className="mb-6">
        <h1 className="display text-2xl">Models</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Browse the library or upload your own. Custom uploads are checked for framing and
          focus before they can be used.
        </p>
      </header>

      <Card>
        <ModelPicker
          value={selected}
          onChange={setSelected}
          filterOptions={options?.model_filters}
        />
      </Card>

      {selected?.validation && selected.validation.acceptable === false && (
        <Card className="mt-4 border-warning/30">
          <h2 className="text-sm font-medium text-warning">This photo needs attention</h2>
          <p className="mt-1 text-sm text-ink-muted">{selected.validation.message}</p>
          {selected.validation.reasons?.length ? (
            <ul className="mt-3 space-y-1 text-xs text-ink-muted">
              {selected.validation.reasons.map((reason) => (
                <li key={reason}>• {reason}</li>
              ))}
            </ul>
          ) : null}
        </Card>
      )}
    </div>
  )
}
