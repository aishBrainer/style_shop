# AI Model Licence Register

Required by §72 of the product specification.

> **Do not assume "open source" means "commercial SaaS allowed."** That
> assumption is wrong often enough to be a business risk, and several of the
> technically strongest virtual try-on models are exactly the case where it
> fails.

This file is the human-readable register. The machine-readable one is the
`ai_models` table (§50), seeded from `apps/api/app/seed.py`. Both must agree.

## How the code enforces this

Three layers, so a mistake in one is caught by another:

1. **`ModelInfo.commercial_use`** — every provider class declares its own
   licence status in code (`apps/api/app/ai/base.py`).
2. **Registry guard** — `app/ai/registry.py::_enforce_license` refuses to load
   any engine not marked `ALLOWED`, unless `ALLOW_NON_COMMERCIAL_MODELS=true`.
   That flag exists for local benchmarking and logs a warning every time it is
   used. It must never be set in production.
3. **Admin guard** — `POST /admin/models/{id}/toggle` rejects enabling a model
   whose registry row is not `commercial_use=allowed`, with the licence named
   in the error.

## Status legend

| Status | Meaning |
|---|---|
| `allowed` | Reviewed; licence permits commercial SaaS use. |
| `not_allowed` | Reviewed; licence forbids commercial use. Benchmarking only. |
| `unreviewed` | Not yet reviewed. Treated as not allowed by the guards. |

---

## Register

### Virtual try-on

| Field | Value |
|---|---|
| **Model** | Mock Virtual Try-On (CPU reference) |
| **Repository** | This repository — `apps/api/app/ai/providers/mock.py` |
| **Checkpoint** | None (procedural) |
| **Licence** | MIT (same as this project) |
| **Commercial use** | `allowed` |
| **Redistribution** | Yes |
| **Attribution** | Not required |
| **Restrictions** | None |
| **Dataset restrictions** | None — no training data involved |
| **Notes** | Produces a composite, not a real try-on. Ships enabled so the platform is testable end to end without weights. Not a production model. |

| Field | Value |
|---|---|
| **Model** | CatVTON |
| **Repository** | https://github.com/Zheng-Chong/CatVTON |
| **Checkpoint** | `zhengchong/CatVTON` |
| **Licence** | CC BY-NC-SA 4.0 |
| **Commercial use** | **`not_allowed`** |
| **Redistribution** | Only under the same licence (ShareAlike) |
| **Attribution** | Required |
| **Restrictions** | **NonCommercial.** A paid SaaS is a commercial use. ShareAlike may also extend to derivative weights. |
| **Dataset restrictions** | Trained on VITON-HD / DressCode — both carry their own research-only terms. Verify these separately; a permissive code licence does not cure a restricted training set. |
| **Notes** | Technically attractive (authors report inference under 8 GB VRAM at 1024×768). Ships **disabled**, adapter is a stub. Benchmarking only (§78). |

| Field | Value |
|---|---|
| **Model** | IDM-VTON |
| **Repository** | https://github.com/yisol/IDM-VTON |
| **Licence** | CC BY-NC-SA 4.0 |
| **Commercial use** | **`not_allowed`** |
| **Notes** | Same constraint as CatVTON. Not integrated. Listed here so the finding is recorded rather than rediscovered. |

### Segmentation

| Field | Value |
|---|---|
| **Model** | rembg / U²-Net |
| **Repository** | https://github.com/danielgatis/rembg |
| **Checkpoint** | `u2net` (~176 MB, downloaded on first use) |
| **Licence** | MIT (code) + Apache-2.0 (U²-Net weights) |
| **Commercial use** | `allowed` |
| **Redistribution** | Yes, with licence text |
| **Attribution** | Licence notice retained |
| **Restrictions** | None material |
| **Notes** | Default segmentation provider. CPU-only, so background removal works without a GPU. |

| Field | Value |
|---|---|
| **Model** | Segment Anything 2 (SAM 2) |
| **Repository** | https://github.com/facebookresearch/sam2 |
| **Checkpoint** | `sam2.1_hiera_large.pt` |
| **Licence** | Apache-2.0 (code **and** checkpoints) |
| **Commercial use** | `allowed` |
| **Redistribution** | Yes |
| **Attribution** | Licence notice retained |
| **Restrictions** | None material |
| **Notes** | Intended production auto-mask (§13). Ships disabled — needs the GPU image and a downloaded checkpoint. One of the few components here where licensing is genuinely settled. |

### Image generation / inpainting

| Field | Value |
|---|---|
| **Model** | SDXL base 1.0 |
| **Repository** | https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0 |
| **Licence** | CreativeML Open RAIL++-M |
| **Commercial use** | **`unreviewed`** |
| **Redistribution** | Permitted, but the use restrictions must be passed downstream |
| **Attribution** | Not required |
| **Restrictions** | Open RAIL++-M permits commercial use **but attaches a list of prohibited uses that you must impose on your own users**. That obligation has to be reflected in your terms of service before you enable this. |
| **Notes** | Ships **disabled** pending that terms-of-service work. Marked `unreviewed` rather than `allowed` deliberately — it is not a plain permissive licence. |

### Upscaling

| Field | Value |
|---|---|
| **Model** | Real-ESRGAN x4plus |
| **Repository** | https://github.com/xinntao/Real-ESRGAN |
| **Checkpoint** | `RealESRGAN_x4plus.pth` |
| **Licence** | BSD-3-Clause |
| **Commercial use** | `allowed` |
| **Redistribution** | Yes, with copyright notice |
| **Attribution** | Copyright notice retained |
| **Restrictions** | No endorsement using the authors' names |
| **Notes** | Ships disabled (needs the GPU image + weights). The `mock` provider does Lanczos + unsharp meanwhile, which is adequate at 2×. |

### Video

Nothing integrated. §30 is Phase 2/3. When you pick a video model, add its row
here **before** wiring the provider, not after.

---

## Before you enable any model

1. Read the actual licence file in the repository — not a summary, not a blog
   post, not this table.
2. Check the **training data** licence separately. A permissive code licence
   over a research-only dataset does not make the weights commercially usable.
3. Record the finding in this file **and** in the `ai_models` row.
4. Only then flip `enabled` in the admin panel.

If a licence is ambiguous, treat it as `not_allowed` and get legal advice. The
architecture (§114) exists precisely so that swapping a model out later costs
you a config change instead of a rewrite — use that, rather than shipping on a
licence you are unsure about.

## Open question for this project

**No commercially-licensed VTON model is currently wired up.** That is the one
genuine blocker between this codebase and a sellable product, and it is a
sourcing decision, not an engineering one. The options are, roughly:

- licence a commercial VTON model from its authors;
- train or fine-tune on data you have rights to;
- find a permissively-licensed model that meets your quality bar (benchmark it
  with §78 before committing);
- run the non-commercial models only for internal evaluation while you decide.

Everything else in the platform works without that decision being made.
