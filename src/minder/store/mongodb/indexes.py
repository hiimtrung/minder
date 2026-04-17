"""
MongoDB collection indexes — called once at application startup.
"""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:  # type: ignore[type-arg]
    """Create all required MongoDB indexes (idempotent)."""

    # Users
    users = db["users"]
    await users.create_index([("email", ASCENDING)], unique=True)
    await users.create_index([("username", ASCENDING)], unique=True)
    await users.create_index([("company_id", ASCENDING)])

    # Clients
    clients = db["clients"]
    await clients.create_index([("slug", ASCENDING)], unique=True)
    await clients.create_index([("created_by_user_id", ASCENDING)])

    client_api_keys = db["client_api_keys"]
    await client_api_keys.create_index([("client_id", ASCENDING)])
    await client_api_keys.create_index([("status", ASCENDING)])

    client_sessions = db["client_sessions"]
    await client_sessions.create_index([("client_id", ASCENDING)])
    await client_sessions.create_index([("access_token_id", ASCENDING)], unique=True)

    audit_logs = db["audit_logs"]
    await audit_logs.create_index([("actor_id", ASCENDING)])
    await audit_logs.create_index([("event_type", ASCENDING)])

    # Skills
    skills = db["skills"]
    await skills.create_index([("company_id", ASCENDING)])
    await skills.create_index([("title", ASCENDING)])
    await skills.create_index([("language", ASCENDING)])

    # Prompts
    prompts = db["prompts"]
    await prompts.create_index([("company_id", ASCENDING)])
    await prompts.create_index([("name", ASCENDING)], unique=True)

    # Sessions
    sessions = db["sessions"]
    await sessions.create_index([("company_id", ASCENDING)])
    await sessions.create_index([("user_id", ASCENDING)])
    await sessions.create_index([("repo_id", ASCENDING)])

    # Workflows
    workflows = db["workflows"]
    await workflows.create_index([("company_id", ASCENDING)])
    await workflows.create_index([("name", ASCENDING)])

    # Repositories
    repos = db["repositories"]
    await repos.create_index([("company_id", ASCENDING)])
    await repos.create_index([("repo_name", ASCENDING)])

    # Repository Workflow States
    workflow_states = db["repository_workflow_states"]
    await workflow_states.create_index([("repo_id", ASCENDING)])
    await workflow_states.create_index([("session_id", ASCENDING)])

    # Documents
    documents = db["documents"]
    await documents.create_index([("doc_type", ASCENDING)])
    await documents.create_index([("project", ASCENDING)])
    await documents.create_index(
        [("source_path", ASCENDING), ("project", ASCENDING)],
        unique=True,
    )

    # History
    history = db["history"]
    await history.create_index([("session_id", ASCENDING)])

    # Errors
    errors = db["errors"]
    await errors.create_index([("error_code", ASCENDING)])
