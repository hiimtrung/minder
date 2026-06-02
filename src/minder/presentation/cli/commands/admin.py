"""Admin management CLI commands (password reset, user listing)."""
from __future__ import annotations

import asyncio
import sys


def _run(coro):
    return asyncio.run(coro)


async def _reset_password(username: str | None, new_password: str) -> int:
    from minder.config import Settings
    from minder.bootstrap.providers import build_store
    from minder.auth.service import AuthService

    config = Settings()
    store = build_store(config)
    await store.init_db()

    users = await store.list_users()
    if not users:
        print("No admin users found in the database.")
        return 1

    if username:
        target = next((u for u in users if u.username == username), None)
        if target is None:
            print(f"User '{username}' not found. Available users:")
            for u in users:
                print(f"  {u.username}")
            return 1
    else:
        # Default to the first admin
        admins = [u for u in users if u.role == "admin"]
        target = admins[0] if admins else users[0]

    auth = AuthService(store, config)
    await auth.set_password(target.id, new_password)
    print(f"Password reset for user '{target.username}' (email: {target.email}).")
    print("You can now log in at the Minder dashboard with your new password.")
    return 0


async def _list_users() -> int:
    from minder.config import Settings
    from minder.bootstrap.providers import build_store

    config = Settings()
    store = build_store(config)
    await store.init_db()

    users = await store.list_users()
    if not users:
        print("No users found.")
        return 0

    print(f"{'Username':<20} {'Role':<10} {'Email':<30} {'Has password'}")
    print("-" * 75)
    for u in users:
        has_pw = "yes" if getattr(u, "password_hash", None) else "no"
        print(f"{u.username:<20} {u.role:<10} {u.email:<30} {has_pw}")
    return 0


def reset_password_command(args) -> int:
    if len(args.password) < 8:
        print("Error: password must be at least 8 characters.", file=sys.stderr)
        return 1
    return _run(_reset_password(args.username, args.password))


def list_users_command(args) -> int:
    return _run(_list_users())
