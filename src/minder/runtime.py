from __future__ import annotations

import importlib.util
import logging
import signal
import subprocess
import sys
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

    Some CI runners report AVX2 in /proc/cpuinfo but the hypervisor blocks
    the instructions, causing an unrecoverable SIGILL.  We probe by running
    a subprocess that initialises the llama.cpp backend; if the subprocess
    is killed by SIGILL (returncode == -signal.SIGILL) we mark the library
    as unavailable and fall back to mock mode.  Result is cached for the
    lifetime of the process.
    """
    global _LLAMA_CPP_PROBE
    if _LLAMA_CPP_PROBE is not None:
        return _LLAMA_CPP_PROBE

    if not module_available("llama_cpp"):
        _LLAMA_CPP_PROBE = False
        return False

    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                # Instantiating Llama triggers ggml_backend_reg_count → ggml_cpu_init.
                # /dev/null causes a model-load error (returncode 1) on healthy CPUs;
                # SIGILL kills the process (returncode -4) on unsupported CPUs.
                "from llama_cpp import Llama; Llama(model_path='/dev/null', verbose=False)",
            ],
            capture_output=True,
            timeout=30,
        )
        _LLAMA_CPP_PROBE = proc.returncode != -signal.SIGILL
    except Exception as exc:
        logger.warning("llama.cpp usability probe error: %s", exc)
        _LLAMA_CPP_PROBE = False

    if not _LLAMA_CPP_PROBE:
        logger.warning(
            "llama.cpp unavailable on this CPU (SIGILL probe). Falling back to mock mode."
        )
    return _LLAMA_CPP_PROBE
