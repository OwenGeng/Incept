import { aiVideoApiBase } from '../runtime'
import { StudioFilesService } from './generated'

export type ProductAssetRole = 'truth_anchor' | 'standardized'
export type ProductAssetLifecycle = 'candidate' | 'selected'

export type ProductAsset = {
  id: string
  product_id: string
  file_id: string
  role: ProductAssetRole
  lifecycle: ProductAssetLifecycle
  source_asset_id?: string | null
  prompt: string
  input_fingerprint: string
  metadata_json: Record<string, unknown>
  created_at: string
  updated_at: string
}
export type Product = {
  id: string
  project_id: string
  name: string
  description: string
  claims: Array<Record<string, unknown>>
  prohibited_changes: string[]
  selected_asset_id?: string | null
  assets: ProductAsset[]
  created_at: string
  updated_at: string
}

type ApiEnvelope<T> = { data?: T | null; message?: string; detail?: string }

const productUrl = (projectId: string, suffix = '') =>
  `${aiVideoApiBase}/api/v1/studio/projects/${encodeURIComponent(projectId)}/products${suffix}`

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  const payload = (await response.json().catch(() => ({}))) as ApiEnvelope<T>
  if (!response.ok || payload.data == null) {
    throw new Error(payload.detail ?? payload.message ?? `Request failed (${response.status})`)
  }
  return payload.data
}

export const listProducts = (projectId: string) => request<Product[]>(productUrl(projectId))

export const createProduct = (
  projectId: string,
  body: { name: string; description?: string; claims?: Array<Record<string, unknown>>; prohibited_changes?: string[] },
) => request<Product>(productUrl(projectId), { method: 'POST', body: JSON.stringify(body) })

export const updateProduct = (
  projectId: string,
  productId: string,
  body: { name?: string; description?: string; claims?: Array<Record<string, unknown>>; prohibited_changes?: string[] },
) => request<Product>(productUrl(projectId, `/${encodeURIComponent(productId)}`), {
  method: 'PATCH',
  body: JSON.stringify(body),
})

export const addProductAsset = (
  projectId: string,
  productId: string,
  body: {
    file_id: string
    role: ProductAssetRole
    source_asset_id?: string | null
    prompt?: string
    metadata?: Record<string, unknown>
  },
) => request<ProductAsset>(productUrl(projectId, `/${encodeURIComponent(productId)}/assets`), {
  method: 'POST',
  body: JSON.stringify(body),
})

export const selectProductAsset = (projectId: string, productId: string, assetId: string) =>
  request<Product>(
    productUrl(projectId, `/${encodeURIComponent(productId)}/assets/${encodeURIComponent(assetId)}/select`),
    { method: 'POST', body: JSON.stringify({ selected_by: 'studio-user' }) },
  )

export async function uploadProductFile(projectId: string, file: File): Promise<string> {
  const response = await StudioFilesService.uploadFileApiApiV1StudioFilesUploadPost({
    formData: {
      file: file as unknown as string,
      project_id: projectId,
      usage_kind: 'asset_image',
      source_ref: 'product_asset',
    },
    name: file.name,
  })
  if (!response.data?.id) throw new Error('The uploaded file did not return an ID')
  return response.data.id
}
