from __future__ import annotations

import importlib.util
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LLAMA_CPP_PROBE: bool | None = None


def module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def load_attr(module_name: str, attr_name: str) -> Any | None:
    if not module_available(module_name):
        return None
    module = __import__(module_name, fromlist=[attr_name])
    return getattr(module, attr_name, None)


def llama_cpp_usable() -> bool:
    """Return True only if llama.cpp can actually run on this CPU.

    Some CI runners / VM hypervisors block AVX2 instructions even when
    /proc/cpuinfo advertises them, causing an unrecoverable SIGILL.  We
    probe by running a subprocess that initialises the ggml backend; if the
    subprocess is killed by SIGILL (returncode == -signal.SIGILL) we mark
    the library as unavailable and fall back to mock mode.

    Build the Docker image with CMAKE_ARGS containing -DGGML_AVX2=OFF (and
    related flags) to compile a portable binary that avoids SIGILL entirely.
    Result is cached for the lifetime of the process.
    """
    global _LLAMA_CPP_PROBE
    if _LLAMA_CPP_PROBE is not None:
        return _LLAMA_CPP_PROBE

    if not module_available("llama_cpp"):
        logger.warning("llama-cpp-python is not installed. Falling back to mock mode.")
        _LLAMA_CPP_PROBE = False
        return False

    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                # Instantiating Llama triggers ggml_backend_reg_count → ggml_cpu_init.
                # /dev/null causes a model-load error (returncode 1) on healthy CPUs;
                # SIGILL (returncode -4) means the CPU doesn't support the compiled ISA.
                "from llama_cpp import Llama; Llama(model_path='/dev/null', verbose=False)",
            ],
            capture_output=True,
            timeout=30,
        )
        if proc.returncode == -signal.SIGILL:
            logger.warning(
                "llama.cpp unavailable: CPU or hypervisor blocked an instruction "
                "(SIGILL). Rebuild the image with CMAKE_ARGS containing "
                "-DGGML_AVX2=OFF to fix this. Falling back to mock mode."
            )
            _LLAMA_CPP_PROBE = False
        else:
            _LLAMA_CPP_PROBE = True
    except subprocess.TimeoutExpired:
        logger.warning("llama.cpp usability probe timed out. Falling back to mock mode.")
        _LLAMA_CPP_PROBE = False
    except Exception as exc:
        logger.warning("llama.cpp usability probe error: %s. Falling back to mock mode.", exc)
        _LLAMA_CPP_PROBE = False

    return _LLAMA_CPP_PROBE


def get_writable_hf_cache_dir() -> str | None:
    """Return a writable HuggingFace Hub cache directory.

    When ``HUGGINGFACE_HUB_CACHE`` (or ``HF_HOME``) points to a read-only
    path — common in Docker where the models volume is mounted ``:ro`` — HF Hub
    cannot create the per-repo directories and raises ``[Errno 30] Read-only
    file system``.  This helper detects that situation and returns a writable
    fallback so callers can pass it as ``cache_dir`` to
    ``Llama.from_pretrained()``.

    Returns:
        ``None``  — no override needed; HF Hub will use its env-configured
                    cache (which is writable or not set).
        ``str``   — path of a writable fallback directory that the caller
                    should pass as ``cache_dir``.
    """
    hf_cache = os.environ.get("HUGGINGFACE_HUB_CACHE") or os.environ.get("HF_HOME", "")
    if not hf_cache:
        return None  # no env override; HF uses ~/.cache/huggingface (writable)

    if os.access(hf_cache, os.W_OK):
        return None  # configured cache is writable; no override needed

    # Configured cache exists but is read-only (e.g. Docker :ro volume).
    fallback = os.environ.get("MINDER_MODEL_CACHE_DIR", "/tmp/minder_hf_cache")
    try:
        Path(fallback).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("Could not create HF fallback cache dir %r: %s", fallback, exc)
        return None
    logger.info(
        "HF model cache %r is read-only; downloads will use writable fallback: %s",
        hf_cache,
        fallback,
    )
    return fallback
