"""
Tests for the memory language normalization fix.

Root cause: minder_memory_store accepted any language value (e.g. "typescript")
but is_memory_record() only classified entries with language in MEMORY_LANGUAGES
as memories. This caused stored memories to silently vanish from
minder_memory_list and minder_memory_recall.

Fix: minder_memory_store normalizes the language to a memory-eligible value
("markdown") when the caller passes a non-memory language like "typescript".
The original language is preserved as a tag.
"""

from __future__ import annotations

import pytest

from minder.config import MinderConfig
from minder.store.relational import RelationalStore
from minder.tools.memory import MemoryTools, is_memory_record, MEMORY_LANGUAGES

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def store() -> RelationalStore:
    backend = RelationalStore(IN_MEMORY_URL)
    await backend.init_db()
    yield backend
    await backend.dispose()


@pytest.fixture
def config() -> MinderConfig:
    return MinderConfig()


class TestIsMemoryRecord:
    """Verify the is_memory_record filter function."""

    def test_accepts_all_memory_languages(self) -> None:
        from types import SimpleNamespace

        for lang in MEMORY_LANGUAGES:
            record = SimpleNamespace(language=lang, source_metadata=None)
            assert is_memory_record(record), f"language={lang!r} should be a memory"

    def test_rejects_programming_languages(self) -> None:
        from types import SimpleNamespace

        for lang in ("python", "typescript", "go", "rust", "java"):
            record = SimpleNamespace(language=lang, source_metadata=None)
            assert not is_memory_record(record), f"language={lang!r} should NOT be a memory"

    def test_rejects_when_source_metadata_present(self) -> None:
        from types import SimpleNamespace

        record = SimpleNamespace(language="markdown", source_metadata={"repo": "git"})
        assert not is_memory_record(record)


@pytest.mark.asyncio
class TestMemoryStoreLanguageNormalization:
    """Test that minder_memory_store normalizes non-memory languages."""

    async def test_store_with_memory_language_preserves_it(
        self, store: RelationalStore, config: MinderConfig
    ) -> None:
        tools = MemoryTools(store, config)
        result = await tools.minder_memory_store(
            title="English Memory",
            content="Some content",
            tags=["test"],
            language="en",
        )

        # Verify it's retrievable as a memory
        memories = await tools.minder_memory_list()
        assert len(memories) == 1
        assert memories[0]["id"] == result["id"]

    async def test_store_with_programming_language_normalizes_to_markdown(
        self, store: RelationalStore, config: MinderConfig
    ) -> None:
        """The core regression test for the bug."""
        tools = MemoryTools(store, config)
        result = await tools.minder_memory_store(
            title="TypeScript Gotcha",
            content="Some TypeScript-specific knowledge",
            tags=["ts", "gotcha"],
            language="typescript",
        )

        # The memory MUST be visible in memory_list (this was the bug)
        memories = await tools.minder_memory_list()
        assert len(memories) == 1, (
            f"Expected 1 memory, got {len(memories)}. "
            "Memories stored with non-memory languages must still be retrievable."
        )
        assert memories[0]["id"] == result["id"]

        # The original language should be preserved as a tag
        assert "lang:typescript" in result["tags"]

    async def test_store_preserves_existing_tags(
        self, store: RelationalStore, config: MinderConfig
    ) -> None:
        tools = MemoryTools(store, config)
        result = await tools.minder_memory_store(
            title="Go Pattern",
            content="Use context.Context for cancellation",
            tags=["go", "patterns", "concurrency"],
            language="go",
        )

        # All original tags should still be present
        assert "go" in result["tags"]
        assert "patterns" in result["tags"]
        assert "concurrency" in result["tags"]
        # Plus the language tag
        assert "lang:go" in result["tags"]

    async def test_store_no_duplicate_lang_tag(
        self, store: RelationalStore, config: MinderConfig
    ) -> None:
        """If the caller already has a lang: tag, don't duplicate it."""
        tools = MemoryTools(store, config)
        result = await tools.minder_memory_store(
            title="Rust Memory",
            content="Use Cow<str> for flexible borrowing",
            tags=["rust", "lang:rust"],
            language="rust",
        )

        # Should not have duplicate lang:rust
        assert result["tags"].count("lang:rust") == 1

    async def test_memory_language_does_not_add_lang_tag(
        self, store: RelationalStore, config: MinderConfig
    ) -> None:
        """When language is already memory-eligible, no lang: tag is needed."""
        tools = MemoryTools(store, config)
        result = await tools.minder_memory_store(
            title="Markdown Memory",
            content="Some knowledge",
            tags=["general"],
            language="markdown",
        )

        # No lang:markdown tag should be added
        assert "lang:markdown" not in result["tags"]
        assert result["tags"] == ["general"]

    async def test_mixed_languages_all_retrievable(
        self, store: RelationalStore, config: MinderConfig
    ) -> None:
        """Store memories with various languages and verify all are listed."""
        tools = MemoryTools(store, config)
        
        languages = ["en", "typescript", "python", "markdown", "go", "vi"]
        for i, lang in enumerate(languages):
            await tools.minder_memory_store(
                title=f"Memory {i}",
                content=f"Content for {lang}",
                tags=[f"tag{i}"],
                language=lang,
            )

        memories = await tools.minder_memory_list()
        assert len(memories) == len(languages), (
            f"Expected {len(languages)} memories but got {len(memories)}. "
            f"All languages should produce retrievable memories."
        )
