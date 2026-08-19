# ---------------------------------------------------------------------------
# Default (CPU) image. Runs the API and every worker with the "mock"/CPU
# providers — no CUDA, no model weights, buildable on any machine.
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/srv/app

WORKDIR /srv/app

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /weights \
    && chown -R appuser:appuser /srv/app /weights
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


# ---------------------------------------------------------------------------
# GPU image. Build explicitly when you are ready to run real checkpoints:
#
#   docker build -f apps/api/Dockerfile --target gpu -t fashion-api:gpu apps/api
#
# Then point worker-vton-gpu / worker-image-gpu at this image and set the
# *_PROVIDER env vars away from "mock".
# ---------------------------------------------------------------------------
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04 AS gpu

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/srv/app \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /srv/app

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3-pip python3.11-dev \
        libgl1 libglib2.0-0 libgomp1 git curl \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Heavy AI stack — only present in the GPU image.
RUN pip install \
        torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu124 \
    && pip install \
        diffusers==0.32.1 \
        transformers==4.47.1 \
        accelerate==1.2.1 \
        safetensors==0.4.5

COPY . .

RUN mkdir -p /weights
EXPOSE 8000
CMD ["celery", "-A", "app.queue.celery_app:celery", "worker", "-Q", "vton", "--concurrency", "1"]
