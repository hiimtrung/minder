"""Seed default SubAgent definitions on startup."""

from __future__ import annotations

import logging

from minder.store.interfaces import IOperationalStore
from minder.tools.seeds.default_agents import DEFAULT_AGENTS

logger = logging.getLogger(__name__)


async def seed_default_agents(store: IOperationalStore) -> None:
    """Upsert default agents — always keep system-managed agents up to date.

    User-created agents (is_default=False) are never touched.
    Default agents (is_default=True) are always updated to the latest
    system_prompt, tools list, and metadata so that fixes to the startup
    sequence and tool discovery instructions take effect without a DB reset.
    """
    for defn in DEFAULT_AGENTS:
        name = defn["name"]
        existing = await store.get_agent_by_name(name)
        if existing is None:
            await store.create_agent(**defn)
            logger.info("Seeded default SubAgent: %r", name)
        else:
            await store.upsert_agent(name, **{k: v for k, v in defn.items() if k != "name"})
            logger.info("Updated default SubAgent: %r", name)
