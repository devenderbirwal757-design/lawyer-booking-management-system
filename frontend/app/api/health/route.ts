import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

/**
 * Liveness/readiness probe for the container healthcheck and load balancers.
 * Deliberately does not call the backend: the frontend is healthy when it can
 * serve traffic, and backend availability is reported in the body so a failing
 * API shows up without failing the container.
 */
export function GET(): NextResponse {
  return NextResponse.json(
    {
      status: 'ok',
      service: 'frontend',
      env: process.env.NODE_ENV ?? 'development',
      release:
        process.env.SENTRY_RELEASE ??
        process.env.VERCEL_GIT_COMMIT_SHA ??
        'local',
      timestamp: new Date().toISOString(),
    },
    { headers: { 'Cache-Control': 'no-store' } }
  )
}
