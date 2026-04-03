from __future__ import annotations

import argparse
import asyncio
from typing import Any

from minder.auth.service import AuthService, UserRole
from minder.config import Settings
from minder.server import build_store
from minder.store.relational import RelationalStore


async def ensure_admin(
    store: RelationalStore,
    config: Settings,
    *,
    email: str,
    username: str,
    display_name: str,
) -> dict[str, Any]:
    auth = AuthService(store, config)
    existing = await store.get_user_by_email(email)
    if existing is not None:
        return {"created": False, "user_id": str(existing.id), "api_key": None}
    user, api_key = await auth.register_user(
        email=email,
        username=username,
        display_name=display_name,
        role=UserRole.ADMIN,
    )
    return {"created": True, "user_id": str(user.id), "api_key": api_key}


async def _main_async() -> None:
    parser = argparse.ArgumentParser(description="Create the initial Minder admin user.")
    parser.add_argument("--email", default=None)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--display-name", default="Admin")
    args = parser.parse_args()

    config = Settings()
    store = build_store(config)
    await store.init_db()
    try:
        result = await ensure_admin(
            store,
            config,
            email=args.email or config.auth.default_admin_email,
            username=args.username,
            display_name=args.display_name,
        )
    finally:
        await store.dispose()

    if result["created"]:
        print(f"Admin created: {result['user_id']}")
        print(f"API key: {result['api_key']}")
    else:
        print(f"Admin already exists: {result['user_id']}")


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
