'use client'

/** §32 — brand settings reused by every generated creative. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { ApiError, api } from '@/lib/api'
import { Button, Card, Field, Input, Textarea } from '@/components/ui'
import { useToast } from '@/components/ui/toast'

interface BrandKitForm {
  name: string
  primary_color: string
  secondary_color: string
  accent_color: string
  heading_font: string
  body_font: string
  brand_tone: string
  cta_style: string
  product_positioning: string
}

const EMPTY: BrandKitForm = {
  name: 'Default',
  primary_color: '#7C5CFF',
  secondary_color: '#111219',
  accent_color: '#3ECF8E',
  heading_font: '',
  body_font: '',
  brand_tone: '',
  cta_style: '',
  product_positioning: '',
}

export default function BrandKitPage() {
  const toast = useToast()
  const queryClient = useQueryClient()
  const [form, setForm] = useState<BrandKitForm>(EMPTY)

  const { data, isLoading } = useQuery({
    queryKey: ['brand-kit'],
    queryFn: () => api.brandKit.get(),
  })

  useEffect(() => {
    if (data) setForm({ ...EMPTY, ...(data as Partial<BrandKitForm>) })
  }, [data])

  const save = useMutation({
    mutationFn: () => api.brandKit.save(form as unknown as Record<string, unknown>),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['brand-kit'] })
      toast.success('Brand kit saved')
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : 'Could not save'),
  })

  function set<K extends keyof BrandKitForm>(key: K, value: BrandKitForm[K]) {
    setForm((f) => ({ ...f, [key]: value }))
  }

  return (
    <div className="mx-auto max-w-3xl">
      <header className="mb-6">
        <h1 className="display text-2xl">Brand Kit</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Saved once, applied to every creative you generate.
        </p>
      </header>

      <Card className="space-y-5">
        <Field label="Kit name">
          <Input value={form.name} onChange={(e) => set('name', e.target.value)} />
        </Field>

        <div className="grid gap-4 sm:grid-cols-3">
          <ColorField label="Primary" value={form.primary_color} onChange={(v) => set('primary_color', v)} />
          <ColorField label="Secondary" value={form.secondary_color} onChange={(v) => set('secondary_color', v)} />
          <ColorField label="Accent" value={form.accent_color} onChange={(v) => set('accent_color', v)} />
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Heading font">
            <Input
              value={form.heading_font}
              onChange={(e) => set('heading_font', e.target.value)}
              placeholder="Inter"
            />
          </Field>
          <Field label="Body font">
            <Input
              value={form.body_font}
              onChange={(e) => set('body_font', e.target.value)}
              placeholder="Inter"
            />
          </Field>
        </div>

        <Field label="Brand tone" hint="How copy should sound.">
          <Input
            value={form.brand_tone}
            onChange={(e) => set('brand_tone', e.target.value)}
            placeholder="Confident, minimal, understated"
          />
        </Field>

        <Field label="CTA style">
          <Input
            value={form.cta_style}
            onChange={(e) => set('cta_style', e.target.value)}
            placeholder="Shop now"
          />
        </Field>

        <Field label="Product positioning">
          <Textarea
            value={form.product_positioning}
            onChange={(e) => set('product_positioning', e.target.value)}
            rows={3}
            placeholder="Premium everyday basics for people who care about fabric."
          />
        </Field>

        <div className="flex justify-end">
          <Button onClick={() => save.mutate()} loading={save.isPending} disabled={isLoading}>
            Save brand kit
          </Button>
        </div>
      </Card>
    </div>
  )
}

function ColorField({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <Field label={label}>
      <div className="flex items-center gap-2">
        <input
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
          className="h-10 w-12 shrink-0 cursor-pointer rounded-lg border border-edge bg-canvas"
        />
        <Input value={value} onChange={(e) => onChange(e.target.value.toUpperCase())} />
      </div>
    </Field>
  )
}
