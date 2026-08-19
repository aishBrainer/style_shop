# Deployment — Vercel (frontend) + Render (backend)

The app is five components. Vercel hosts one of them; Render hosts three; you
supply the fifth.

| Component | Host | Config |
|---|---|---|
| Next.js frontend | Vercel | `apps/web/vercel.json` |
| FastAPI + Celery workers | Render | `render.yaml` |
| PostgreSQL + Redis | Render | `render.yaml` |
| Object storage | **external** — R2 / B2 / S3 | you provide |
| GPU workers | **external** — optional | see below |

Deploy the backend first. The frontend needs its URL.

---

## 1. Object storage (before anything else)

Render has no S3-compatible service, and the API cannot store an upload without
one. Cloudflare R2 is the usual choice — S3-compatible, no egress fees.

Create a bucket and an API token with read/write on it, then keep these to hand:

| Variable | R2 example |
|---|---|
| `S3_ENDPOINT_URL` | `https://<account-id>.r2.cloudflarestorage.com` |
| `S3_PUBLIC_ENDPOINT_URL` | same as above |
| `S3_ACCESS_KEY` | R2 access key ID |
| `S3_SECRET_KEY` | R2 secret access key |
| `S3_BUCKET` | `fashion-studio` |
| `S3_REGION` | `auto` |

Keep the bucket **private**. The app never serves objects directly — it issues
short-lived signed URLs, which is what keeps customer uploads confidential.

---

## 2. Backend on Render

**New → Blueprint → connect the repo.** Render reads `render.yaml` and
provisions the API, three workers, beat, Postgres and Redis.

It will prompt for the values marked `sync: false`. Fill in the six `S3_*`
variables above, plus:

| Variable | Value |
|---|---|
| `CORS_ORIGINS` | your Vercel URL, e.g. `https://style-shop.vercel.app` |
| `WEB_URL` | same |

`SECRET_KEY` is generated automatically for the API. **Copy it into the
`fashion-worker-env` group** — workers verify the same signatures, and a
mismatch produces confusing auth failures rather than an obvious error. Do the
same for `DATABASE_URL`, `REDIS_URL` and the two Celery URLs: Render's
cross-service references resolve per service, not into shared groups.

### Verify

```bash
curl https://fashion-api-XXXX.onrender.com/health/ready
```

Expect `{"status":"ready","checks":{"database":"ok","redis":"ok","storage":"ok"}}`.
Anything reporting `error` names the failing dependency directly.

### First deploy notes

- Migrations and seeding run in the API's start command only, never in a
  worker, so four services cannot race each other on the same schema.
- `rembg` downloads ~176 MB of weights on first use. Without a persistent
  disk that repeats after every restart — the first background removal after
  a deploy is slow, subsequent ones are not.

---

## 3. Frontend on Vercel

**New Project → import the repo**, then — this is the part that produces the
"No Next.js version detected" error if skipped:

**Settings → General → Root Directory → `apps/web`**

`vercel.json` lives inside `apps/web`, so it cannot be what points Vercel
there. The setting is required.

Environment variables:

| Variable | Value |
|---|---|
| `API_INTERNAL_URL` | your Render API URL — the critical one |
| `NEXT_PUBLIC_APP_NAME` | `AI Fashion Studio` |
| `NEXT_PUBLIC_MAX_UPLOAD_MB` | `20` |

`API_INTERNAL_URL` is what `next.config.mjs` proxies `/api/v1/*` to. The
browser only ever talks to your Vercel domain, so the session cookie stays
first-party and no CORS preflight is involved in normal use.

Redeploy after setting it — rewrites are baked in at build time.

---

## 4. Check it end to end

1. Register an account. If this fails, `CORS_ORIGINS` or `COOKIE_SECURE` is wrong.
2. Upload a product image. If this fails, the `S3_*` values are wrong.
3. Run a background removal. Genuinely works on CPU; proves the whole
   queue → worker → storage → gallery loop.
4. Watch the progress bar. Smooth means SSE is through; jumpy means it fell
   back to polling (see below).

---

## Known limits of this topology

**Try-on does not produce real results.** Render has no GPU, so `VTON_PROVIDER`
is `mock` — it composites the garment onto the torso. Background removal,
adjustments and upscaling are real. Try-on is not, and must not be shown to a
customer as output. See `MODEL_LICENSE.md` for why no real checkpoint ships
enabled.

**Live progress may degrade to polling.** Server-sent events proxied through a
Vercel rewrite to an external origin are unreliable. The frontend already falls
back to polling, so progress still updates — just less smoothly. If it matters,
point the browser straight at the Render domain for `/api/v1/events` and set
`CORS_ORIGINS` accordingly.

**Free tiers will not work.** Render's free web services sleep when idle, which
stalls the queue; workers and Redis have no free tier at all. The plans in
`render.yaml` are the cheapest that actually function.

**Redis is shared across three roles** — cache, Celery broker and result
backend all point at one instance. Celery namespaces its keys, so this is safe,
but a busy queue and the pub/sub channel compete for the same memory. Split
them if throughput becomes a problem.

---

## Adding a GPU later

Nothing above changes. Host the GPU box anywhere that can reach Render's
Postgres and Redis, then:

1. Build the GPU image:

```bash
docker build -f apps/api/Dockerfile --target gpu -t fashion-api:gpu apps/api
```

2. Run the try-on and image workers there, pointed at the same `DATABASE_URL`,
   `REDIS_URL` and `S3_*` values.
3. Set `VTON_PROVIDER` / `IMAGE_PROVIDER` away from `mock` — only after
   recording the checkpoint's licence in `MODEL_LICENSE.md`.
4. Scale `fashion-worker-vton` and `fashion-worker-image` on Render to zero so
   they stop competing for the same queues.

The engine abstraction means no application code changes for any of this.
