"""Seed default workflows on first startup."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from minder.store.interfaces import IOperationalStore

logger = logging.getLogger(__name__)

DEFAULT_WORKFLOWS: list[dict[str, Any]] = [
    {
        "name": "tdd",
        "version": 1,
        "description": "Test-Driven Development workflow ensuring tests are written before implementation.",
        "enforcement": "strict",
        "steps": [
            {
                "name": "Problem Analysis",
                "description": "Analyze the problem, understand requirements, and plan the implementation.",
                "gate": "Provide a clear problem analysis and implementation plan.",
            },
            {
                "name": "Test Writing",
                "description": "Write failing tests that define the expected behavior and cover edge cases.",
                "gate": "Verify that tests are written and fail as expected (red state).",
            },
            {
                "name": "Implementation",
                "description": "Implement the minimum code necessary to make the tests pass.",
                "gate": "Verify that all tests pass (green state) and no regressions are introduced.",
            },
            {
                "name": "Review",
                "description": "Review the code for quality, adherence to patterns, and clean up technical debt.",
                "gate": "Code review approval and verification of quality standards.",
            },
        ],
        "policies": {"block_step_skips": True},
        "default_for_repo": True,
    }
]


async def seed_default_workflows(store: IOperationalStore) -> None:
    """Insert default workflows only if they do not already exist.

    Never overwrites user-modified defaults — guards by name existence check.
    """
    for defn in DEFAULT_WORKFLOWS:
        name = defn["name"]
        existing = await store.get_workflow_by_name(name)
        if existing is not None:
            logger.debug("Workflow %r already exists, skipping seed", name)
            continue
        
        # Make a copy and inject an id if not present
        payload = dict(defn)
        payload["id"] = uuid.uuid4()
        
        await store.create_workflow(**payload)
        logger.info("Seeded default workflow: %r", name)
