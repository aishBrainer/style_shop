'use client'

/** §37 — draggable original ↔ generated comparison. */

import { useCallback, useEffect, useRef, useState } from 'react'

import { cn } from '@/lib/utils'

export function BeforeAfter({
  before,
  after,
  beforeLabel = 'Original',
  afterLabel = 'Generated',
  className,
}: {
  before: string
  after: string
  beforeLabel?: string
  afterLabel?: string
  className?: string
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState(50)
  const [dragging, setDragging] = useState(false)

  const updateFromClientX = useCallback((clientX: number) => {
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect) return
    const pct = ((clientX - rect.left) / rect.width) * 100
    setPosition(Math.min(100, Math.max(0, pct)))
  }, [])

  useEffect(() => {
    if (!dragging) return

    // Listeners go on window, not the element: the pointer routinely leaves the
    // image while dragging and the handle should keep following it.
    const onMove = (e: PointerEvent) => updateFromClientX(e.clientX)
    const onUp = () => setDragging(false)

    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    return () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }
  }, [dragging, updateFromClientX])

  return (
    <div
      ref={containerRef}
      className={cn(
        'relative select-none overflow-hidden rounded-2xl border border-edge bg-canvas-raised',
        className,
      )}
      onPointerDown={(e) => {
        setDragging(true)
        updateFromClientX(e.clientX)
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- signed URLs must
          not pass through the Next image optimizer, which strips the query. */}
      <img src={after} alt={afterLabel} className="block w-full" draggable={false} />

      <div
        className="absolute inset-0 overflow-hidden"
        style={{ clipPath: `inset(0 ${100 - position}% 0 0)` }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={before} alt={beforeLabel} className="block w-full" draggable={false} />
      </div>

      <div
        className="absolute inset-y-0 w-0.5 bg-white/90 shadow-[0_0_12px_rgba(54,39,69,0.45)]"
        style={{ left: `${position}%` }}
      >
        <div
          className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize
                     rounded-full border-2 border-white bg-canvas/80 p-2 backdrop-blur"
          role="slider"
          tabIndex={0}
          aria-label="Comparison position"
          aria-valuenow={Math.round(position)}
          aria-valuemin={0}
          aria-valuemax={100}
          onKeyDown={(e) => {
            if (e.key === 'ArrowLeft') setPosition((p) => Math.max(0, p - 5))
            if (e.key === 'ArrowRight') setPosition((p) => Math.min(100, p + 5))
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5">
            <path d="M9 6L3 12l6 6M15 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
      </div>

      <span className="pointer-events-none absolute left-3 top-3 rounded-full bg-plum/70 px-2.5 py-1 text-[11px] font-medium text-white backdrop-blur">
        {beforeLabel}
      </span>
      <span className="pointer-events-none absolute right-3 top-3 rounded-full bg-plum/70 px-2.5 py-1 text-[11px] font-medium text-white backdrop-blur">
        {afterLabel}
      </span>
    </div>
  )
}
