#!/usr/bin/env node
/**
 * Test-harness API proxy. Not part of the application.
 *
 * The browser reaches the backend cross-origin, which requires the backend to
 * send CORS headers. Two things make that unusable as a test fixture today:
 *
 *   1. The backend now emits CORS headers itself (`corsheaders` is wired into
 *      `INSTALLED_APPS`/`MIDDLEWARE` in `config/settings/base.py`, scoped to
 *      `/api/`), so this proxy no longer has to invent them. It keeps its own
 *      headers only because the Playwright origin is not on the backend's
 *      allowlist.
 *   2. The API mixes DRF router routes, which require a trailing slash, with
 *      hand-written routes that take none (`/availability/slots`). Any proxy in
 *      front has to preserve the caller's exact path.
 *
 * This sits on its own port in front of the backend, adds the CORS headers the
 * browser needs, and forwards the path untouched. The frontend is built with
 * `NEXT_PUBLIC_API_URL` pointing here, so the Lighthouse gate and the Playwright
 * suite both drive a working stack without changing any application code.
 *
 * Usage:
 *   node scripts/test-api-proxy.mjs                 # listens on TEST_PROXY_PORT
 *   TEST_PROXY_TARGET=http://localhost:8000 \
 *   TEST_PROXY_PORT=3399 node scripts/test-api-proxy.mjs
 */
import { createServer } from 'node:http'

const TARGET = (process.env.TEST_PROXY_TARGET ?? 'http://localhost:8000').replace(
  /\/+$/,
  ''
)
const PORT = Number(process.env.TEST_PROXY_PORT ?? 3399)
/** Origin allowed to make credentialed requests. Mirrors the frontend's dev origin. */
const ALLOWED_ORIGIN = process.env.TEST_PROXY_ALLOWED_ORIGIN ?? 'http://localhost:3000'

/** Hop-by-hop headers that must not be forwarded in either direction. */
const HOP_BY_HOP = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
  'host',
  'content-length',
])

function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': ALLOWED_ORIGIN,
    'Access-Control-Allow-Credentials': 'true',
    'Access-Control-Allow-Headers':
      'Content-Type, Authorization, X-Request-ID, Idempotency-Key, X-Tenant-Slug',
    'Access-Control-Allow-Methods': 'GET, POST, PATCH, PUT, DELETE, OPTIONS',
    'Access-Control-Max-Age': '600',
  }
}

function forward(url, req, headers, body) {
  return fetch(url, {
    method: req.method,
    headers,
    body,
    redirect: 'manual',
  })
}

/** Insert a trailing slash on the path, leaving any query string intact. */
/**
 * Append a trailing slash to the *path* only, and never when it already has
 * one - `/services/?status=active` must not become `/services//?status=active`,
 * which the backend answers 404 and which would otherwise turn one missing
 * slash into an infinite retry.
 */
function withTrailingSlash(url) {
  const queryAt = url.indexOf('?')
  const path = queryAt === -1 ? url : url.slice(0, queryAt)
  if (path.endsWith('/')) return url
  const slashed = `${path}/`
  return queryAt === -1 ? slashed : `${slashed}${url.slice(queryAt)}`
}

const server = createServer(async (req, res) => {
  if (req.method === 'OPTIONS') {
    res.writeHead(204, corsHeaders())
    res.end()
    return
  }

  const chunks = []
  for await (const chunk of req) {
    chunks.push(chunk)
  }
  const body = chunks.length ? Buffer.concat(chunks) : undefined

  const headers = {}
  for (const [key, value] of Object.entries(req.headers)) {
    if (!HOP_BY_HOP.has(key.toLowerCase()) && value !== undefined) {
      headers[key] = value
    }
  }
  // Django resolves the tenant from the host, and an IP host parses as a slug
  // ("127" from 127.0.0.1). Forward a name so the default tenant is used.
  headers.host = new URL(TARGET).host

  try {
    let upstream = await forward(`${TARGET}${req.url}`, req, headers, body)

    // Contract deviation, not a test convenience: backend-plan.md §4 specifies
    // `GET /services?status=active` and `GET /services/{slug}` with no trailing
    // slash, and the frontend calls exactly that. The backend mounts those on a
    // DRF router, which requires one, so the documented path 404s. Retry with a
    // slash so the suite exercises the real page, and so the mismatch is visible
    // here rather than as a silently empty landing page.
    if (upstream.status === 404 && !req.url.endsWith('/')) {
      const retried = withTrailingSlash(req.url)
      upstream = await forward(`${TARGET}${retried}`, req, headers, body)
      if (upstream.status !== 404) {
        console.warn(
          `[test-api-proxy] ${req.method} ${req.url} -> retried as ${retried}`
        )
      }
    }

    const outHeaders = { ...corsHeaders() }
    upstream.headers.forEach((value, key) => {
      if (!HOP_BY_HOP.has(key.toLowerCase())) {
        outHeaders[key] = value
      }
    })

    res.writeHead(upstream.status, outHeaders)
    res.end(Buffer.from(await upstream.arrayBuffer()))
  } catch (error) {
    res.writeHead(502, { 'Content-Type': 'application/json', ...corsHeaders() })
    res.end(
      JSON.stringify({
        error: {
          code: 'proxy_error',
          message: `Test proxy could not reach ${TARGET}: ${error.message}`,
          details: null,
        },
      })
    )
  }
})

server.listen(PORT, '127.0.0.1', () => {
  console.log(`test-api-proxy listening on http://localhost:${PORT} -> ${TARGET}`)
})
