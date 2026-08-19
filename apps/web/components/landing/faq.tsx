'use client'

import { ChevronDown } from 'lucide-react'
import { useState } from 'react'

import { cn } from '@/lib/utils'

const FAQS = [
  {
    q: 'How realistic are the results?',
    // §104 — no "100% realistic" claim, and the caveats are stated plainly.
    a: 'These are AI-generated product images, not photographs. Quality depends on the garment, the model photo, pose, lighting and input resolution. Flat-lay packshots on a plain background give the best results; heavily patterned or highly structured garments are hardest.',
  },
  {
    q: 'How long does a generation take?',
    a: 'Typically between 30 seconds and two minutes, depending on the model, output size and how busy the queue is. You see live progress and your position in the queue while it runs.',
  },
  {
    q: 'Who owns the images I generate?',
    a: 'You do. We do not use your uploads to train models, and generated images are private to your workspace by default.',
  },
  {
    q: 'Are my product photos kept private?',
    a: 'Yes. Uploads go to private storage and are only ever served through short-lived signed links. You can delete individual assets, whole projects, or your entire account at any time.',
  },
  {
    q: 'Can I upload my own models?',
    a: 'Yes. Upload a full-body or three-quarter photo with the subject clearly visible. We check resolution, focus and framing on upload and tell you if a photo will not work well before you spend credits on it.',
  },
  {
    q: 'What is a credit?',
    a: 'One try-on generation costs one credit. HD output and extra variations cost more; background removal and basic adjustments are free. If a generation fails, the credit goes back to your balance automatically.',
  },
  {
    q: 'Do you use paid AI APIs?',
    a: 'No. The platform runs self-hosted open models on our own GPUs, so there is no per-image third-party fee. That is also why the AI engine is swappable — a better model can be dropped in without changing anything you use.',
  },
]

export function LandingFaq() {
  const [open, setOpen] = useState<number | null>(0)

  return (
    <div className="mx-auto max-w-3xl divide-y divide-edge overflow-hidden rounded-2xl border border-edge">
      {FAQS.map((faq, i) => {
        const isOpen = open === i
        return (
          <div key={faq.q}>
            <button
              onClick={() => setOpen(isOpen ? null : i)}
              aria-expanded={isOpen}
              className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition hover:bg-canvas-overlay"
            >
              <span className="text-sm font-medium">{faq.q}</span>
              <ChevronDown
                className={cn('h-4 w-4 shrink-0 text-ink-faint transition', isOpen && 'rotate-180')}
              />
            </button>
            {isOpen && (
              <p className="px-5 pb-5 text-sm leading-relaxed text-ink-muted">{faq.a}</p>
            )}
          </div>
        )
      })}
    </div>
  )
}
