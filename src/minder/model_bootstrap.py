"""Model bootstrap — pre-download GGUF models at server startup.

Replaces the old ``scripts/download_models.sh`` workflow.  The server calls
``ensure_models_available()`` once during startup so that the embedding and LLM
providers never hit a cold download on the first real request.

Design
------
- No-op if both models are already present in the local HF Hub cache.
- Falls back gracefully: a download failure is logged as a warning and the
  server continues in mock mode; it does **not** abort startup.
- Cross-platform: Windows, macOS, and Linux (including Docker containers).
  Permission repairs use portable ``stat`` constants; symlink handling is
  delegated to ``huggingface_hub`` which already handles the Windows
  difference (copies instead of symlinks when ``os.symlink`` is unavailable).
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from minder.runtime import get_effective_hf_cache_dir, get_writable_hf_cache_dir

if TYPE_CHECKING:
    from minder.config import MinderConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_cached(repo_id: str, filename: str, cache_dir: str | None) -> bool:
    """Return True if *filename* from *repo_id* is already in the local cache.

    Uses ``local_files_only=True`` so no network call is made.  Any exception
    (including ``LocalEntryNotFoundError``) maps to False.
    """
    try:
        from huggingface_hub import hf_hub_download

        hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            cache_dir=cache_dir,
            local_files_only=True,
        )
        return True
    except Exception:
        return False


def _fix_permissions(local_path: str) -> None:
    """Ensure the downloaded blob and its ancestor cache dirs are readable.

    On Windows this is a no-op: Docker containers run Linux under WSL2 so the
    real permission fix happens there; native Windows Python processes rely on
    NTFS ACLs, which ``huggingface_hub`` already sets correctly.
    """
    if sys.platform == "win32":
        return

    import stat

    p = Path(local_path)
    targets: list[Path] = [p]

    # Walk up at most four levels (blob → blobs/ → models--…/ → cache_dir)
    # to fix directory execute bits without touching unrelated paths.
    parent = p.parent
    for _ in range(4):
        if not parent.exists() or parent == parent.parent:
            break
        targets.append(parent)
        parent = parent.parent

    for item in targets:
        try:
            current = item.lstat().st_mode  # lstat: don't follow symlinks
            if stat.S_ISLNK(current):
                # Symlinks themselves cannot be chmod'd on Linux — skip.
                continue
            if stat.S_ISDIR(current):
                # Ensure owner, group, and other can traverse (execute) the dir.
                item.chmod(current | stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
            elif stat.S_ISREG(current):
                # Readable by all, writable by owner.
                item.chmod(current | stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
        except OSError:
            # Read-only filesystem, immutable flag, or insufficient privilege.
            # Log at debug level — this is best-effort.
            logger.debug("Could not fix permissions on %s", item)


def _download_one(repo_id: str, filename: str, cache_dir: str | None) -> bool:
    """Download *filename* from *repo_id* into *cache_dir*.

    Returns True on success, False on failure.  Errors are logged as warnings
    so callers can decide whether to continue or abort.
    """
    try:
        from huggingface_hub import hf_hub_download

        logger.info(
            "[model-bootstrap] Downloading %s / %s  (cache: %s)",
            repo_id,
            filename,
            cache_dir or "<hf-default>",
        )
        local_path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            cache_dir=cache_dir,
        )
        _fix_permissions(local_path)
        logger.info("[model-bootstrap] Ready: %s", local_path)
        return True
    except Exception as exc:
        logger.warning(
            "[model-bootstrap] Download failed for %s / %s: %s"
            " — server will continue in mock mode until the model is available",
            repo_id,
            filename,
            exc,
        )
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ensure_models_available(config: MinderConfig) -> None:
    """Pre-download GGUF models required by the configured providers.

    Called synchronously during server startup (before the first request).
    Safe to call multiple times — downloads are skipped when files are already
    present in the local HF Hub cache.

    Providers skipped
    -----------------
    - ``embedding.provider != "llama_cpp"`` — no GGUF embedding model needed.
    - ``embedding.runtime == "mock"``        — mock mode, no model needed.
    - ``llm.provider != "llama_cpp"``        — OpenAI or other remote provider.
    """
    # Determine which models to check
    models: list[tuple[str, str, str]] = []

    if (
        config.embedding.provider == "llama_cpp"
        and config.embedding.runtime != "mock"
    ):
        models.append((
            config.embedding.llama_cpp_model_repo,
            config.embedding.llama_cpp_model_file,
            "embedding",
        ))

    if config.llm.provider == "llama_cpp":
        models.append((
            config.llm.llama_cpp_model_repo,
            config.llm.llama_cpp_model_file,
            "LLM",
        ))

    if not models:
        logger.debug("[model-bootstrap] No llama_cpp models configured — skipping.")
        return

    # Resolve the effective cache directory once for all models.
    # get_writable_hf_cache_dir() returns None when the env-configured dir is
    # already writable (most local dev setups).  get_effective_hf_cache_dir()
    # resolves that None to the actual env-configured path so we can pass it
    # explicitly to hf_hub_download's cache_dir parameter.
    cache_dir = get_effective_hf_cache_dir()

    logger.info(
        "[model-bootstrap] Checking %d model(s) in cache: %s",
        len(models),
        cache_dir or "<hf-default>",
    )

    for repo_id, filename, label in models:
        if _is_cached(repo_id, filename, cache_dir):
            logger.info(
                "[model-bootstrap] %s model already cached: %s / %s",
                label,
                repo_id,
                filename,
            )
            continue

        logger.info(
            "[model-bootstrap] %s model not found locally — starting download: %s / %s",
            label,
            repo_id,
            filename,
        )
        _download_one(repo_id, filename, cache_dir)
