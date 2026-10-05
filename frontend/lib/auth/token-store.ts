import { SESSION_COOKIES } from '@/lib/auth/cookies'

/**
 * Browser-side session store.
 *
 * The backend answers `auth/admin/login` and `auth/otp/verify` with
 * `{ access, refresh, ... }` in the JSON body and sets no cookie, and it
 * authenticates with `Authorization: Bearer` only - a cookie carrying
 * `access_token` is rejected by `AdminJWTAuthentication`. The browser therefore
 * has to hold the pair itself and do three things with it:
 *
 *  1. attach `Authorization: Bearer <access>` to every API call,
 *  2. mirror the pair into the `access_token` / `refresh_token` cookies, because
 *     `middleware.ts` decides route access from cookies alone and server
 *     components call `getSession()`, which forwards them to `/auth/me`,
 *  3. hand a rotated pair back after a refresh.
 *
 * The cookies are deliberately *not* `HttpOnly`: the module that owns them has
 * to overwrite them after a refresh. That is acceptable because the access
 * token is only ever sent back to our own API as a bearer header and is never
 * rendered into a page. A `HttpOnly` cookie would be the stronger choice, but it
 * would require the backend to own cookie issuance, and that is its call.
 *
 * Cookie scope: the API origin differs from the app origin by port only
 * (`localhost:3398` -> `localhost:3399`) and cookies are host-scoped with no
 * port component, so a cookie set from the app origin is also sent to the API.
 */

export interface TokenPair {
  access: string
  refresh: string
}

const ACCESS_TOKEN_MAX_AGE_SECONDS = 60 * 60
const REFRESH_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 30

let accessToken: string | null = null
let refreshToken: string | null = null

function cookieAttributes(): string {
  const secure = window.location.protocol === 'https:' ? '; Secure' : ''
  return `path=/; SameSite=Lax${secure}`
}

function writeCookie(name: string, value: string, maxAge: number): void {
  document.cookie = `${name}=${encodeURIComponent(value)}; ${cookieAttributes()}; max-age=${maxAge}`
}

function clearCookie(name: string): void {
  document.cookie = `${name}=; ${cookieAttributes()}; max-age=0`
}

export function readCookie(name: string): string | null {
  const match = new RegExp(`(?:^|; )${name}=([^;]*)`).exec(document.cookie)
  return match ? decodeURIComponent(match[1]) : null
}

/** Adopt a token pair and mirror it into the cookies the route guard reads. */
export function setSession(pair: TokenPair): void {
  accessToken = pair.access
  refreshToken = pair.refresh
  writeCookie(SESSION_COOKIES[0], pair.access, ACCESS_TOKEN_MAX_AGE_SECONDS)
  writeCookie(SESSION_COOKIES[1], pair.refresh, REFRESH_TOKEN_MAX_AGE_SECONDS)
}

export function getAccessToken(): string | null {
  if (accessToken) return accessToken
  // Rehydrate after a full page load, where module scope is gone but the
  // cookie survives.
  accessToken = readCookie(SESSION_COOKIES[0])
  return accessToken
}

export function getRefreshToken(): string | null {
  if (refreshToken) return refreshToken
  refreshToken = readCookie(SESSION_COOKIES[1])
  return refreshToken
}

export function clearSession(): void {
  accessToken = null
  refreshToken = null
  for (const name of SESSION_COOKIES) clearCookie(name)
}

/** Narrow an unknown auth response body to a token pair. */
export function toTokenPair(payload: unknown): TokenPair | null {
  if (
    typeof payload === 'object' &&
    payload !== null &&
    'access' in payload &&
    'refresh' in payload &&
    typeof (payload as TokenPair).access === 'string' &&
    typeof (payload as TokenPair).refresh === 'string'
  ) {
    return payload as TokenPair
  }
  return null
}
