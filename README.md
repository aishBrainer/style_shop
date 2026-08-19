# AI Fashion Studio

An AI photoshoot and marketing studio for ecommerce brands. Upload a garment,
pick a model, get an on-model product image — then background, edit, upscale
and download without leaving the app.

Built to the specification in *AI Fashion Studio — Full Product Scope &
Technical Architecture*. Section references throughout the code (`§14`, `§72`,
…) point back at it.

---

## Quick start

```bash
cp .env.example .env
```

Set a real `SECRET_KEY` in `.env` (compose refuses to start without one):

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Then:

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Web app | http://localhost:3000 |
| API docs | http://localhost:8000/docs |
| MinIO console | http://localhost:9001 |

A development administrator is seeded outside production:
`admin@aifashionstudio.local` / `changeme-admin-123` (override with
`ADMIN_EMAIL` / `ADMIN_PASSWORD`).

**No GPU is required.** The default providers run on CPU, so the full loop —
upload → queue → worker → live progress → gallery → download — works on a
laptop. See *AI models* below for what that does and does not mean.

---

## What is built

Everything in the MVP scope (§3, items 1–17), plus the Phase 2 image tools.

**Core loop (§90, §115)** — register, create a project, upload a garment,
select or upload a model, auto-detect the garment category, edit the mask,
choose settings, generate, watch live progress, compare against the original,
upscale, download, and find it saved in the project.

**Studio tools** — virtual try-on, product photography, background
removal/replacement, generative fill, magic eraser, canvas expansion, image
adjustment, upscaling.

**Platform** — multi-tenant organizations, projects, products, model library,
custom model upload with validation, asset library with three renditions,
credit ledger, usage tracking, feature flags, notifications, audit log, admin
panel with GPU monitoring and the AI model registry.

**Not built** — video (§30), ad creatives (§31), Shopify (§107), payments.
These are Phase 3+ in the spec; the schema and queue routing for them exist.

---

## Architecture

```
Browser ──▶ Next.js ──▶ FastAPI ──▶ Redis queue ──▶ Celery workers ──▶ AI engines
                            │                                              │
                            ├──▶ PostgreSQL (metadata only)                │
                            └──▶ S3/MinIO (bytes) ◀────────────────────────┘
                            │
                            └──▶ SSE ──▶ live progress in the browser
```

Two rules the whole design hangs on:

**AI never runs inside an HTTP request (§18).** `POST /vton/jobs` charges
credits, writes a row, enqueues, and returns a job id in milliseconds. Progress
arrives over SSE; a polling fallback covers proxies that buffer streams.

**No layer above `app/ai/` knows which model is loaded (§15, §114).** Engines
implement `VirtualTryOnEngine`, `SegmentationEngine`, `ImageGenerationEngine`,
`UpscaleEngine` or `VideoEngine`. Swapping VTON v1 for v2 is an env var, not a
refactor.

### Layout

```
apps/
  api/                    FastAPI + Celery (one codebase, many worker roles)
    app/
      api/v1/             routes — validate, delegate, return
      services/           business logic
      ai/
        base.py           the engine interfaces
        registry.py       provider resolution, model cache, licence guard
        providers/        mock, rembg, sam2, diffusers, realesrgan, catvton
        pipelines/        §17 stage orchestration
      queue/              celery app, tasks, events, maintenance
      workers/            job lifecycle, asset I/O, heartbeats
      models/ schemas/    SQLAlchemy 2.x + Pydantic v2
  web/                    Next.js 14 App Router
infrastructure/nginx/
MODEL_LICENSE.md          §72 licence register — read before enabling a model
```

### Workers (§49)

Queue per engine, so a slow job cannot starve a fast one:

| Worker | Queue | Handles |
|---|---|---|
| `worker-cpu` | `cpu` | background removal, adjustments, analysis, validation |
| `worker-vton` | `vton` | try-on |
| `worker-image` | `image` | diffusion: backgrounds, photography, inpaint, upscale |
| `worker-video` | `video` | Phase 2, `--profile video` |
| `beat` | — | stale-job reaping, usage rollups, retention sweeps |

GPU variants live behind `--profile gpu`.

---

## AI models

