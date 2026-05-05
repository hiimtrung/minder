"""Seed default SubAgent definitions on first startup."""

from __future__ import annotations

import logging

from minder.store.interfaces import IOperationalStore
from minder.tools.seeds.default_agents import DEFAULT_AGENTS

logger = logging.getLogger(__name__)


async def seed_default_agents(store: IOperationalStore) -> None:
    """Insert default agents only if they do not already exist.

    Never overwrites user-modified defaults — guards by name existence check.
    """
    for defn in DEFAULT_AGENTS:
        name = defn["name"]
        existing = await store.get_agent_by_name(name)
        if existing is not None:
            logger.debug("SubAgent %r already exists, skipping seed", name)
            continue
        await store.create_agent(**defn)
        logger.info("Seeded default SubAgent: %r", name)
