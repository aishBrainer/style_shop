/**
 * API client.
 *
 * Requests go to a same-origin `/api/v1/...` path, which next.config.mjs
 * rewrites to FastAPI. That keeps the httpOnly session cookie in play without
 * any cross-origin negotiation.
 */

import type {
  Asset,
  AssetType,
  JobCreated,
  Job,
  ModelProfile,
  Page,
  Product,
  Project,
  Session,
  StudioOptions,
} from './types'

const BASE = '/api/v1'

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly details?: Record<string, unknown>,
  ) {
    super(message)
    this.name = 'ApiError'
  }

  /** Field-level messages from the 422 handler, for inline form errors. */
  get fieldErrors(): Record<string, string> {
    const fields = this.details?.fields
    return typeof fields === 'object' && fields !== null ? (fields as Record<string, string>) : {}
  }
}

let refreshInFlight: Promise<boolean> | null = null

async function refreshSession(): Promise<boolean> {
  // Collapse concurrent 401s into a single refresh — otherwise a page that
  // fires five queries at once would rotate the refresh token five times and
  // invalidate its own session.
  if (!refreshInFlight) {
    refreshInFlight = fetch(`${BASE}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    })
      .then((r) => r.ok)
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null
      })
  }
  return refreshInFlight
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown
  retryOn401?: boolean
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, retryOn401 = true, headers, ...rest } = options

  const isFormData = body instanceof FormData
  const response = await fetch(`${BASE}${path}`, {
    ...rest,
    credentials: 'include',
    headers: {
      ...(isFormData ? {} : body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...headers,
    },
    body: isFormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
  })

  // An expired access token is recoverable: refresh once, then replay.
  if (response.status === 401 && retryOn401 && !path.startsWith('/auth/')) {
    if (await refreshSession()) {
      return request<T>(path, { ...options, retryOn401: false })
    }
  }

  if (!response.ok) {
    let code = 'REQUEST_FAILED'
    let message = `Request failed (${response.status})`
    let details: Record<string, unknown> | undefined

    try {
      const payload = await response.json()
      if (payload?.error) {
        code = payload.error.code ?? code
        message = payload.error.message ?? message
        details = payload.error.details
      }
    } catch {
      // Non-JSON error body (a proxy timeout page, say) — keep the generic text.
    }

    throw new ApiError(message, response.status, code, details)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

const get = <T>(path: string) => request<T>(path)
const post = <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body })
const patch = <T>(path: string, body?: unknown) => request<T>(path, { method: 'PATCH', body })
const put = <T>(path: string, body?: unknown) => request<T>(path, { method: 'PUT', body })
const del = <T>(path: string) => request<T>(path, { method: 'DELETE' })

function query(params: Record<string, unknown>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const s = search.toString()
  return s ? `?${s}` : ''
}

export const api = {
  auth: {
    session: () => get<Session>('/auth/session'),
    login: (email: string, password: string) => post<Session>('/auth/login', { email, password }),
    register: (email: string, password: string, full_name?: string) =>
      post<Session>('/auth/register', { email, password, full_name }),
    logout: () => post<{ message: string }>('/auth/logout'),
    updateProfile: (full_name: string) => patch<unknown>('/auth/profile', { full_name }),
    forgotPassword: (email: string) => post<{ message: string }>('/auth/password/forgot', { email }),
    resetPassword: (token: string, password: string) =>
      post<{ message: string }>('/auth/password/reset', { token, password }),
    changePassword: (current_password: string, new_password: string) =>
      post<{ message: string }>('/auth/password/change', { current_password, new_password }),
    verifyEmail: (token: string) => post<{ message: string }>('/auth/verify-email/confirm', { token }),
    requestVerification: () => post<{ message: string }>('/auth/verify-email/request'),
    deleteAccount: (confirm: string, password?: string) =>
      post<{ message: string }>('/auth/delete-account', { confirm, password }),
  },

  assets: {
    list: (params: { type?: AssetType; project_id?: string; page?: number; page_size?: number } = {}) =>
      get<Page<Asset>>(`/assets${query(params)}`),
    get: (id: string) => get<Asset>(`/assets/${id}`),
    upload: async (file: File, type: AssetType = 'product', projectId?: string) => {
      const form = new FormData()
      form.append('file', file)
      form.append('type', type)
      if (projectId) form.append('project_id', projectId)
      return request<Asset>('/assets', { method: 'POST', body: form })
    },
    uploadMask: (imageBase64: string, projectId?: string) =>
      post<Asset>('/assets/mask', { image_base64: imageBase64, project_id: projectId }),
    update: (id: string, body: { is_favourite?: boolean; project_id?: string; filename?: string }) =>
      patch<Asset>(`/assets/${id}`, body),
    downloadUrl: (id: string, variant: 'original' | 'preview' | 'thumbnail' = 'original') =>
      get<{ url: string; filename: string; expires_in: number }>(
        `/assets/${id}/download${query({ variant })}`,
      ),
    remove: (id: string) => del<{ message: string }>(`/assets/${id}`),
  },

  projects: {
    list: (params: { include_archived?: boolean; page?: number } = {}) =>
      get<Page<Project>>(`/projects${query(params)}`),
    get: (id: string) => get<Project>(`/projects/${id}`),
    create: (name: string, description?: string) => post<Project>('/projects', { name, description }),
    update: (id: string, body: Partial<Project>) => patch<Project>(`/projects/${id}`, body),
    remove: (id: string) => del<{ message: string }>(`/projects/${id}`),
  },

  products: {
    list: (params: { project_id?: string; search?: string; page?: number } = {}) =>
      get<Page<Product>>(`/products${query(params)}`),
    get: (id: string) => get<Product>(`/products/${id}`),
    create: (body: { name: string; image_asset_id: string; project_id?: string; sku?: string }) =>
      post<Product>('/products', body),
    update: (id: string, body: Partial<Product>) => patch<Product>(`/products/${id}`, body),
    remove: (id: string) => del<{ message: string }>(`/products/${id}`),
  },

  models: {
    list: (params: Record<string, unknown> = {}) => get<Page<ModelProfile>>(`/models${query(params)}`),
    create: (body: { name: string; image_asset_id: string; gender?: string; body_type?: string }) =>
      post<ModelProfile>('/models', body),
    update: (id: string, body: Partial<ModelProfile>) => patch<ModelProfile>(`/models/${id}`, body),
    remove: (id: string) => del<{ message: string }>(`/models/${id}`),
  },

  studio: {
    options: () => get<StudioOptions>('/studio/options'),
    credits: () => get<{ balance: number; plan: string; consumed_30d: number; granted_30d: number; transactions: unknown[] }>('/credits'),
    usage: (days = 30) => get<Record<string, unknown>>(`/usage${query({ days })}`),
  },

  jobs: {
    list: (params: { type?: string; status?: string; project_id?: string; page?: number } = {}) =>
      get<Page<Job>>(`/jobs${query(params)}`),
    get: (id: string) => get<Job>(`/jobs/${id}`),
    cancel: (id: string) => post<Job>(`/jobs/${id}/cancel`),
    retry: (id: string) => post<Job>(`/jobs/${id}/retry`),
    creations: (params: { project_id?: string; page?: number } = {}) =>
      get<Page<Job>>(`/creations${query(params)}`),
  },

  generate: {
    vton: (body: Record<string, unknown>) => post<JobCreated>('/vton/jobs', body),
    vtonBulk: (body: Record<string, unknown>) =>
      post<{ batch_id: string; job_ids: string[]; credits_cost: number }>('/vton/bulk', body),
    removeBackground: (body: Record<string, unknown>) => post<JobCreated>('/background/remove', body),
    replaceBackground: (body: Record<string, unknown>) => post<JobCreated>('/background/replace', body),
    photography: (body: Record<string, unknown>) => post<JobCreated>('/photography/jobs', body),
    inpaint: (body: Record<string, unknown>) => post<JobCreated>('/edit/inpaint', body),
    removeObject: (body: Record<string, unknown>) => post<JobCreated>('/edit/remove-object', body),
    expand: (body: Record<string, unknown>) => post<JobCreated>('/edit/expand', body),
    upscale: (body: Record<string, unknown>) => post<JobCreated>('/upscale/jobs', body),
    enhance: (body: Record<string, unknown>) => post<JobCreated>('/edit/enhance', body),
  },

  brandKit: {
    get: () => get<Record<string, unknown> | null>('/brand-kit'),
    save: (body: Record<string, unknown>) => put<Record<string, unknown>>('/brand-kit', body),
  },

  admin: {
    stats: () => get<Record<string, unknown>>('/admin/stats'),
    users: (params: Record<string, unknown> = {}) => get<Page<Record<string, unknown>>>(`/admin/users${query(params)}`),
    blockUser: (id: string, blocked: boolean, reason?: string) =>
      post<unknown>(`/admin/users/${id}/block`, { blocked, reason }),
    organizations: (params: Record<string, unknown> = {}) =>
      get<Page<Record<string, unknown>>>(`/admin/organizations${query(params)}`),
    jobs: (params: Record<string, unknown> = {}) => get<Page<Record<string, unknown>>>(`/admin/jobs${query(params)}`),
    workers: () => get<Record<string, unknown>[]>('/admin/workers'),
    models: () => get<Record<string, unknown>[]>('/admin/models'),
    toggleModel: (id: string, enabled: boolean) => post<unknown>(`/admin/models/${id}/toggle`, { enabled }),
    flags: () => get<Record<string, unknown>[]>('/admin/feature-flags'),
    updateFlag: (key: string, body: Record<string, unknown>) => patch<unknown>(`/admin/feature-flags/${key}`, body),
    auditLogs: (params: Record<string, unknown> = {}) => get<Page<Record<string, unknown>>>(`/admin/audit-logs${query(params)}`),
  },
}
