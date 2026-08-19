'use client'

import { useQuery, useQueryClient, type UseQueryOptions } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'

import { api } from './api'
import { TERMINAL_STATUSES, type Job, type JobStatus, type Session, type StudioOptions } from './types'

export function useSession(options?: Partial<UseQueryOptions<Session>>) {
  return useQuery({
    queryKey: ['session'],
    queryFn: () => api.auth.session(),
    // An anonymous visitor gets a 401; retrying that three times just delays
    // the redirect to /login.
    retry: false,
    staleTime: 60_000,
    ...options,
  })
}

export function useStudioOptions() {
  return useQuery<StudioOptions>({
    queryKey: ['studio-options'],
    queryFn: () => api.studio.options(),
    staleTime: 5 * 60_000,
  })
}

/**
 * §57 — live job progress over SSE.
 *
 * One EventSource for the whole app: the API publishes to a per-user channel,
 * so a socket per job would be pure waste. Falls back to polling if the stream
 * cannot be established (a proxy that buffers, a corporate network, …), which
 * keeps the studio usable rather than silently stuck at 0%.
 */
export function useJobStream(onEvent?: (event: string, job: Partial<Job> & { job_id: string }) => void) {
  const queryClient = useQueryClient()
  const [connected, setConnected] = useState(false)
  const handlerRef = useRef(onEvent)
  handlerRef.current = onEvent

  useEffect(() => {
    if (typeof window === 'undefined' || typeof EventSource === 'undefined') return

    const source = new EventSource('/api/v1/events', { withCredentials: true })
    let closed = false

    const handle = (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data)
        const jobId: string | undefined = payload.job_id
        if (!jobId) return

        // Only carry across the fields the event actually supplied; spreading
        // undefined values would blank out good cached data.
        const patch: Partial<Job> = {}
        const status = payload.data?.status as JobStatus | undefined
        if (status) patch.status = status
        if (typeof payload.data?.progress === 'number') patch.progress = payload.data.progress
        if ('stage' in (payload.data ?? {})) patch.stage_label = payload.data.stage ?? null

        // Update the cached job in place so any mounted progress bar moves
        // without waiting for a refetch.
        queryClient.setQueryData<Job>(['job', jobId], (prev) =>
          prev ? { ...prev, ...patch } : prev,
        )

        // Terminal states carry results we do not have — refetch those.
        if (status && TERMINAL_STATUSES.includes(status)) {
          queryClient.invalidateQueries({ queryKey: ['job', jobId] })
          queryClient.invalidateQueries({ queryKey: ['jobs'] })
          queryClient.invalidateQueries({ queryKey: ['creations'] })
          queryClient.invalidateQueries({ queryKey: ['credits'] })
        }

        handlerRef.current?.(payload.event, { ...patch, job_id: jobId })
      } catch {
        // A malformed frame is not worth tearing the stream down for.
      }
    }

    source.addEventListener('connected', () => setConnected(true))
    for (const name of [
      'job.created',
      'job.queued',
      'job.processing',
      'job.progress',
      'job.completed',
      'job.failed',
      'job.cancelled',
      'job.validating',
      'job.preprocessing',
      'job.post_processing',
      'job.uploading',
    ]) {
      source.addEventListener(name, handle as EventListener)
    }

    source.onerror = () => {
      setConnected(false)
      // EventSource reconnects on its own; closing here would defeat that.
      if (source.readyState === EventSource.CLOSED) closed = true
    }

    return () => {
      closed = true
      source.close()
      setConnected(false)
    }
  }, [queryClient])

  return { connected }
}

/**
 * Watch a single job to completion.
 *
 * Polls as a backstop even when SSE is connected — at a slow interval, because
 * a dropped event should cost the user a few seconds, not leave the UI stuck
 * on "processing" forever.
 */
export function useJob(jobId: string | null, { enabled = true } = {}) {
  return useQuery<Job>({
    queryKey: ['job', jobId],
    queryFn: () => api.jobs.get(jobId as string),
    enabled: Boolean(jobId) && enabled,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (!status) return 2000
      return TERMINAL_STATUSES.includes(status) ? false : 4000
    },
  })
}

/** Tracks a set of jobs the user just launched, e.g. a bulk batch (§39). */
export function useJobQueue() {
  const [jobIds, setJobIds] = useState<string[]>([])

  const track = useCallback((ids: string | string[]) => {
    setJobIds((prev) => {
      const next = Array.isArray(ids) ? ids : [ids]
      return [...new Set([...next, ...prev])].slice(0, 50)
    })
  }, [])

  const clear = useCallback(() => setJobIds([]), [])

  return { jobIds, track, clear }
}

/** Prevents an object URL leak when a preview image is replaced. */
export function useObjectUrl(file: File | null): string | null {
  const [url, setUrl] = useState<string | null>(null)

  useEffect(() => {
    if (!file) {
      setUrl(null)
      return
    }
    const objectUrl = URL.createObjectURL(file)
    setUrl(objectUrl)
    return () => URL.revokeObjectURL(objectUrl)
  }, [file])

  return url
}
