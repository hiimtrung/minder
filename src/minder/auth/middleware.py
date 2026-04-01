"""
Auth Middleware — JWT extraction and validation for SSE / HTTP connections.

Usage:
    middleware = AuthMiddleware(auth_service)
    user = await middleware.authenticate(request.headers.get("Authorization"))
"""

from typing import Optional

from minder.auth.service import AuthError, AuthService
from minder.models.user import User


class AuthMiddleware:
    """
    Extracts Bearer JWT from the Authorization header and returns the
    authenticated User.  Raises AuthError on any failure so callers can
    convert it to the appropriate HTTP/transport error.
    """

    def __init__(self, auth_service: AuthService) -> None:
        self._auth = auth_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_bearer_token(self, authorization: Optional[str]) -> str:
        """
        Parse 'Bearer <token>' from the Authorization header value.

        Raises:
            AuthError(AUTH_MISSING_TOKEN)  — header absent or empty.
            AuthError(AUTH_INVALID_HEADER) — wrong scheme or malformed.
        """
        if not authorization or not authorization.strip():
            raise AuthError("AUTH_MISSING_TOKEN", "Authorization header is required")

        parts = authorization.strip().split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise AuthError(
                "AUTH_INVALID_HEADER",
                "Authorization header must use 'Bearer <token>' scheme",
            )
        token = parts[1].strip()
        if not token:
            raise AuthError("AUTH_MISSING_TOKEN", "Bearer token value is empty")
        return token

    async def authenticate(self, authorization: Optional[str]) -> User:
        """
        Full authentication flow: extract token → validate JWT → return user.

        Raises AuthError on any failure.
        """
        token = self.extract_bearer_token(authorization)
        return await self._auth.get_user_from_jwt(token)
