import { withSentryConfig } from '@sentry/nextjs/config'
import type { NextConfig } from 'next'

const apiBase =
  process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api/v1'

function originOf(base: string): string {
  try {
    return new URL(base).origin
  } catch {
    return base
  }
}

const securityHeaders = [
  {
    key: 'X-Frame-Options',
    value: 'DENY',
  },
  {
    key: 'X-Content-Type-Options',
    value: 'nosniff',
  },
  {
    key: 'Referrer-Policy',
    value: 'strict-origin-when-cross-origin',
  },
  {
    key: 'Permissions-Policy',
    value: 'camera=(), microphone=(), geolocation=()',
  },
]

// CSP is served in production only. Dev mode needs inline scripts/styles from
// React Refresh. `'unsafe-inline'` for styles is required by Radix inline
// `style` props; for scripts prefer a nonce-based CSP during hardening (Phase 8,
// security.md §A11).
const contentSecurityPolicy = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  `font-src 'self'`,
  `connect-src 'self' ${originOf(apiBase)} https://api.razorpay.com https://checkout.razorpay.com`,
  'frame-src https://checkout.razorpay.com',
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
  "object-src 'none'",
].join('; ')

const isProd = process.env.NODE_ENV === 'production'
const isSentryEnabled = Boolean(process.env.SENTRY_AUTH_TOKEN)

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Next otherwise answers `/api/v1/services/` with a 308 to `/api/v1/services`
  // before middleware runs, stripping the trailing slash that Django's DRF
  // router requires. With this set, middleware sees the caller's exact path and
  // `proxyToApi` forwards it unchanged.
  //
  // NB: in Next 15.5 this is a top-level key; under `experimental` it is
  // rejected with "Unrecognized key(s) in object".
  // `skipTrailingSlashRedirect: true` would also preserve the trailing slash,
  // but in Next 15.5 + Turbopack dev it breaks the build manifest
  // (`ENOENT .../static/development/_buildManifest.js.tmp.*`) and every page
  // 500s. `proxyToApi` in middleware.ts resolves the slash mismatch itself, so
  // the redirect is left enabled and dev stays usable.
  poweredByHeader: false,
  // Emits a self-contained server bundle in .next/standalone for the container
  // image (Phase 9). The Vercel path ignores this.
  output: 'standalone',
  turbopack: {
    root: process.cwd(),
  },
  // Client stack traces are unreadable without maps; they are uploaded to Sentry
  // at build time and stripped from the served bundles.
  productionBrowserSourceMaps: isSentryEnabled,
  async headers() {
    const headers = [...securityHeaders]
    if (isProd) {
      headers.push({
        key: 'Content-Security-Policy',
        value: contentSecurityPolicy,
      })
      // Only safe over HTTPS, which is enforced by the platform/terminator in
      // front of the container (Phase 9, custom domain + HTTPS).
      headers.push({
        key: 'Strict-Transport-Security',
        value: 'max-age=63072000; includeSubDomains; preload',
      })
    }
    return [
      {
        source: '/(.*)',
        headers,
      },
      {
        // The health endpoint is used by the container healthcheck and load
        // balancers; it must stay cheap and must not be cached.
        source: '/api/health',
        headers: [{ key: 'Cache-Control', value: 'no-store' }],
      },
    ]
  },
}

// `silent: true` keeps local builds and CI quiet when the Sentry auth token is
// absent; uploads only run when SENTRY_AUTH_TOKEN is set.
export default withSentryConfig(nextConfig, {
  silent: !isSentryEnabled,
  sourcemaps: {
    deleteSourcemapsAfterUpload: true,
  },
})
