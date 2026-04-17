from __future__ import annotations

import time
from dataclasses import dataclass

from minder.auth.principal import Principal
from minder.auth.service import AuthError
from minder.config import MinderConfig
from minder.store.interfaces import ICacheProvider


class RateLimitError(AuthError):
    def __init__(self, message: str) -> None:
        super().__init__("AUTH_RATE_LIMITED", message)


@dataclass(slots=True)
class RateLimitDecision:
    limit: int
    count: int
    remaining: int
    reset_at: int


class RateLimiter:
    def __init__(
        self,
        *,
        cache: ICacheProvider,
        config: MinderConfig,
    ) -> None:
        self._cache = cache
        self._config = config

    def enabled(self) -> bool:
        return self._config.rate_limit.enabled

    def _limit_for_principal(self, principal: Principal) -> int:
        if principal.principal_type == "client":
            return self._config.rate_limit.client_limit
        role = principal.role
        if role == "admin":
            return self._config.rate_limit.admin_limit
        if role == "readonly":
            return self._config.rate_limit.readonly_limit
        return self._config.rate_limit.member_limit

    def _key(self, principal: Principal, tool_name: str, window_start: int) -> str:
        return f"rate_limit:{principal.principal_type}:{principal.principal_id}:{tool_name}:{window_start}"

    async def enforce(self, *, principal: Principal, tool_name: str) -> RateLimitDecision:
        limit = self._limit_for_principal(principal)
        now = int(time.time())
        window = self._config.rate_limit.window_seconds
        window_start = now - (now % window)
        reset_at = window_start + window
        key = self._key(principal, tool_name, window_start)

        count = await self._cache.incr(key)
        if count == 1:
            await self._cache.expire(key, window)

        if count > limit:
            raise RateLimitError(
                f"Rate limit exceeded for {principal.principal_type} '{principal.principal_id}' on tool '{tool_name}'"
            )

        return RateLimitDecision(
            limit=limit,
            count=count,
            remaining=max(limit - count, 0),
            reset_at=reset_at,
        )

    async def get_usage(self, *, principal: Principal, tool_name: str) -> dict[str, int]:
        limit = self._limit_for_principal(principal)
        now = int(time.time())
        window = self._config.rate_limit.window_seconds
        window_start = now - (now % window)
        reset_at = window_start + window
        key = self._key(principal, tool_name, window_start)
        raw = await self._cache.get(key)
        count = int(raw or "0")
        return {
            "count": count,
            "limit": limit,
            "remaining": max(limit - count, 0),
            "reset_at": reset_at,
        }
