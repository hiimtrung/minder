"""
Auth Service — user registration, API key management, JWT issuance/validation.

Error codes follow the project standard:
  AUTH_USER_EXISTS        — duplicate registration
  AUTH_USER_NOT_FOUND     — user lookup miss
  AUTH_USER_INACTIVE      — deactivated account
  AUTH_INVALID_KEY        — API key mismatch
  AUTH_TOKEN_EXPIRED      — JWT past exp claim
  AUTH_TOKEN_INVALID      — malformed or tampered JWT
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Tuple

import jwt
from passlib.context import CryptContext  # type: ignore[import-untyped]

from minder.config import MinderConfig
from minder.models.user import User
from minder.store.relational import RelationalStore

# ---------------------------------------------------------------------------
# Role hierarchy
# ---------------------------------------------------------------------------


class UserRole(str, Enum):
    ADMIN = "admin"
    MEMBER = "member"
    READONLY = "readonly"


ROLE_HIERARCHY: dict[UserRole, int] = {
    UserRole.ADMIN: 3,
    UserRole.MEMBER: 2,
    UserRole.READONLY: 1,
}

# ---------------------------------------------------------------------------
# Domain exception
# ---------------------------------------------------------------------------


class AuthError(Exception):
    """Raised for all auth-layer failures. Carries a structured error code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)

    def __repr__(self) -> str:
        return f"AuthError(code={self.code!r}, message={self.message!r})"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

_pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


class AuthService:
    """Stateless auth service. Injected with store + config at construction."""

    def __init__(self, store: RelationalStore, config: MinderConfig) -> None:
        self._store = store
        self._config = config

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_api_key(self) -> str:
        """Return a cryptographically random API key with the configured prefix."""
        token = secrets.token_urlsafe(32)
        return f"{self._config.auth.api_key_prefix}{token}"

    @staticmethod
    def _hash_secret(secret: str) -> str:
        return _pwd_context.hash(secret)

    @staticmethod
    def _verify_secret(secret: str, hashed: str) -> bool:
        return _pwd_context.verify(secret, hashed)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def register_user(
        self,
        email: str,
        username: str,
        display_name: str,
        role: UserRole = UserRole.MEMBER,
    ) -> Tuple[User, str]:
        """
        Create a new user account.

        Returns:
            (user, plaintext_api_key) — caller must surface the key once; it
            is never stored in plaintext.

        Raises:
            AuthError(AUTH_USER_EXISTS) if email is already registered.
        """
        if await self._store.get_user_by_email(email):
            raise AuthError("AUTH_USER_EXISTS", f"Email '{email}' is already registered")

        if await self._store.get_user_by_username(username):
            raise AuthError("AUTH_USER_EXISTS", f"Username '{username}' is already taken")

        api_key = self._generate_api_key()
        user = await self._store.create_user(
            id=uuid.uuid4(),
            email=email,
            username=username,
            display_name=display_name,
            api_key_hash=self._hash_secret(api_key),
            role=role.value,
            is_active=True,
            settings={},
        )
        return user, api_key

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def authenticate_api_key(self, api_key: str) -> User:
        """
        Authenticate with a plaintext API key.

        Scans active users and verifies bcrypt hashes.  Suitable for low
        write-frequency auth (MCP connect).  For high-throughput use-cases,
        add an indexed prefix column.

        Raises:
            AuthError(AUTH_INVALID_KEY) on mismatch.
            AuthError(AUTH_USER_INACTIVE) if account is disabled.
        """
        users = await self._store.list_users(active_only=False)
        for user in users:
            if self._verify_secret(api_key, user.api_key_hash):
                if not user.is_active:
                    raise AuthError("AUTH_USER_INACTIVE", "User account is inactive")
                await self._store.update_user(user.id, last_login=datetime.now(UTC))
                return user
        raise AuthError("AUTH_INVALID_KEY", "Invalid API key")

    # ------------------------------------------------------------------
    # JWT
    # ------------------------------------------------------------------

    def issue_jwt(self, user: User) -> str:
        """Issue a signed JWT for the user."""
        now = datetime.now(UTC)
        payload = {
            "sub": str(user.id),
            "email": user.email,
            "username": user.username,
            "role": user.role,
            "iat": now,
            "exp": now + timedelta(hours=self._config.auth.jwt_expiry_hours),
        }
        return jwt.encode(payload, self._config.auth.jwt_secret, algorithm="HS256")

    def validate_jwt(self, token: str) -> dict:
        """
        Decode and validate a JWT.

        Returns the decoded payload dict.

        Raises:
            AuthError(AUTH_TOKEN_EXPIRED) if past exp.
            AuthError(AUTH_TOKEN_INVALID) on any other JWT error.
        """
        try:
            return jwt.decode(
                token,
                self._config.auth.jwt_secret,
                algorithms=["HS256"],
            )
        except jwt.ExpiredSignatureError:
            raise AuthError("AUTH_TOKEN_EXPIRED", "JWT token has expired")
        except jwt.InvalidTokenError as exc:
            raise AuthError("AUTH_TOKEN_INVALID", f"Invalid JWT: {exc}")

    async def get_user_from_jwt(self, token: str) -> User:
        """Validate JWT and return the corresponding active user."""
        payload = self.validate_jwt(token)
        user_id = uuid.UUID(payload["sub"])
        user = await self._store.get_user_by_id(user_id)
        if not user:
            raise AuthError("AUTH_USER_NOT_FOUND", "User referenced by token not found")
        if not user.is_active:
            raise AuthError("AUTH_USER_INACTIVE", "User account is inactive")
        return user

    # ------------------------------------------------------------------
    # Key rotation
    # ------------------------------------------------------------------

    async def rotate_api_key(self, user_id: uuid.UUID) -> str:
        """
        Generate and store a new API key for the user.

        Returns the new plaintext key (display once).

        Raises:
            AuthError(AUTH_USER_NOT_FOUND) if user doesn't exist.
        """
        user = await self._store.get_user_by_id(user_id)
        if not user:
            raise AuthError("AUTH_USER_NOT_FOUND", f"User {user_id} not found")

        new_key = self._generate_api_key()
        await self._store.update_user(user_id, api_key_hash=self._hash_secret(new_key))
        return new_key
