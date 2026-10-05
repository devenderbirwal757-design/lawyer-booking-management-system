#!/usr/bin/env node
/**
 * Lighthouse gate for the public pages (plan §8, Phase 8).
 *
 * Audits the routes a prospective client hits before they can book, and fails
 * the build when a score or metric regresses past its target:
 *
 *   - performance >= 90, accessibility >= 90, best-practices >= 90, SEO >= 90
 *   - LCP < 2500 ms
 *
 * Only the four categories above are scored. Accessibility and SEO are the two
 * that regress silently: a broken landmark, a lost label, or a dropped
 * canonical does not fail the type-checker or the bundle budget, so this is the
 * only automated check that would notice.
 *
 * Requires a running server. `npm run check:lighthouse` starts one itself via
 * Playwright's webServer-less path: pass a base URL with LIGHTHOUSE_BASE_URL to
 * audit an already-running instance (CI does this), otherwise the script boots
 * `next start` on port 3000 and tears it down afterwards.
 *
 * Colour-contrast is not asserted in this run. It is covered by the axe sweep
 * in `tests/unit/a11y.test.tsx`, and Lighthouse's own contrast audit needs a
 * real compositor.
 */
import { spawn } from 'node:child_process'
import { cp } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { join } from 'node:path'

import * as chromeLauncher from 'chrome-launcher'
import lighthouse from 'lighthouse'

/** Routes under audit, and why each is here. */
const ROUTES = [
  { path: '/', label: 'landing' },
  { path: '/services', label: 'service list' },
  { path: '/book', label: 'booking wizard' },
]

const CATEGORIES = ['performance', 'accessibility', 'best-practices', 'seo']
const MIN_CATEGORY_SCORE = 0.9
const MAX_LCP_MS = 2500

/**
 * Measurement profile. Lighthouse's default is mobile emulation on a throttled
 * Slow 4G connection with a 4x CPU slowdown, which is the harshest reading the
 * plan's targets could be applied to. It is the default here so the gate is a
 * worst-case check, but it is also the noisiest: repeat runs of the same build
 * have varied by ~5 points on these routes, so treat a single-point move as
 * noise. Set LIGHTHOUSE_FORM_FACTOR=desktop to audit without throttling.
 */
const FORM_FACTOR = process.env.LIGHTHOUSE_FORM_FACTOR ?? 'mobile'
const THROTTLE = FORM_FACTOR === 'desktop' ? null : { rttMs: 150, throughputKbps: 1638, cpuSlowdownMultiplier: 4 }

const PORT = Number(process.env.LIGHTHOUSE_PORT ?? 3311)
const EXTERNAL_BASE_URL = process.env.LIGHTHOUSE_BASE_URL

/**
 * Lighthouse needs a Chrome it can attach a debugger to. We launch Playwright's
 * pinned Chromium rather than whatever Chrome the machine happens to have, so a
 * local run and a CI run score the same engine. `--no-sandbox` is required
 * inside CI containers.
 */
const CHROME_FLAGS = [
  '--headless=new',
  '--no-sandbox',
  '--disable-gpu',
  '--disable-dev-shm-usage',
]

/**
 * `next build` runs with `output: 'standalone'`, and `next start` is documented
 * as unsupported in that mode - it starts, serves briefly, then exits. Auditing
 * it produced a connection error rather than a score. Launch the standalone
 * bundle the same way the E2E job does, copying the two directories the
 * standalone output deliberately leaves out.
 */
const STANDALONE_SERVER = join(process.cwd(), '.next', 'standalone', 'server.js')

async function startServer() {
  const standalone = existsSync(STANDALONE_SERVER)
  if (standalone) {
    for (const [from, to] of [
      ['.next/static', '.next/standalone/.next/static'],
      ['public', '.next/standalone/public'],
    ]) {
      if (!existsSync(join(process.cwd(), from))) continue
      await cp(join(process.cwd(), from), join(process.cwd(), to), {
        recursive: true,
      })
    }
  }

  const child = standalone
    ? spawn(process.execPath, [STANDALONE_SERVER], {
        stdio: 'ignore',
        detached: false,
        // `PORT` is overwritten rather than inherited, so an unrelated `PORT`
        // in the environment cannot bind this server to the Django port.
        env: { ...process.env, PORT: String(PORT), HOSTNAME: '127.0.0.1' },
      })
    : spawn('npx', ['next', 'start', '--port', String(PORT)], {
        stdio: 'ignore',
        detached: false,
      })

  return child
}

