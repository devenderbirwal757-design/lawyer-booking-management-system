import { NextRequest, NextResponse } from 'next/server'

import { hasSessionCookies } from '@/lib/auth/cookies'

function safeNextPath(pathname: string): string {
  return pathname.startsWith('/') && !pathname.startsWith('//') ? pathname : '/'
}

/** Prefix proxied to Django when both the app and the API share one origin. */
const API_PREFIX = '/api/v1'
const API_PROXY_TARGET = process.env.API_PROXY_TARGET?.replace(/\/+$/, '')

/**
 * Same-origin API proxy.
 *
 * Two constraints make this live in middleware rather than in
 * `next.config.ts`'s `rewrites()`:
 *
 * The path handling is the delicate part. Django's route surface mixes
 * conventions: DRF router routes require a trailing slash (`/services/`), while
 * hand-written ones take none (`/availability/slots`). `next.config.ts`'s
 * `rewrites()` cannot express that — its `:path*` capture drops the slash, and
 * `skipTrailingSlashRedirect` breaks the Turbopack dev build manifest — so the
 * slash is resolved here instead:
 *
 *   - a router path arrives here without its slash, because Next issues a 308 to
 *     the slash-less form before middleware runs. Django answers that with
 *     `APPEND_SLASH`'s own 301, which is followed server-side so the browser
 *     never sees a redirect hop and never re-enters middleware.
 *   - a hand-written path arrives intact and is forwarded once.
 *
 * Django resolves the tenant from the `Host` header and treats a bare IP as a
 * slug ("127" from 127.0.0.1), which 404s, so `Host` is rewritten to the
 * target's.
 *
 * `rewrite()` is used rather than a hand-rolled `fetch` so Django's auth cookies
 * and `Set-Cookie` pass through untouched.
 */
async function proxyToApi(req: NextRequest): Promise<NextResponse> {
  const target = API_PROXY_TARGET
  if (!target) {
    // Misconfiguration is a bug, not a browser condition: fail loudly instead of
    // letting the request fall through to a Next 404 that looks like a bug in
    // the app.
    return new NextResponse(
      JSON.stringify({
        error: {
          code: 'api_proxy_misconfigured',
          message: 'API_PROXY_TARGET is not set on the server.',
          details: null,
        },
      }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    )
  }

  const url = new URL(`${target}${req.nextUrl.pathname}${req.nextUrl.search}`)

  const headers = new Headers(req.headers)
  // Hop-by-hop and length headers describe the client hop, not the upstream one.
  headers.delete('host')
  headers.delete('content-length')
  headers.delete('connection')
  headers.set('host', new URL(target).host)

  const hasBody = !['GET', 'HEAD', 'OPTIONS'].includes(req.method)
  const body = hasBody ? await req.arrayBuffer() : undefined

  const send = async (u: URL): Promise<Response> =>
    fetch(u, {
      method: req.method,
      headers,
      body,
      redirect: 'manual',
    })

  let upstream: Response
  try {
    upstream = await send(url)

    // Next strips the trailing slash before middleware runs, so a DRF router
    // route arrives slash-less and Django answers `APPEND_SLASH`'s 301. Follow
    // that once, server-side: the browser gets a single 200 instead of a redirect
    // chain that would re-enter this middleware and drop the slash again, looping.
    //
    // Bounded to a 301 whose `Location` is this same path plus a trailing slash,
    // so a genuine redirect (login, canonical host) passes through untouched.
    // Django sends `Location` absolute and built from `request.build_absolute_uri`
    // (`APPEND_SLASH`), so the comparison is on the pathname, not the raw header.
    const location = upstream.headers.get('location')
    if (upstream.status === 301 && location) {
      const redirected = new URL(location, url)
      const samePathWithSlash =
        redirected.pathname === `${url.pathname}/` && redirected.search === url.search
      if (samePathWithSlash) {
        upstream = await send(redirected)
      }
    }

    // Fallback: DEBUG=True disables Django's APPEND_SLASH redirect, so router
    // routes that arrive slash-less return 404. Retry once with a trailing
    // slash for GET/HEAD only.
    if (
      upstream.status === 404 &&
      !url.pathname.endsWith('/') &&
      ['GET', 'HEAD'].includes(req.method)
    ) {
      const retryUrl = new URL(url)
      retryUrl.pathname = `${url.pathname}/`
      const retried = await send(retryUrl)
      if (retried.status < 400) {
        upstream = retried
      }
    }
  } catch {
    return new NextResponse(
      JSON.stringify({
        error: {
          code: 'api_proxy_unreachable',
          message: `The API at ${target} could not be reached.`,
          details: null,
        },
      }),
      { status: 502, headers: { 'Content-Type': 'application/json' } }
    )
  }

  const outHeaders = new Headers()
  upstream.headers.forEach((value, key) => {
    const lower = key.toLowerCase()
    if (lower !== 'content-encoding' && lower !== 'content-length' && lower !== 'connection') {
      outHeaders.set(key, value)
    }
  })
  outHeaders.delete('content-encoding')
  outHeaders.delete('content-length')

  return new NextResponse(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: outHeaders,
  })
}

function redirectToLogin(req: NextRequest, loginPath: string): NextResponse {
  const url = req.nextUrl.clone()
  url.pathname = loginPath
  url.searchParams.set('next', safeNextPath(req.nextUrl.pathname))
  return NextResponse.redirect(url)
}

export async function middleware(req: NextRequest): Promise<NextResponse> {
  const hasToken = hasSessionCookies((name) => req.cookies.has(name))
  const { pathname } = req.nextUrl

  // Checked before the auth guards: the API has its own authentication and must
  // never be redirected to the login page, which would turn a 401 into a 302.
  if (pathname === API_PREFIX || pathname.startsWith(`${API_PREFIX}/`)) {
    if (API_PROXY_TARGET) {
      return proxyToApi(req)
    }
    // No target configured: the API is on its own origin, so the browser
    // addresses it directly and CORS (not this proxy) applies.
    return NextResponse.next()
  }

  if (pathname.startsWith('/admin')) {
    if (pathname === '/admin/login' || pathname.startsWith('/admin/login/')) {
      return NextResponse.next()
    }
    if (!hasToken) {
      return redirectToLogin(req, '/admin/login')
    }
    return NextResponse.next()
  }

  if (
    pathname.startsWith('/dashboard') ||
    pathname.startsWith('/bookings') ||
    pathname.startsWith('/payments') ||
    pathname.startsWith('/profile')
  ) {
    if (!hasToken) {
      return redirectToLogin(req, '/login')
    }
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    // `/api/v1` is matched before the app routes so a proxied API call is never
    // intercepted by the auth guards above.
    '/api/v1',
    '/api/v1/:path*',
    '/dashboard/:path*',
    '/bookings/:path*',
    '/payments/:path*',
    '/profile/:path*',
    '/admin/:path*',
  ],
}
