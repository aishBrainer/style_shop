'use client'

/** §34 — projects group products, models, generations and creatives. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FolderOpen, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'

import { ApiError, api } from '@/lib/api'
import { formatRelative } from '@/lib/utils'
import { Button, Card, EmptyState, Field, Input, Modal, Skeleton, Textarea } from '@/components/ui'
import { useToast } from '@/components/ui/toast'

export default function ProjectsPage() {
  const toast = useToast()
  const queryClient = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.projects.list(),
  })

  const create = useMutation({
    mutationFn: () => api.projects.create(name.trim(), description.trim() || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      setCreating(false)
      setName('')
      setDescription('')
      toast.success('Project created')
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : 'Could not create the project'),
  })

  const remove = useMutation({
    mutationFn: (id: string) => api.projects.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      toast.success('Project deleted')
    },
  })

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h1 className="display text-2xl">Projects</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Group a collection&apos;s products, models and creatives together.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4" /> New project
        </Button>
      </header>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-40" />
          ))}
        </div>
      ) : !data?.items.length ? (
        <EmptyState
          icon={<FolderOpen className="h-8 w-8" />}
          title="No projects yet"
          description='Create one for each collection or campaign, e.g. "Summer Collection 2026".'
          action={<Button onClick={() => setCreating(true)}>Create a project</Button>}
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.items.map((project) => (
            <Card key={project.id} className="group flex flex-col">
              {project.cover_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={project.cover_url}
                  alt=""
                  className="mb-3 aspect-video w-full rounded-lg object-cover"
                />
              ) : (
                <div className="mb-3 grid aspect-video w-full place-items-center rounded-lg bg-canvas-overlay">
                  <FolderOpen className="h-6 w-6 text-ink-faint" />
                </div>
              )}

              <h2 className="text-sm font-medium">{project.name}</h2>
              {project.description && (
                <p className="mt-1 line-clamp-2 text-xs text-ink-muted">{project.description}</p>
              )}

              <div className="mt-3 flex items-center justify-between text-[11px] text-ink-faint">
                <span>
                  {project.asset_count} assets · {project.generation_count} generations
                </span>
                <span>{formatRelative(project.updated_at)}</span>
              </div>

              <button
                onClick={() => remove.mutate(project.id)}
                className="mt-3 flex items-center gap-1.5 self-start text-[11px] text-ink-faint opacity-0 transition hover:text-danger group-hover:opacity-100"
              >
                <Trash2 className="h-3 w-3" /> Delete
              </button>
            </Card>
          ))}
        </div>
      )}

      <Modal
        open={creating}
        onClose={() => setCreating(false)}
        title="New project"
        footer={
          <>
            <Button variant="ghost" onClick={() => setCreating(false)}>Cancel</Button>
            <Button
              onClick={() => create.mutate()}
              loading={create.isPending}
              disabled={!name.trim()}
            >
              Create
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Name">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Summer Collection 2026"
              autoFocus
            />
          </Field>
          <Field label="Description">
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="Optional"
            />
          </Field>
        </div>
      </Modal>
    </div>
  )
}
