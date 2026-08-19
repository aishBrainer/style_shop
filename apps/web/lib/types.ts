/** Mirrors the FastAPI schemas. Kept hand-written and small rather than
 *  generated, so the surface the UI depends on stays visible. */

export type JobStatus =
  | 'queued'
  | 'validating'
  | 'preprocessing'
  | 'processing'
  | 'post_processing'
  | 'uploading'
  | 'completed'
  | 'failed'
  | 'cancelled'

export type JobType =
  | 'vton'
  | 'background_remove'
  | 'background_replace'
  | 'product_photography'
  | 'upscale'
  | 'inpaint'
  | 'object_remove'
  | 'expand'
  | 'enhance'
  | 'model_swap'
  | 'pose'
  | 'video'
  | 'ad_creative'

export type GarmentCategory =
  | 'upper_body'
  | 'lower_body'
  | 'full_body'
  | 'outerwear'
  | 'dress'
  | 'jumpsuit'
  | 'other'

export type AssetType =
  | 'product'
  | 'model'
  | 'generated_image'
  | 'generated_video'
  | 'logo'
  | 'brand_asset'
  | 'mask'
  | 'thumbnail'

export type PlanTier = 'free' | 'pro' | 'business'

export const TERMINAL_STATUSES: JobStatus[] = ['completed', 'failed', 'cancelled']

export interface Asset {
  id: string
  type: AssetType
  status: string
  filename: string
  mime_type: string
  size_bytes: number
  width: number | null
  height: number | null
  project_id: string | null
  is_favourite: boolean
  has_watermark: boolean
  ai_model_key: string | null
  generation_job_id: string | null
  generation_params: Record<string, unknown> | null
  created_at: string
  url: string | null
  preview_url: string | null
  thumbnail_url: string | null
}

export interface Job {
  id: string
  type: JobType
  status: JobStatus
  progress: number
  stage_label: string | null
  project_id: string | null
  batch_id: string | null
  params: Record<string, unknown>
  seed: number | null
  ai_model_key: string | null
  output_asset_ids: string[] | null
  primary_output_asset_id: string | null
  error_code: string | null
  error_message: string | null
  retry_count: number
  max_retries: number
  credits_cost: number
  duration_ms: number | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  outputs: Asset[]
  queue_position: number | null
  estimated_seconds: number | null
}

export interface JobCreated {
  job_id: string
  status: JobStatus
  queue_position: number | null
  estimated_seconds: number | null
  credits_cost: number
  credits_remaining: number
}

export interface Organization {
  id: string
  name: string
  slug: string
  plan: PlanTier
  credit_balance: number
  storage_quota_mb: number
  storage_used_bytes: number
  max_projects: number
  max_concurrent_jobs: number
  is_personal: boolean
}

export interface User {
  id: string
  email: string
  full_name: string | null
  avatar_url: string | null
  role: 'user' | 'admin'
  is_active: boolean
  email_verified_at: string | null
  default_organization_id: string | null
  created_at: string
}

export interface Session {
  user: User
  organization: Organization
  memberships: { id: string; organization_id: string; role: string; organization: Organization | null }[]
}

export interface Project {
  id: string
  name: string
  description: string | null
  is_archived: boolean
  cover_asset_id: string | null
  created_at: string
  updated_at: string
  cover_url: string | null
  asset_count: number
  generation_count: number
}

export interface Product {
  id: string
  name: string
  sku: string | null
  description: string | null
  category: GarmentCategory | null
  category_confidence: number | null
  bounding_box: number[] | null
  project_id: string | null
  image_asset_id: string
  mask_asset_id: string | null
  analysis: Record<string, unknown> | null
  created_at: string
  image: Asset | null
}

export interface ModelProfile {
  id: string
  name: string
  organization_id: string | null
  image_asset_id: string
  gender: string | null
  age_group: string | null
  body_type: string | null
  pose: string | null
  style: string | null
  collection: string | null
  tags: string[] | null
  is_active: boolean
  is_builtin: boolean
  validation: { acceptable?: boolean; reasons?: string[]; message?: string } | null
  created_at: string
  image: Asset | null
}

export interface Preset {
  key: string
  label: string
  prompt: string | null
  preview_url: string | null
}

export interface StudioOptions {
  garment_categories: Preset[]
  background_presets: Preset[]
  lighting: Preset[]
  camera: Preset[]
  composition: Preset[]
  model_filters: Record<string, string[]>
  poses: Preset[]
  credit_costs: Record<string, number>
  features: Record<string, boolean>
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: Record<string, unknown> }
}
