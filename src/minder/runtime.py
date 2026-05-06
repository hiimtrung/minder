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
