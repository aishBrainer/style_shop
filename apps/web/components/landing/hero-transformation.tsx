'use client'

/**
 * §5 hero visual: product photo → AI processing → finished model image.
 *
 * Drawn rather than photographed. Shipping placeholder "results" as if they
 * were real output would be exactly the overclaiming §104 warns against, and
 * there is no benchmarked model behind them yet. Replace these panels with
 * genuine before/after pairs once you have generations you are happy to stand
 * behind.
 */

import { motion } from 'framer-motion'
import { Shirt, Sparkles, User } from 'lucide-react'

const STAGES = [
  'Analysing garment',
  'Mapping body',
  'Applying garment',
  'Rendering fabric',
  'Finishing image',
]

export function HeroTransformation() {
  return (
    <div className="mx-auto mt-16 grid max-w-4xl items-center gap-4 sm:grid-cols-[1fr_auto_1fr]">
      <Panel label="Product photo" tone="neutral">
        <Shirt className="h-16 w-16 text-ink-faint" strokeWidth={1.2} />
      </Panel>

      <ProcessingColumn />

      <Panel label="Finished image" tone="accent">
        <User className="h-16 w-16 text-accent" strokeWidth={1.2} />
      </Panel>
    </div>
  )
}

function Panel({
  label,
  tone,
  children,
}: {
  label: string
  tone: 'neutral' | 'accent'
  children: React.ReactNode
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className={
        tone === 'accent'
          ? 'panel flex aspect-[3/4] flex-col items-center justify-center gap-4 border-accent/30 shadow-glow'
          : 'panel flex aspect-[3/4] flex-col items-center justify-center gap-4'
      }
    >
      {children}
      <span className="text-xs uppercase tracking-wider text-ink-faint">{label}</span>
    </motion.div>
  )
}

function ProcessingColumn() {
  return (
    <div className="flex flex-col items-center gap-3 py-6 sm:px-4">
      <div className="relative grid h-12 w-12 place-items-center">
        <span className="absolute inset-0 animate-pulse-ring rounded-full border border-accent/40" />
        <span className="grid h-12 w-12 place-items-center rounded-full bg-accent-muted text-accent">
          <Sparkles className="h-5 w-5" />
        </span>
      </div>

      {/* §46 — the same stage sequence the studio shows during a real run. */}
      <ul className="hidden space-y-1.5 text-center sm:block">
        {STAGES.map((stage, i) => (
          <motion.li
            key={stage}
            initial={{ opacity: 0.25 }}
            animate={{ opacity: [0.25, 1, 0.25] }}
            transition={{
              duration: 2.4,
              repeat: Infinity,
              delay: i * 0.45,
              ease: 'easeInOut',
            }}
            className="whitespace-nowrap text-[11px] text-ink-muted"
          >
            {stage}
          </motion.li>
        ))}
      </ul>
    </div>
  )
}
