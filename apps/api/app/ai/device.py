"""Device selection and VRAM reporting (§52, §63).

Imports torch lazily so the CPU image — which has no torch installed — can
still import this module.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class DeviceInfo:
    device: str
    gpu_name: str | None = None
    vram_total_mb: int | None = None
    vram_used_mb: int | None = None
    utilization: float | None = None


def resolve_device() -> str:
    """Honour AI_DEVICE, falling back to whatever this machine actually has."""
    requested = settings.ai_device
    if requested != "auto":
        return requested

    torch = _try_torch()
    if torch is None:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def device_info() -> DeviceInfo:
    device = resolve_device()
    if device != "cuda":
        return DeviceInfo(device=device)

    torch = _try_torch()
    if torch is None or not torch.cuda.is_available():
        return DeviceInfo(device="cpu")

    idx = torch.cuda.current_device()
    props = torch.cuda.get_device_properties(idx)
    total_mb = int(props.total_memory / 1024 / 1024)
    used_mb = int(torch.cuda.memory_allocated(idx) / 1024 / 1024)

    return DeviceInfo(
        device="cuda",
        gpu_name=props.name,
        vram_total_mb=total_mb,
        vram_used_mb=used_mb,
        utilization=_nvidia_smi_utilization(),
    )


def peak_vram_mb() -> int | None:
    torch = _try_torch()
    if torch is None or not torch.cuda.is_available():
        return None
    return int(torch.cuda.max_memory_allocated() / 1024 / 1024)


def reset_peak_vram() -> None:
    torch = _try_torch()
    if torch is not None and torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()


def empty_cache() -> None:
    """§52 — release cached blocks between jobs so a long-lived worker does not
    fragment VRAM into uselessness."""
    torch = _try_torch()
    if torch is not None and torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()


def _try_torch():
    try:
        import torch  # noqa: PLC0415

        return torch
    except ImportError:
        return None


def _nvidia_smi_utilization() -> float | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return float(out.stdout.strip().splitlines()[0])
    except Exception:  # noqa: BLE001 — monitoring must never break a job
        return None
