from __future__ import annotations

import argparse
import asyncio
import subprocess
import tempfile
import uuid
from pathlib import Path

from minder.config import Settings
from minder.embedding.local import LocalEmbeddingProvider
from minder.server import build_store
from minder.store.relational import RelationalStore


def _resolve_skill_source(source: str) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    path = Path(source).expanduser()
    if path.exists():
        return path, None
    temp_dir = tempfile.TemporaryDirectory()
    subprocess.run(
        ["git", "clone", "--depth", "1", source, temp_dir.name],
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(temp_dir.name), temp_dir


async def seed_skills(store: RelationalStore, config: Settings, source: str) -> dict[str, int]:
    base_dir, temp_dir = _resolve_skill_source(source)
    imported = 0
    skipped = 0
    embedder = LocalEmbeddingProvider(
        fastembed_model=config.embedding.fastembed_model,
        fastembed_cache_dir=config.embedding.fastembed_cache_dir,
        dimensions=min(config.embedding.dimensions, 16),
        runtime="auto",
    )
    try:
        files = sorted(
            path for path in base_dir.rglob("*") if path.is_file() and path.suffix.lower() in {".md", ".txt"}
        )
        existing_titles = {skill.title for skill in await store.list_skills()}
        for file_path in files:
            title = file_path.stem
            if title in existing_titles:
                skipped += 1
                continue
            content = file_path.read_text(encoding="utf-8")
            await store.create_skill(
                id=uuid.uuid4(),
                title=title,
                content=content,
                language="markdown",
                tags=["seeded"],
                embedding=embedder.embed(content),
                usage_count=0,
                quality_score=0.0,
            )
            existing_titles.add(title)
            imported += 1
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()
    return {"imported": imported, "skipped": skipped}


async def _main_async() -> None:
    parser = argparse.ArgumentParser(description="Seed skills into Minder.")
    parser.add_argument("source", nargs="?", default=None)
    args = parser.parse_args()

    config = Settings()
    source = args.source or config.seeding.skills_repo
    if not source:
        raise SystemExit("No skill source provided. Pass a path/repo or configure seeding.skills_repo.")

    store = build_store(config)
    await store.init_db()
    try:
        result = await seed_skills(store, config, source)
    finally:
        await store.dispose()
    print(result)


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
