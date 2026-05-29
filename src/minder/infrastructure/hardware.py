"""Hardware profile detection for optimal LLM inference settings.

Detects platform, architecture, and available RAM, then computes inference
parameters that keep memory usage within safe bounds on the current device.

Key findings:
  - n_batch=512 (llama.cpp default) + n_ctx=16384 → Metal compute buffers
    can exceed 10 GB on Apple Silicon, causing OOM/swap and "no response".
  - Reducing n_batch to 128 and n_ctx to ≤8192 cuts compute buffers by ~8x
    while keeping prefill speed acceptable for single-user chat workloads.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_cached_profile: HardwareProfile | None = None


@dataclass(frozen=True)
class HardwareProfile:
    platform: str           # 'darwin' | 'linux' | 'windows'
    arch: str               # 'arm64' | 'x86_64' | ...
    is_apple_silicon: bool
    total_ram_gb: float
    cpu_count: int

    # Recommended Llama.cpp init parameters
    n_ctx: int          # context window tokens
    n_batch: int        # prompt-processing batch size
    n_ubatch: int       # Metal/CUDA micro-batch size (n_batch // 2)
    n_gpu_layers: int   # -1 = all on GPU/Metal, 0 = CPU-only
    n_threads: int      # CPU threads (0 = let llama.cpp decide)
    use_flash_attn: bool


def get_hardware_profile(*, max_ctx: int = 16384) -> HardwareProfile:
    """Return a cached (or freshly computed) hardware profile.

    Args:
        max_ctx: Upper bound for the context window.  The returned ``n_ctx``
                 will never exceed this value.
    """
    global _cached_profile
    if _cached_profile is not None and _cached_profile.n_ctx <= max_ctx:
        return _cached_profile

    sys_platform = platform.system().lower()
    arch = platform.machine().lower()
    cpu_count = os.cpu_count() or 4
    is_apple_silicon = sys_platform == "darwin" and arch == "arm64"
    total_ram_gb = _get_total_ram_gb(sys_platform)

    n_ctx, n_batch, n_ubatch, n_gpu_layers, n_threads, use_flash_attn = _compute_settings(
        is_apple_silicon=is_apple_silicon,
        total_ram_gb=total_ram_gb,
        cpu_count=cpu_count,
        max_ctx=max_ctx,
    )

    _cached_profile = HardwareProfile(
        platform=sys_platform,
        arch=arch,
        is_apple_silicon=is_apple_silicon,
        total_ram_gb=total_ram_gb,
        cpu_count=cpu_count,
        n_ctx=n_ctx,
        n_batch=n_batch,
        n_ubatch=n_ubatch,
        n_gpu_layers=n_gpu_layers,
        n_threads=n_threads,
        use_flash_attn=use_flash_attn,
    )
    logger.info(
        "Hardware profile: platform=%s arch=%s ram=%.0fGB "
        "n_ctx=%d n_batch=%d n_gpu_layers=%d flash_attn=%s",
        sys_platform, arch, total_ram_gb,
        n_ctx, n_batch, n_gpu_layers, use_flash_attn,
    )
    return _cached_profile


def _compute_settings(
    *,
    is_apple_silicon: bool,
    total_ram_gb: float,
    cpu_count: int,
    max_ctx: int,
) -> tuple[int, int, int, int, int, bool]:
    """Return (n_ctx, n_batch, n_ubatch, n_gpu_layers, n_threads, flash_attn).

    Memory model (all on Metal/GPU for Apple Silicon):

      total_inference_memory
        ≈ model_weights
        + kv_cache      ← n_ctx × n_kv_heads × head_dim × n_layers × 2 × dtype
        + attn_scratch  ← n_batch × n_ctx × n_heads × n_layers × dtype   (dominant!)
        + process       ← Python + libraries

    With n_batch=512 (llama.cpp default) and n_ctx=16384 on a 4B model:
      attn_scratch ≈ 512 × 16384 × 8 × 18 × 4 bytes ≈ 4.8 GB
      + model (Q8_0): 4.5 GB + KV: 1.2 GB + process: 2 GB ≈ 12.5 GB
      → approaches / exceeds 16 GB → heavy swap → "no response"

    With n_batch=128 and n_ctx=8192 on 16 GB device (Q4_K_M):
      attn_scratch ≈ 128 × 8192 × 8 × 18 × 4 ≈ 0.6 GB
      + model (Q4_K_M): 2.5 GB + KV: 0.6 GB + process: 2 GB ≈ 5.7 GB ✓
    """
    # Approximate architecture constants (conservative for ~4B class models)
    _N_LAYERS = 18
    _N_HEADS = 8
    _N_KV_HEADS = 4
    _HEAD_DIM = 256
    _DTYPE_BYTES = 2  # float16

    # ── Batch size — determined first as it's the biggest lever ───────────────
    # Single-user app: n_batch=128 gives fast prefill without large scratch bufs.
    if total_ram_gb >= 48:
        n_batch = 512
    elif total_ram_gb >= 32:
        n_batch = 256
    elif total_ram_gb >= 16:
        n_batch = 128
    else:
        n_batch = 64

    # ── Context length — derived from remaining RAM budget ────────────────────
    # Reserve for model weights (Q4_K_M ~2.5 GB; Q8_0 ~4.5 GB) + process (~2 GB).
    # Use 4 GB as a safe model-weights estimate so the formula works for either.
    _MODEL_OVERHEAD_GB = 6.0  # model weights + Python + system overhead
    budget_gb = max(0.5, total_ram_gb * 0.55 - _MODEL_OVERHEAD_GB)
    budget_bytes = int(budget_gb * 1_073_741_824)

    # Per-token cost = KV contribution + attention-scratch contribution
    #   kv_per_token = n_kv_heads * head_dim * n_layers * 2 (K+V) * dtype_bytes
    kv_per_token = _N_KV_HEADS * _HEAD_DIM * _N_LAYERS * 2 * _DTYPE_BYTES
    #   attn_per_token = n_batch * n_heads * n_layers * dtype_bytes
    #   (attention matrix is n_batch × n_ctx, scaled per head and layer)
    attn_per_token = n_batch * _N_HEADS * _N_LAYERS * _DTYPE_BYTES
    bytes_per_token = kv_per_token + attn_per_token

    raw_ctx = int(budget_bytes / bytes_per_token) if bytes_per_token > 0 else 2048

    # Snap to nearest power-of-two ≤ max_ctx
    n_ctx = 1024
    for bucket in (1024, 2048, 4096, 8192, 16384):
        if raw_ctx >= bucket:
            n_ctx = min(bucket, max_ctx)
    n_ctx = max(1024, n_ctx)

    n_ubatch = max(32, n_batch // 2)

    # ── GPU / CPU settings ────────────────────────────────────────────────────
    if is_apple_silicon:
        n_gpu_layers = -1   # All layers on Metal (unified memory)
        n_threads = 0       # Metal manages parallelism
        use_flash_attn = True
    else:
        n_gpu_layers = 0
        n_threads = max(1, cpu_count // 2)
        use_flash_attn = False

    return n_ctx, n_batch, n_ubatch, n_gpu_layers, n_threads, use_flash_attn


def _get_total_ram_gb(sys_platform: str) -> float:
    """Return total installed RAM in GB. Falls back to 8 GB on any error."""
    try:
        if sys_platform == "darwin":
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=3,
            )
            return int(result.stdout.strip()) / (1024 ** 3)
        if sys_platform == "linux":
            with open("/proc/meminfo") as fh:
                for line in fh:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return kb / (1024 ** 2)
    except Exception as exc:
        logger.debug("RAM detection failed (%s), assuming 8 GB", exc)
    return 8.0
