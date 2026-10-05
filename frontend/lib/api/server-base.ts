/**
 * Base URL for fetches issued from the server (RSC, route handlers, metadata).
 *
 * The browser may address the API relatively — `/api/v1` — when the app is
 * served behind the same-origin proxy in `next.config.ts` (see `API_PROXY_TARGET`).
 * That is a transport detail the browser understands and `fetch` on the server
 * does not: a relative URL has no origin to resolve against during static
 * generation, so prerendering the landing page would hang and retry.
 *
 * So the two environments resolve the base independently:
 *
 *   server  -> `API_URL`, then `NEXT_PUBLIC_API_URL`, then the local default
 *   browser -> `NEXT_PUBLIC_API_URL`, then `API_URL`, then the local default
 *
 * `API_URL` is deliberately absent from the client bundle, which is what makes
 * it safe to keep a server-only absolute origin here.
 */
const DEFAULT_API_URL = 'http://localhost:8000/api/v1'

function normalize(value: string): string {
  return value.replace(/\/+$/, '')
}

function isAbsolute(value: string): boolean {
  return /^https?:\/\//i.test(value)
}

export function serverApiBaseUrl(): string {
  const candidate =
    process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_URL
  if (isAbsolute(candidate)) {
    return normalize(candidate)
  }
  // A relative `NEXT_PUBLIC_API_URL` cannot be fetched from the server, so fall
  // back to the default origin rather than issuing a request that cannot resolve.
  return normalize(DEFAULT_API_URL)
}
