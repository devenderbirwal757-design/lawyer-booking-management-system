import { existsSync } from 'node:fs'

import { defineConfig, devices } from '@playwright/test'

/**
 * Phase 8 end-to-end gate (plan §9.1 / PRD §31).
 *
 * The suite runs against a *real* stack - Next `next start`, the browser-facing
 * API proxy, and a live Django backend - because the behaviours worth locking
 * down here (proxy tenant headers, trailing-slash routing, OTP exchange, admin
 * scoping) only exist once those three are wired together.
 *
 * The backend is expected to be running already (see `.env.local` /
 * `docs/local-dev.md`); CI starts it in the job that invokes this suite. The
 * proxy and the Next server are started here so each run gets a clean pair.
 *
 * `localhost` is deliberate and load-bearing: `NEXT_PUBLIC_API_URL` is inlined
 * into the client bundle at build time, so the built app, the proxy and the
 * browser origin all have to agree. Mixing `127.0.0.1` and `localhost` produces
 * an origin mismatch that CORS rejects with a bare `net::ERR_FAILED`. For the
 * same reason the web server command builds the app itself unless
 * `E2E_SKIP_BUILD=1` says a matching build already exists.
 */
const PROXY_PORT = Number(process.env.TEST_PROXY_PORT ?? 3399)
const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 3398)
const API_PORT = Number(process.env.E2E_API_PORT ?? 8000)

const proxyOrigin = `http://localhost:${PROXY_PORT}`
const webOrigin = `http://localhost:${WEB_PORT}`
const apiOrigin = `http://localhost:${API_PORT}`
const apiUrl = `${proxyOrigin}/api/v1`

/**
 * `next.config.ts` sets `output: 'standalone'`, and `next start` is documented
 * as unsupported in that mode - it starts, serves a little, then exits, which
 * surfaces as a wave of `ERR_CONNECTION_REFUSED` rather than a clean error. So
 * the E2E server runs the standalone bundle instead, after copying the two
 * directories that are deliberately left out of it.
 */
const verifyBuild = `node scripts/verify-build-env.mjs ${apiUrl}`

/**
 * `NEXT_PUBLIC_API_URL` is inlined into the client bundle at build time, so the
 * build has to be compiled against the proxy origin this run uses. When the
 * build is skipped, `verify-build-env` reads the existing bundle and refuses to
 * start against a mismatched one - otherwise every browser-side call fails
 * silently and the suite just times out on a skeleton.
 */
const startWeb =
  process.env.E2E_SKIP_BUILD === '1'
    ? `${verifyBuild} && npm run start:standalone -- --port ${WEB_PORT}`
    : `NEXT_PUBLIC_API_URL=${apiUrl} API_URL=${apiUrl} NEXT_PUBLIC_APP_URL=${webOrigin} ` +
      `npm run build && npm run start:standalone -- --port ${WEB_PORT}`

/**
 * The OTP helper reads codes out of the backend's stdout, so that stream is
 * redirected to a known file rather than left attached to Playwright.
 */
export const BACKEND_LOG = process.env.E2E_BACKEND_LOG ?? '/tmp/backend-e2e.log'

/**
 * Interpreter used to start Django. Defaults to the repo's virtualenv, which is
 * what a local checkout has; CI installs into the runner's own Python instead,
 * so it points `E2E_PYTHON` at that.
 */
const BACKEND_PYTHON =
  process.env.E2E_PYTHON ??
  (existsSync('../backend/.venv/bin/python')
    ? '../backend/.venv/bin/python'
    : 'python3')

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // Kept at 1: the booking specs walk one customer's OTP window and the admin
  // specs share a tenant, so a higher worker count makes throttle and
  // availability assertions flaky for reasons that have nothing to do with the
  // code under test.
  workers: 1,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : [['list']],
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: webOrigin,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      // Django first, and on its own port: the proxy and Next both fail fast
      // without it, and the OTP helper needs its stdout. `reuseExistingServer`
      // is off on purpose - a stray process squatting on 8000 would otherwise
      // satisfy the readiness probe and shadow the API for the whole run.
      //
      // The throttle overrides are inlined in the command rather than passed via
      // `env`, because `webServer.env` did not reach `manage.py` here and the
      // stock rates (5 OTP sends/hour, 5 logins/15min) made the suite 429
      // itself into failure. The backend's own defaults are left untouched.
      command:
        `DJANGO_THROTTLE_ANON_RATE=1000/min ` +
        `DJANGO_THROTTLE_USER_RATE=1000/min ` +
        `DJANGO_THROTTLE_OTP_REQUEST_RATE=1000/hour ` +
        `DJANGO_THROTTLE_OTP_VERIFY_RATE=1000/hour ` +
        `DJANGO_THROTTLE_LOGIN_RATE=1000/15min ` +
        `DJANGO_THROTTLE_BOOKING_RATE=1000/min ` +
        `DJANGO_THROTTLE_PAYMENT_RATE=1000/min ` +
        `${BACKEND_PYTHON} -u manage.py runserver ${API_PORT} --noreload > ${BACKEND_LOG} 2>&1`,
      cwd: '../backend',
      url: `${apiOrigin}/api/v1/services/`,
      reuseExistingServer: false,
      stdout: 'ignore',
      stderr: 'pipe',
      timeout: 90_000,
    },
    {
      command: `node scripts/test-api-proxy.mjs`,
      url: `${proxyOrigin}/api/v1/services/?status=active`,
      reuseExistingServer: !process.env.CI,
      stdout: 'ignore',
      stderr: 'pipe',
      timeout: 30_000,
      env: {
        TEST_PROXY_PORT: String(PROXY_PORT),
        TEST_PROXY_ALLOWED_ORIGIN: webOrigin,
      },
    },
    {
      command: startWeb,
      url: webOrigin,
      reuseExistingServer: !process.env.CI,
      stdout: 'ignore',
      stderr: 'pipe',
      timeout: 420_000,
      env: {
        NEXT_PUBLIC_API_URL: apiUrl,
        API_URL: apiUrl,
        NEXT_PUBLIC_APP_URL: webOrigin,
        PORT: String(WEB_PORT),
      },
    },
  ],
})
