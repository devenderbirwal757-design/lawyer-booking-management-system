# Deployment runbook (Phase 9)

The frontend deploys as a single container built from the Next.js `standalone`
server bundle. Any platform that can run an OCI image and terminate TLS in
front of it works: Fly.io, Render, Railway, ECS, Cloud Run, or a plain VM with
nginx/Caddy.

## 1. Build the image

```bash
docker build -t lawyer-frontend:latest \
  --build-arg NEXT_PUBLIC_APP_URL=https://example.in \
  --build-arg NEXT_PUBLIC_API_URL=https://api.example.in/api/v1 \
  --build-arg NEXT_PUBLIC_RAZORPAY_KEY_ID=rzp_live_xxx \
  --build-arg NEXT_PUBLIC_SENTRY_DSN=https://xxx@o0.ingest.sentry.io/0 \
  --build-arg NEXT_PUBLIC_SENTRY_ENVIRONMENT=production \
  --build-arg NEXT_PUBLIC_SENTRY_RELEASE="$(git rev-parse HEAD)" \
  .
```

`NEXT_PUBLIC_*` values are compiled into the client bundle, so they are build
arguments, not just runtime environment variables. Changing the API URL or
Razorpay key requires a rebuild, not a container restart.

Locally, `docker compose up --build` runs the same image with a healthcheck and
`localhost:3000` published.

## 2. Runtime environment

Only server-side values need to be set on the container:

| Variable             | Required | Purpose                                   |
| -------------------- | -------- | ----------------------------------------- |
| `NODE_ENV`           | yes      | Set to `production`                       |
| `PORT`               | no       | Defaults to `3000`                        |
| `HOSTNAME`           | no       | Defaults to `0.0.0.0`                     |
| `SENTRY_DSN`         | no       | Server error reporting                    |
| `SENTRY_ENVIRONMENT` | no       | `production` / `staging`                  |
| `SENTRY_RELEASE`     | no       | Git SHA, for error grouping               |
| `API_URL`            | no       | Server-side fallback for the API base URL |

Sentry is inert when no DSN is set, so preview and local builds run without any
monitoring configuration.

## 3. Health checks

`GET /api/health` returns `200` with a small JSON body and `Cache-Control:
no-store`. It never calls the backend, so a backend outage does not restart the
frontend containers. Point the platform healthcheck at it:

```
GET /api/health
```

The image also declares a `HEALTHCHECK` using the same path.

## 4. Custom domain + HTTPS

1. Point the domain's DNS (A/AAAA or CNAME) at the platform's assigned address.
2. Attach the domain in the platform and let it issue a certificate.
3. Set `NEXT_PUBLIC_APP_URL=https://your-domain` so canonical URLs, the sitemap,
   and `robots.txt` emit the real origin, then rebuild.
4. Confirm the redirect is enforced at the terminator (platform setting or
   nginx/Cloudflare "Always Use HTTPS"). HSTS is sent from the app in production
   once TLS is confirmed.

The backend must be reachable from the browser (it is called directly with
HttpOnly cookies), so `NEXT_PUBLIC_API_URL` and the backend's CORS and cookie
`Domain`/`Secure` settings must all agree on the final origins.

## 5. Error monitoring

1. Create a Sentry project (Node.js + React) and note the DSNs.
2. Add repository secrets: `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, `SENTRY_PROJECT`,
   and `NEXT_PUBLIC_SENTRY_DSN`.
3. Pass `NEXT_PUBLIC_SENTRY_RELEASE=$GITHUB_SHA` when building; error grouping
   follows the release.
4. Source maps are uploaded at build time via `withSentryConfig` and deleted
   afterwards. This only happens when `SENTRY_AUTH_TOKEN` is present, so local
   and CI-without-secrets builds are unaffected.

Event data is deliberately minimized: no user info, cookies, headers, query
params, or request bodies (`dataCollection` in `sentry.*.config.ts`).

## 6. Pre-deploy checklist

```bash
npm run ci        # lint, typecheck, test, build, bundle budget
docker build -t lawyer-frontend:verify .
docker run --rm -d --name f -p 3000:3000 lawyer-frontend:verify
curl -fsS http://127.0.0.1:3000/api/health
```

Then walk the PRD §31 flow in staging: book a consultation as a customer, sign
in as an admin, confirm the appointment, issue a refund, and check that the Sentry
project received the container's health/startup events without request data.

## 7. Rollback

Keep the previous image tag. Roll back by re-pointing the platform to the
previous tag and redeploying; no rebuild is required since runtime env vars are
injected at start. Note that clients holding a cached bundle keep running the
older code until they reload, so `NEXT_PUBLIC_SENTRY_RELEASE` should match the
image that actually serves the bundle.
