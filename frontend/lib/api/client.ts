import type { z } from 'zod'

import { endpoints } from '@/lib/api/endpoints'
import { ApiError, ErrorCodes, parseApiErrorBody } from '@/lib/api/error'
import {
  clearSession,
  getAccessToken,
  getRefreshToken,
  setSession,
  toTokenPair,
} from '@/lib/auth/token-store'

const DEFAULT_API_URL = 'http://localhost:8000/api/v1'

function normalizeBaseUrl(value?: string): string {
  if (!value) {
    return DEFAULT_API_URL
  }
  return value.replace(/\/+$/, '')
}

export const API_BASE_URL = normalizeBaseUrl(
  process.env.NEXT_PUBLIC_API_URL ?? process.env.API_URL
)

let unauthorisedHandler: (() => void) | null = null

export function setUnauthorisedHandler(handler: (() => void) | null): void {
  unauthorisedHandler = handler
}

type HttpMethod = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'

interface RequestOptions {
  method?: HttpMethod
  path: string
  body?: unknown
  headers?: HeadersInit
  idempotencyKey?: string
  signal?: AbortSignal
}

function buildUrl(path: string): string {
  const hasLeadingSlash = path.startsWith('/')
  return `${API_BASE_URL}${hasLeadingSlash ? '' : '/'}${path}`
}

async function parseResponse(res: Response): Promise<unknown> {
  if (res.status === 204) {
    return undefined
  }
  const text = await res.text()
  if (!text) {
    return undefined
  }
  try {
    return JSON.parse(text) as unknown
  } catch {
    return text
  }
}

/**
 * Exchange the stored refresh token for a new pair and adopt it.
 *
 * The backend only exposes the admin-scoped `/auth/refresh`, so both token
 * kinds go through that route; a customer-specific refresh endpoint is on the
 * backend team's list (see `frontend-plan.md`, Phase 8 known gaps).
 */
async function attemptRefresh(): Promise<boolean> {
  const refresh = getRefreshToken()
  if (!refresh) return false
  try {
    const res = await fetch(`${API_BASE_URL}${endpoints.auth.refresh}`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh }),
    })
    if (!res.ok) {
      clearSession()
      return false
    }
    const rotated = toTokenPair(await res.json())
    if (!rotated) {
      clearSession()
      return false
    }
    setSession(rotated)
    return true
  } catch {
    clearSession()
    return false
  }
}

export class ResponseValidationError extends ApiError {
  readonly issues: z.ZodIssue[]

  constructor(issues: z.ZodIssue[]) {
    super(
      0,
      ErrorCodes.internal,
      'The API response did not match the expected schema.'
    )
    this.name = 'ResponseValidationError'
    this.issues = issues
  }
}

/**
 * `schema` and `refresh` live in the same object as the request options rather
 * than in a second parameter. They used to be read from a separate `config`
 * argument that no `api.*` helper ever passed, so every `schema` a caller
 * supplied was silently dropped and `refresh: false` was impossible - responses
 * came back unvalidated and a bare TypeScript generic was the only thing
 * standing between a decimal-string price from the API and `formatMoney`.
 */
interface RequestConfig extends RequestOptions {
  schema?: z.ZodType<unknown>
  refresh?: boolean
}

/** What callers pass: everything except the fields the helper supplies. */
type RequestOptions_ = Omit<RequestConfig, 'path' | 'method'>

async function request<T>(config: RequestConfig): Promise<T> {
  const {
    method = 'GET',
    path,
    body,
    headers,
    idempotencyKey,
    signal,
    schema,
    refresh,
  } = config

  const requestHeaders = new Headers(headers)
  requestHeaders.set('Content-Type', 'application/json')
  requestHeaders.set('X-Request-ID', crypto.randomUUID())
  if (idempotencyKey) {
    requestHeaders.set('Idempotency-Key', idempotencyKey)
  }
  // The backend authenticates with `Authorization: Bearer` only; the session
  // cookies exist for the Next route guard, not for the API. See
  // `lib/auth/session.ts`.
  const token = getAccessToken()
  if (token) {
    requestHeaders.set('Authorization', `Bearer ${token}`)
  }

  const res = await fetch(buildUrl(path), {
    method,
    headers: requestHeaders,
    credentials: 'include',
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  })

  const payload = await parseResponse(res)

  if (!res.ok) {
    const apiError =
      parseApiErrorBody(res.status, payload) ??
      new ApiError(
        res.status,
        ErrorCodes.internal,
        `Request failed with status ${res.status}`
      )

    if (res.status === 401 && refresh !== false) {
      const refreshed = await attemptRefresh()
      if (refreshed) {
        return request<T>({ ...config, refresh: false })
      }
      unauthorisedHandler?.()
    }

    throw apiError
  }

  if (schema) {
    const parsed = schema.safeParse(payload)
    if (!parsed.success) {
      throw new ResponseValidationError(parsed.error.issues)
    }
    return parsed.data as T
  }

  return payload as T
}

export const api = {
  get: <T>(path: string, config?: RequestOptions_) =>
    request<T>({ ...config, path, method: 'GET' }),

  post: <T>(path: string, body?: unknown, config?: RequestOptions_) =>
    request<T>({ ...config, path, method: 'POST', body }),

  patch: <T>(path: string, body?: unknown, config?: RequestOptions_) =>
    request<T>({ ...config, path, method: 'PATCH', body }),

  put: <T>(path: string, body?: unknown, config?: RequestOptions_) =>
    request<T>({ ...config, path, method: 'PUT', body }),

  del: <T>(path: string, config?: RequestOptions_) =>
    request<T>({ ...config, path, method: 'DELETE' }),
}

export type { RequestOptions }
