from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mcp.server.fastmcp import FastMCP

from minder.prompts import PromptRegistry
from minder.store.interfaces import IOperationalStore


def _dynamic_prompt(name: str, template: str) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        title=name.replace("_", " ").title(),
        description=f"Prompt {name}",
        content_template=template,
        arguments=["value"],
    )


@pytest.mark.asyncio
async def test_sync_registers_and_removes_dynamic_prompts() -> None:
    app = FastMCP(name="test-prompts")
    store = AsyncMock(spec=IOperationalStore)
    store.list_prompts.return_value = [_dynamic_prompt("custom_prompt", "Use {value}")]

    PromptRegistry.register(app, store=store)
    await PromptRegistry.sync(app, store)

    manager = app._prompt_manager
    assert manager.get_prompt("debug") is not None
    assert manager.get_prompt("custom_prompt") is not None

    custom_prompt = manager.get_prompt("custom_prompt")
    rendered = await custom_prompt.render({"value": "repo/a"})
    assert "repo/a" in str(rendered[0])

    store.list_prompts.return_value = []
    await PromptRegistry.sync(app, store)

    assert manager.get_prompt("custom_prompt") is None
    assert manager.get_prompt("debug") is not None


@pytest.mark.asyncio
async def test_sync_allows_database_override_of_builtin_prompt() -> None:
    app = FastMCP(name="test-prompts")
    store = AsyncMock(spec=IOperationalStore)
    store.list_prompts.return_value = [_dynamic_prompt("debug", "Override {value}")]

    PromptRegistry.register(app, store=store)
    await PromptRegistry.sync(app, store)

    debug_prompt = app._prompt_manager.get_prompt("debug")
    rendered = await debug_prompt.render({"value": "incident-42"})
    assert "Override incident-42" in str(rendered[0])


@pytest.mark.asyncio
async def test_builtin_tdd_prompt_renders_without_required_arguments() -> None:
    app = FastMCP(name="test-prompts")

    PromptRegistry.register(app)

    tdd_prompt = app._prompt_manager.get_prompt("tdd_step")
    rendered = await tdd_prompt.render({})

    assert "Current Workflow Step: Test Writing" in str(rendered[0])
