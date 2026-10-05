/**
 * Fail fast when an existing production build was compiled against a different
 * API origin than the one this run is about to use.
 *
 * `NEXT_PUBLIC_API_URL` is inlined into the client bundle at build time. A build
 * made without the E2E environment therefore keeps talking to whatever origin it
 * was compiled with, and every browser-side API call silently fails - which
 * surfaces as pages that render a skeleton and then time out on a label, with
 * nothing in the Django log. Checking the bundle turns that into one clear
 * message instead of a minute of per-test timeouts.
 *
 * Usage: `node scripts/verify-build-env.mjs <expected-api-url>`
 */
import { readdir, readFile } from 'node:fs/promises'
import { join } from 'node:path'

const expected = process.argv[2]

if (!expected) {
  console.error('Usage: node scripts/verify-build-env.mjs <expected-api-url>')
  process.exit(2)
}

const CHUNKS = '.next/static/chunks'

async function* walk(dir) {
  let entries
  try {
    entries = await readdir(dir, { withFileTypes: true })
  } catch {
    return
  }
  for (const entry of entries) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) yield* walk(path)
    else if (entry.name.endsWith('.js')) yield path
  }
}

/** The origin a chunk was compiled against, if it embedded one at all. */
const ORIGIN_PATTERN = /https?:\/\/[a-z0-9.:-]+\/api\/v\d+/gi

const found = new Set()

for await (const file of walk(CHUNKS)) {
  const source = await readFile(file, 'utf8')
  for (const match of source.matchAll(ORIGIN_PATTERN)) {
    found.add(match[0])
  }
}

if (found.size === 0) {
  console.error(
    `[verify-build-env] No API origin found in ${CHUNKS}. The build looks wrong; ` +
      'run a clean `npm run build`.'
  )
  process.exit(1)
}

const normalised = new Set([...found].map((url) => url.replace(/\/$/, '')))

if (!normalised.has(expected.replace(/\/$/, ''))) {
  console.error(
    `[verify-build-env] This build talks to ${[...normalised].join(', ')} but the ` +
      `run expects ${expected}.\n` +
      'NEXT_PUBLIC_API_URL is inlined at build time, so rebuild with that value:\n' +
      `  NEXT_PUBLIC_API_URL=${expected} API_URL=${expected} npm run build`
  )
  process.exit(1)
}

console.log(`[verify-build-env] build targets ${expected}`)