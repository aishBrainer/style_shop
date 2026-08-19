'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Boxes, Plus } from 'lucide-react'
import { useState } from 'react'

import { ApiError, api } from '@/lib/api'
import type { Asset } from '@/lib/types'
import { formatRelative, titleCase } from '@/lib/utils'
import { Badge, Button, Card, EmptyState, Field, Input, Modal, Skeleton } from '@/components/ui'
import { useToast } from '@/components/ui/toast'
import { UploadZone } from '@/components/studio/upload-zone'

export default function ProductsPage() {
  const toast = useToast()
  const queryClient = useQueryClient()

  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [sku, setSku] = useState('')
  const [asset, setAsset] = useState<Asset | null>(null)
  const [search, setSearch] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['products', search],
    queryFn: () => api.products.list({ search: search || undefined }),
  })

  const create = useMutation({
    mutationFn: () =>
      api.products.create({
        name: name.trim(),
        image_asset_id: asset!.id,
        sku: sku.trim() || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] })
      setAdding(false)
      setName('')
      setSku('')
      setAsset(null)
      // §10 — category detection runs asynchronously on the CPU queue.
      toast.success('Product added', 'We are detecting the garment category now.')
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : 'Could not add the product'),
  })

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="display text-2xl">Products</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Your garment catalogue. Upload once, reuse across every generation.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name or SKU"
            className="h-10 w-52"
          />
          <Button onClick={() => setAdding(true)}>
            <Plus className="h-4 w-4" /> Add product
          </Button>
        </div>
      </header>

      {isLoading ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          {Array.from({ length: 10 }).map((_, i) => (
            <Skeleton key={i} className="aspect-[3/4]" />
          ))}
        </div>
      ) : !data?.items.length ? (
        <EmptyState
          icon={<Boxes className="h-8 w-8" />}
          title="No products yet"
          description="Add a garment photo to start generating with it."
          action={<Button onClick={() => setAdding(true)}>Add your first product</Button>}
        />
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          {data.items.map((product) => (
            <Card key={product.id} className="!p-3">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={product.image?.thumbnail_url ?? product.image?.preview_url ?? ''}
                alt={product.name}
                className="checkerboard mb-2.5 aspect-square w-full rounded-lg object-contain"
                loading="lazy"
              />
              <p className="truncate text-sm">{product.name}</p>
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                {product.category ? (
                  <Badge tone="accent">{titleCase(product.category)}</Badge>
                ) : (
                  <Badge>Analysing…</Badge>
                )}
              </div>
              <p className="mt-1.5 text-[11px] text-ink-faint">
                {product.sku ? `${product.sku} · ` : ''}
                {formatRelative(product.created_at)}
              </p>
            </Card>
          ))}
        </div>
      )}

      <Modal
        open={adding}
        onClose={() => setAdding(false)}
        title="Add a product"
        footer={
          <>
            <Button variant="ghost" onClick={() => setAdding(false)}>Cancel</Button>
            <Button
              onClick={() => create.mutate()}
              loading={create.isPending}
              disabled={!name.trim() || !asset}
            >
              Add
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <UploadZone
            label="Product photo"
            assetType="product"
            value={asset}
            onChange={setAsset}
            className="max-w-[220px]"
          />
          <Field label="Name">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Linen Shirt" />
          </Field>
          <Field label="SKU" hint="Optional.">
            <Input value={sku} onChange={(e) => setSku(e.target.value)} placeholder="LS-001" />
          </Field>
        </div>
      </Modal>
    </div>
  )
}
