import { serverApiBaseUrl } from '@/lib/api/server-base'
import { endpoints } from '@/lib/api/endpoints'
import {
  serviceListPageSchema,
  serviceSchema,
  type Service,
} from '@/features/services/schema'

const REVALIDATE_SECONDS = 60

// Resolved per call rather than at module load so a build-time value cannot be
// captured before the env is read.
const apiBase = serverApiBaseUrl()

type ApiResponse<T> =
  { ok: true; payload: T } | { ok: false; status: number; error: string }

async function getFromApi<T>(url: string): Promise<ApiResponse<T>> {
  try {
    const res = await fetch(url, { next: { revalidate: REVALIDATE_SECONDS } })
    if (!res.ok) {
      return {
        ok: false,
        status: res.status,
        error: `Request failed with status ${res.status}`,
      }
    }
    return { ok: true, payload: (await res.json()) as T }
  } catch {
    return { ok: false, status: 0, error: 'Unable to reach the services API.' }
  }
}

export type ServicesResult =
  { ok: true; services: Service[] } | { ok: false; error: string }

export async function getActiveServices(): Promise<ServicesResult> {
  const url = `${apiBase}${endpoints.services.list({ status: 'active' })}`
  const res = await getFromApi<unknown>(url)
  if (!res.ok) {
    return { ok: false, error: res.error }
  }

  const parsed = serviceListPageSchema.safeParse(res.payload)
  if (!parsed.success) {
    return {
      ok: false,
      error: 'The services API returned an unexpected shape.',
    }
  }

  return { ok: true, services: parsed.data.results }
}

export type ServiceDetailResult =
  | { status: 'ok'; service: Service }
  | { status: 'not_found' }
  | { status: 'unavailable'; error: string }

export async function getServiceBySlug(
  slug: string
): Promise<ServiceDetailResult> {
  const url = `${apiBase}${endpoints.services.detail(slug)}`
  const res = await getFromApi<unknown>(url)
  if (!res.ok) {
    if (res.status === 404) {
      return { status: 'not_found' }
    }
    return { status: 'unavailable', error: res.error }
  }

  const parsed = serviceSchema.safeParse(res.payload)
  if (!parsed.success) {
    return {
      status: 'unavailable',
      error: 'The service API returned an unexpected shape.',
    }
  }

  return { status: 'ok', service: parsed.data }
}
