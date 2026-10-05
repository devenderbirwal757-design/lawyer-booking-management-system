/**
 * Start the Next standalone server for end-to-end runs.
 *
 * `next build` with `output: 'standalone'` emits a self-contained server in
 * `.next/standalone/`, but deliberately leaves out the static assets and
 * `public/`, which the container image copies in separately. The E2E job has no
 * image, so it does the same copy here and then runs the server, forwarding any
 * `--port` argument to the child's environment.
 */
import { cp, access } from 'node:fs/promises'
import { spawn } from 'node:child_process'

const STANDALONE = '.next/standalone/server.js'

const exists = await access(STANDALONE).then(
  () => true,
  () => false
)
if (!exists) {
  console.error(
    `${STANDALONE} is missing. Run \`npm run build\` first (output: 'standalone').`
  )
  process.exit(1)
}

for (const [from, to] of [
  ['.next/static', '.next/standalone/.next/static'],
  ['public', '.next/standalone/public'],
]) {
  const present = await access(from).then(
    () => true,
    () => false
  )
  if (!present) continue
  await cp(from, to, { recursive: true })
  console.log(`[start-standalone] copied ${from} -> ${to}`)
}

const portArgIndex = process.argv.indexOf('--port')
const port = portArgIndex !== -1 ? process.argv[portArgIndex + 1] : '3000'

// `PORT` is deliberately overwritten rather than inherited: a stray `PORT` in
// the environment once bound this server to the Django port, which silently
// shadowed the API and made every end-to-end failure look like an app bug.
const child = spawn(process.execPath, [STANDALONE], {
  stdio: 'inherit',
  env: { ...process.env, PORT: String(port), HOSTNAME: '127.0.0.1' },
})
child.on('exit', (code, signal) => process.exit(signal ? 1 : (code ?? 0)))
