from __future__ import annotations

import argparse
import asyncio
import uuid
from typing import Any

from minder.auth.service import AuthService
from minder.config import Settings
from minder.server import build_store
from minder.store.interfaces import IOperationalStore


async def reset_admin_api_key(
    store: IOperationalStore,
    config: Settings,
    *,
    username: str,
) -> dict[str, Any]:
    auth = AuthService(store, config)
    user = await store.get_user_by_username(username)
    if user is None:
        raise ValueError(f"User '{username}' not found")
    if getattr(user, "role", None) != "admin":
        raise ValueError(f"User '{username}' is not an admin")

    new_key = await auth.rotate_api_key(user.id)
    await store.create_audit_log(
        id=uuid.uuid4(),
        actor_type="admin_user",
        actor_id=str(user.id),
        event_type="admin.api_key_rotated",
        resource_type="user",
        resource_id=str(user.id),
        outcome="success",
        audit_metadata={"username": username, "via": "reset_admin_api_key.py"},
    )
    return {"rotated": True, "user_id": str(user.id), "api_key": new_key}


async def _main_async() -> None:
    parser = argparse.ArgumentParser(description="Rotate an existing admin API key.")
    parser.add_argument("--username", required=True)
    args = parser.parse_args()

    config = Settings()
    store = build_store(config)
    await store.init_db()
    try:
        result = await reset_admin_api_key(
            store,
            config,
            username=args.username,
        )
    finally:
        await store.dispose()

    print(f"Admin API key rotated: {result['user_id']}")
    print(f"API key: {result['api_key']}")


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