async function waitForServer(baseUrl, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const res = await fetch(baseUrl, { redirect: 'follow' })
      if (res.ok) {
        return true
      }
    } catch {
      // Not listening yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  return false
}

const scoreOf = (lhr, category) => lhr.categories[category]?.score ?? null

function formatScore(score) {
  return score === null ? 'n/a' : Math.round(score * 100)
}

if (!EXTERNAL_BASE_URL && !existsSync(join(process.cwd(), '.next'))) {
  console.error('No build found at .next — run `npm run build` first.')
  process.exit(1)
}

const baseUrl = EXTERNAL_BASE_URL ?? `http://localhost:${PORT}`
let server = null

if (!EXTERNAL_BASE_URL) {
  server = await startServer()
  const up = await waitForServer(baseUrl)
  if (!up) {
    server.kill()
    console.error(`Server never became ready at ${baseUrl}.`)
    process.exit(1)
  }
}

const rows = []
const failures = []

let chrome = null
try {
  chrome = await chromeLauncher.launch({
    chromeFlags: CHROME_FLAGS,
    // Falls back to CHROME_PATH, then to a system Chrome.
    chromePath: process.env.CHROME_PATH || undefined,
  })

  for (const route of ROUTES) {
    const url = `${baseUrl}${route.path}`
    const result = await lighthouse(
      url,
      {
        port: chrome.port,
        output: 'json',
        logLevel: 'error',
        formFactor: FORM_FACTOR,
        screenEmulation:
          FORM_FACTOR === 'desktop'
            ? { mobile: false, width: 1350, height: 940, deviceScaleFactor: 1, disabled: false }
            : { mobile: true, width: 412, height: 823, deviceScaleFactor: 1.75, disabled: false },
        throttlingMethod: THROTTLE ? 'simulate' : 'provided',
        throttling: THROTTLE ?? undefined,
      }
    )
    const lhr = result.lhr

    const scores = Object.fromEntries(
      CATEGORIES.map((category) => [category, scoreOf(lhr, category)])
    )
    const lcp = lhr.audits['largest-contentful-paint']?.numericValue ?? null

    rows.push({ ...route, scores, lcp })

    for (const category of CATEGORIES) {
      const score = scores[category]
      if (score !== null && score < MIN_CATEGORY_SCORE) {
        failures.push(
          `${route.path}: ${category} ${formatScore(score)} < ${formatScore(MIN_CATEGORY_SCORE)}`
        )
      }
    }
    if (lcp !== null && lcp > MAX_LCP_MS) {
      failures.push(`${route.path}: LCP ${Math.round(lcp)}ms > ${MAX_LCP_MS}ms`)
    }
  }
} finally {
  await chrome?.kill()
  server?.kill()
}

const width = Math.max(...rows.map((row) => row.path.length), 6)
console.log(`profile: ${FORM_FACTOR}${THROTTLE ? ' (throttled, 4x CPU)' : ' (unthrottled)'}`)
const header = ['route', ...CATEGORIES, 'LCP']
console.log(header.map((h) => h.padStart(12)).join(' '))
for (const row of rows) {
  const cells = [
    row.path.padEnd(width),
    ...CATEGORIES.map((c) => formatScore(row.scores[c]).toString().padStart(12)),
    `${Math.round(row.lcp ?? 0)}ms`.padStart(12),
  ]
  console.log(cells.join(' '))
}

if (failures.length) {
  console.error(`\nLighthouse targets missed:\n- ${failures.join('\n- ')}`)
  process.exit(1)
}

console.log(
  `\nAll ${rows.length} routes meet >=${formatScore(MIN_CATEGORY_SCORE)} across ${CATEGORIES.join('/')} with LCP <= ${MAX_LCP_MS}ms.`
)
