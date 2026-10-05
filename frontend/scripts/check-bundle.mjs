#!/usr/bin/env node
/**
 * Bundle budget check.
 *
 * Reads .next/app-build-manifest.json, splits each route's chunks into the set
 * shared by every route (framework, React, UI kit) and the route-specific part,
 * then fails the build when either exceeds its budget. Budgets exist to catch
 * regressions: they were captured from the Phase 9 baseline (measured size +
 * 20% headroom, since Turbopack chunking shifts slightly between builds) and
 * should be lowered as routes get optimised.
 *
 * The shared baseline carries the framework, React, the UI kit, and the Sentry
 * browser SDK (added in Phase 9, ~53 kB gzip). Sentry is inert without a DSN
 * but the module is still bundled, so this budget rises if that SDK changes.
 */
import { existsSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const DEFAULT_ROUTE_BUDGET_KB = 400
const SHARED_BUDGET_KB = 810

const ROUTE_BUDGETS_KB = {
  '/(booking)/book/page': 260,
  '/(customer)/bookings/[id]/page': 260,
  '/(customer)/bookings/page': 40,
  '/(customer)/dashboard/page': 200,
  '/(customer)/payments/page': 160,
  '/(customer)/profile/page': 190,
  '/(public)/page': 70,
  '/(public)/privacy/page': 70,
  '/(public)/services/[slug]/page': 70,
  '/(public)/services/page': 70,
  '/(public)/terms/page': 70,
  '/_not-found/page': 20,
  '/admin/(shell)/appointments/[id]/page': 360,
  '/admin/(shell)/appointments/page': 400,
  '/admin/(shell)/audit/page': 230,
  '/admin/(shell)/calendar/page': 340,
  '/admin/(shell)/clients/[id]/page': 240,
  '/admin/(shell)/clients/page': 230,
  '/admin/(shell)/dashboard/page': 270,
  '/admin/(shell)/payments/[id]/page': 250,
  '/admin/(shell)/payments/page': 340,
  '/admin/(shell)/reports/page': 340,
  '/admin/(shell)/services/page': 270,
  '/admin/(shell)/settings/page': 280,
  '/admin/login/page': 150,
  '/admin/page': 20,
  '/login/page': 150,
}

const DIST = join(process.cwd(), '.next')
const manifestPath = join(DIST, 'app-build-manifest.json')

if (!existsSync(manifestPath)) {
  console.error('No build found at .next — run `npm run build` first.')
  process.exit(1)
}

const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
const pages = manifest.pages ?? {}
const jsOf = (files) =>
  files.filter((file) => file.endsWith('.js') && existsSync(join(DIST, file)))
const sizeOf = (file) => statSync(join(DIST, file)).size
const kb = (bytes) => Math.round((bytes / 1024) * 10) / 10

const allSets = Object.values(pages).map((files) => new Set(jsOf(files)))
const shared = [...(allSets[0] ?? [])].filter((file) =>
  allSets.every((set) => set.has(file))
)
const sharedBytes = shared.reduce((sum, file) => sum + sizeOf(file), 0)

const rows = []
const failures = []

for (const [page, files] of Object.entries(pages)) {
  const routeFiles = jsOf(files).filter((file) => !shared.includes(file))
  const routeKb = kb(routeFiles.reduce((sum, file) => sum + sizeOf(file), 0))
  const budget = ROUTE_BUDGETS_KB[page] ?? DEFAULT_ROUTE_BUDGET_KB
  rows.push({ page, routeKb, budget })
  if (routeKb > budget) {
    failures.push(`${page}: route JS ${routeKb} kB exceeds ${budget} kB`)
  }
}

const sharedKb = kb(sharedBytes)
if (sharedKb > SHARED_BUDGET_KB) {
  failures.push(
    `shared baseline: ${sharedKb} kB exceeds ${SHARED_BUDGET_KB} kB`
  )
}

rows.sort((a, b) => b.routeKb - a.routeKb)
const width = Math.max(...rows.map((row) => row.page.length), 10)

console.log(`Shared baseline (${shared.length} chunks): ${sharedKb} kB\n`)
console.log('Route-specific JS (kB)\n')
for (const row of rows) {
  const flag = row.routeKb > row.budget ? '  OVER BUDGET' : ''
  console.log(
    `${row.page.padEnd(width)}  ${String(row.routeKb).padStart(7)}  / ${String(row.budget).padStart(4)}${flag}`
  )
}

if (failures.length) {
  console.error(`\nBundle budget exceeded:\n- ${failures.join('\n- ')}`)
  process.exit(1)
}

console.log(`\nAll ${rows.length} routes are within budget.`)