**The default `mock` provider is not a try-on model.** It composites the
garment onto the model's torso. It exists so every other part of the platform
is testable and load-testable today, and so the pipeline is proven before you
commit to a checkpoint. It must never be presented to a customer as a result.

### The licensing problem

§16 and §72 flag this, and it is the one genuine blocker between this codebase
and a sellable product:

**The strongest open virtual try-on models are licensed CC BY-NC-SA 4.0 —
non-commercial.** That covers CatVTON and IDM-VTON. A paid SaaS is a commercial
use. Their training datasets carry separate research-only terms.

So no VTON checkpoint ships enabled. Three guards enforce that:

1. Each provider declares `commercial_use` in code.
2. `registry._enforce_license` refuses to load anything not `ALLOWED` unless
   `ALLOW_NON_COMMERCIAL_MODELS=true` (benchmarking only — it logs a warning).
3. The admin toggle rejects enabling a non-commercial model, naming the licence.

`MODEL_LICENSE.md` is the register. Components where licensing *is* settled:
SAM 2 (Apache-2.0), rembg/U²-Net (MIT + Apache-2.0), Real-ESRGAN (BSD-3).

### Switching providers

```bash
VTON_PROVIDER=mock          # mock | catvton
IMAGE_PROVIDER=mock         # mock | sdxl
SEGMENTATION_PROVIDER=rembg # mock | rembg | sam2
UPSCALE_PROVIDER=mock       # mock | realesrgan
```

Real checkpoints need the GPU image:

```bash
docker build -f apps/api/Dockerfile --target gpu -t fashion-api:gpu apps/api
docker compose --profile gpu up
```

---

## Development

```bash
# Backend tests — 50 tests, no database or GPU needed
cd apps/api && pytest

# Integration tests need Postgres
TEST_DATABASE_URL=postgresql+psycopg2://fashion:fashion@localhost:5432/fashion_studio pytest

# Frontend
cd apps/web && npm run typecheck && npm run build
```

### Migrations

The first revision builds the schema from the ORM metadata — a hand-copied
initial migration drifts from the models and only a live database catches it.
Everything after is a normal autogenerate:

```bash
docker compose exec api alembic revision --autogenerate -m "add x"
docker compose exec api alembic upgrade head
```

---

## Deliberate decisions

Worth knowing before you change them.

**Auth lives in FastAPI, not Auth.js.** §7 suggests Better Auth / Auth.js.
FastAPI owns every row a session authorises, and splitting session ownership
across two runtimes means two places to enforce organization scoping (§61) —
the exact bug class multi-tenancy least tolerates. Next.js holds the httpOnly
cookie and proxies; it never mints identity.

**One codebase, many worker roles.** §73 sketches `services/vton-worker/` as
separate packages. They would share models, storage, config and the engine
interfaces, so separate packages buy duplicated code, not isolation. Roles are
separate *processes* with independent scaling — which is what §49 actually asks
for.

**No ORM relationships.** Every read loads what it needs explicitly. Under an
async session a lazy relationship raises `MissingGreenlet` the moment anything
touches it, including Pydantic's `from_attributes` walk. `ON DELETE CASCADE` on
the foreign keys gives the same integrity guarantees.

**Credits are refunded only when a job finally gives up.** Refunding on an
attempt Celery will retry hands the credit back while the work still runs.

---

## Verification status

- Backend: 50 tests pass locally (`pytest`).
- Frontend: `tsc --noEmit` clean; `next build` succeeds, 19 routes.
- **Not verified:** `docker compose up` has not been run — Docker was not
  installed on the build machine. The compose stack, migrations, MinIO wiring
  and the worker↔API round trip are unexercised. Expect to shake out
  environment issues on first boot.

---

## Before going to production

1. Resolve the VTON licensing question (`MODEL_LICENSE.md`). Nothing else
   matters until this is settled.
2. Benchmark candidate models against a fixed set (§76, §78) — the `ai_models`
   table has the columns for it.
3. Set `SECRET_KEY`, `COOKIE_SECURE=true`, real S3, and a real SMTP host.
4. Add malware scanning on upload (§58) — currently only image-decode
   validation, which stops payloads-as-images but is not an AV scan.
5. Load-test the queue and size GPU capacity from measurements, not guesses
   (§53).
