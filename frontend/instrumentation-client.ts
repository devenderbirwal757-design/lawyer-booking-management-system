/**
 * Error monitoring bootstrap.
 *
 * The Sentry browser SDK is ~53 kB gzipped and is loaded on every page, including
 * the public marketing and booking routes, which are the ones the §8 performance
 * budget cares about most. Importing it statically ships those bytes to every
 * visitor even when monitoring is switched off.
 *
 * `NEXT_PUBLIC_SENTRY_DSN` is inlined at build time, so when no DSN is configured
 * the branch is dead and the dynamic import never runs — the chunk is never
 * fetched. With a DSN set it initialises one tick later than a static import
 * would, which is why `sentry.client.config.ts` keeps its own `enabled` guard.
 */

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN

if (dsn) {
  void import('./sentry.client.config')
}
