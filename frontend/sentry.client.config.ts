import * as Sentry from '@sentry/nextjs'

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN

Sentry.init({
  dsn,
  enabled: Boolean(dsn),
  environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ?? 'development',
  release:
    process.env.NEXT_PUBLIC_SENTRY_RELEASE ??
    process.env.VERCEL_GIT_COMMIT_SHA ??
    undefined,
  tracesSampleRate: 0,
  // The booking flow handles PII, so nothing identifying is attached: no user
  // info, cookies, headers, or request/response bodies.
  dataCollection: {
    userInfo: false,
    cookies: false,
    httpHeaders: false,
    httpBodies: [],
    urlQueryParams: false,
  },
  attachStacktrace: true,
  ignoreErrors: [
    // Canceled React Query / navigation requests are expected noise.
    'Failed to fetch',
    'Load failed',
    'NetworkError when attempting to fetch resource.',
  ],
})
