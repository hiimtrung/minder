"""
RBAC — role-based access control decorator.

Usage:
    @require_role(UserRole.ADMIN)
    async def admin_only_handler(*args, user: User, **kwargs):
        ...

The decorated function must receive the authenticated `user` as a keyword arg.
"""

import functools
from typing import Callable

from minder.auth.service import AuthError, ROLE_HIERARCHY, UserRole
from minder.models.user import User


def require_role(min_role: UserRole) -> Callable:
    """
    Decorator that enforces a minimum role on an async handler.

    Raises:
        AuthError(AUTH_NO_USER)            — if `user` kwarg is absent.
        AuthError(AUTH_INSUFFICIENT_ROLE)  — if user's role is below min_role.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            user: User | None = kwargs.get("user")
            if user is None:
                raise AuthError(
                    "AUTH_NO_USER",
                    "No authenticated user provided to role-guarded handler",
                )
            try:
                user_role = UserRole(user.role)
            except ValueError:
                raise AuthError(
                    "AUTH_UNKNOWN_ROLE",
                    f"Unrecognised role value: {user.role!r}",
                )

            user_level = ROLE_HIERARCHY.get(user_role, 0)
            required_level = ROLE_HIERARCHY.get(min_role, 0)

            if user_level < required_level:
                raise AuthError(
                    "AUTH_INSUFFICIENT_ROLE",
                    (
                        f"Role '{user_role.value}' is insufficient. "
                        f"Required: '{min_role.value}' or higher."
                    ),
                )
            return await func(*args, **kwargs)

        return wrapper

    return decorator
