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
import json
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Tuple

import jwt
from passlib.context import CryptContext  # type: ignore[import-untyped]
from passlib.exc import UnknownHashError  # type: ignore[import-untyped]

from minder.auth.principal import AdminUserPrincipal, ClientPrincipal, Principal
from minder.config import MinderConfig
from minder.models.user import User
from minder.store.interfaces import ICacheProvider, IOperationalStore

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

    def __init__(
        self,
        store: IOperationalStore,
        config: MinderConfig,
        cache: ICacheProvider | None = None,
    ) -> None:
        self._store = store
        self._config = config
        self._cache = cache
        self._client_session_cache: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_api_key(self) -> str:
        """Return a cryptographically random API key with the configured prefix."""
        token = secrets.token_urlsafe(32)
        return f"{self._config.auth.api_key_prefix}{token}"

    def _generate_client_api_key(self) -> str:
        token = secrets.token_urlsafe(32)
        return f"{self._config.auth.client_api_key_prefix}{token}"

    @staticmethod
    def _hash_secret(secret: str) -> str:
        return _pwd_context.hash(secret)

    @staticmethod
    def _verify_secret(secret: str, hashed: str) -> bool:
        return _pwd_context.verify(secret, hashed)

    async def _session_store_set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        encoded = json.dumps(value, default=str)
        if self._cache is not None:
            await self._cache.set(key, encoded, ttl=ttl_seconds)
            return
        self._client_session_cache[key] = encoded

    async def _session_store_get(self, key: str) -> dict[str, Any] | None:
        raw: str | None
        if self._cache is not None:
            raw = await self._cache.get(key)
        else:
            raw = self._client_session_cache.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def register_user(
        self,
        email: str,
        username: str,
        display_name: str,
        role: UserRole | str = UserRole.MEMBER,
        password: str | None = None,
    ) -> Tuple[User, str]:
        """
        Create a new user account.

        Returns:
            (user, plaintext_api_key) — caller must surface the key once; it
            is never stored in plaintext.

        If ``password`` is supplied it is hashed and stored separately so the
        user can authenticate with username + password *in addition to* the API
        key.

        Raises:
            AuthError(AUTH_USER_EXISTS) if email or username is already taken.
        """
        if await self._store.get_user_by_email(email):
            raise AuthError("AUTH_USER_EXISTS", f"Email '{email}' is already registered")

        if await self._store.get_user_by_username(username):
            raise AuthError("AUTH_USER_EXISTS", f"Username '{username}' is already taken")

        role_str = role.value if isinstance(role, UserRole) else str(role)

        api_key = self._generate_api_key()
        password_hash = self._hash_secret(password) if password else None
        user = await self._store.create_user(
            id=uuid.uuid4(),
            email=email,
            username=username,
            display_name=display_name,
            api_key_hash=self._hash_secret(api_key),
            password_hash=password_hash,
            role=role_str,
            is_active=True,
            settings={},
        )
        return user, api_key

    async def has_admin_users(self) -> bool:
        """Check if any admin users exist in the system."""
        return await self._store.has_admin_users()

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def authenticate_api_key(self, api_key: str) -> User:
        users = await self._store.list_users(active_only=False)
        import logging
        logger = logging.getLogger("minder.auth")
        logger.debug(f"Checking API key against {len(users)} users")
        for user in users:
            try:
                matches = self._verify_secret(api_key, user.api_key_hash)
            except UnknownHashError:
                continue
            if matches:
                if not user.is_active:
                    raise AuthError("AUTH_USER_INACTIVE", "User account is inactive")
                await self._store.update_user(user.id, last_login=datetime.now(UTC))
                return user
        raise AuthError("AUTH_INVALID_KEY", "Invalid API key")

    async def authenticate_username_password(self, username: str, password: str) -> User:
        """Authenticate with username + password.

        Raises:
            AuthError(AUTH_USER_NOT_FOUND)  — username not found
            AuthError(AUTH_PASSWORD_NOT_SET) — user has no password configured
            AuthError(AUTH_INVALID_KEY)      — password mismatch
            AuthError(AUTH_USER_INACTIVE)    — account deactivated
        """
        user = await self._store.get_user_by_username(username)
        if user is None:
            # Return a generic message to avoid username enumeration
            raise AuthError("AUTH_INVALID_KEY", "Invalid username or password")
        if not user.is_active:
            raise AuthError("AUTH_USER_INACTIVE", "User account is inactive")
        password_hash = getattr(user, "password_hash", None)
        if not password_hash:
            raise AuthError(
                "AUTH_PASSWORD_NOT_SET",
                "Password login is not configured for this account. Use your API key instead.",
            )
        try:
            if not self._verify_secret(password, password_hash):
                raise AuthError("AUTH_INVALID_KEY", "Invalid username or password")
        except UnknownHashError:
            raise AuthError("AUTH_INVALID_KEY", "Invalid username or password")
        await self._store.update_user(user.id, last_login=datetime.now(UTC))
        return user

    async def set_password(self, user_id: uuid.UUID, password: str) -> None:
        """Set or update the login password for an existing user."""
        await self._store.update_user(user_id, password_hash=self._hash_secret(password))

    async def register_client(
        self,
        *,
        name: str,
        slug: str,
        created_by_user_id: uuid.UUID,
        description: str = "",
        owner_team: str | None = None,
        transport_modes: list[str] | None = None,
        tool_scopes: list[str] | None = None,
        repo_scopes: list[str] | None = None,
        workflow_scopes: list[str] | None = None,
        rate_limit_policy: dict[str, Any] | None = None,
    ) -> tuple[Any, str]:
        if await self._store.get_client_by_slug(slug):
            raise AuthError("AUTH_CLIENT_EXISTS", f"Client slug '{slug}' is already registered")

        creator = await self._store.get_user_by_id(created_by_user_id)
        if creator is None:
            raise AuthError("AUTH_USER_NOT_FOUND", "Creator user not found")

        client = await self._store.create_client(
            id=uuid.uuid4(),
            name=name,
            slug=slug,
            description=description,
            status="active",
            created_by_user_id=created_by_user_id,
            owner_team=owner_team,
            transport_modes=transport_modes or ["sse", "stdio"],
            tool_scopes=tool_scopes or [],
            repo_scopes=repo_scopes or [],
            workflow_scopes=workflow_scopes or [],
            rate_limit_policy=rate_limit_policy or {},
        )
        client_api_key = self._generate_client_api_key()
        await self._store.create_client_api_key(
            id=uuid.uuid4(),
            client_id=client.id,
            key_prefix=client_api_key[:12],
            secret_hash=self._hash_secret(client_api_key),
            status="active",
            created_by_user_id=created_by_user_id,
        )
        await self._store.create_audit_log(
            id=uuid.uuid4(),
            actor_type="admin_user",
            actor_id=str(created_by_user_id),
            event_type="client.created",
            resource_type="client",
            resource_id=str(client.id),
            outcome="success",
            audit_metadata={"slug": slug},
        )
        return client, client_api_key

    async def create_client_api_key(
        self,
        *,
        client_id: uuid.UUID,
        created_by_user_id: uuid.UUID,
    ) -> str:
        client = await self._store.get_client_by_id(client_id)
        if client is None:
            raise AuthError("AUTH_CLIENT_NOT_FOUND", "Client not found")
        creator = await self._store.get_user_by_id(created_by_user_id)
        if creator is None:
            raise AuthError("AUTH_USER_NOT_FOUND", "Creator user not found")

        client_api_key = self._generate_client_api_key()
        await self._store.create_client_api_key(
            id=uuid.uuid4(),
            client_id=client_id,
            key_prefix=client_api_key[:12],
            secret_hash=self._hash_secret(client_api_key),
            status="active",
            created_by_user_id=created_by_user_id,
        )
        await self._store.create_audit_log(
            id=uuid.uuid4(),
            actor_type="admin_user",
            actor_id=str(created_by_user_id),
            event_type="client.key_created",
            resource_type="client",
            resource_id=str(client_id),
            outcome="success",
            audit_metadata={"client_slug": getattr(client, "slug", None)},
        )
        return client_api_key

    async def revoke_client_api_keys(
        self,
        client_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID | None = None,
    ) -> None:
        now = datetime.now(UTC)
        client = await self._store.get_client_by_id(client_id)
        for key in await self._store.list_client_api_keys(client_id):
            await self._store.update_client_api_key(
                key.id,
                status="revoked",
                revoked_at=now,
            )
        if actor_user_id is not None:
            await self._store.create_audit_log(
                id=uuid.uuid4(),
                actor_type="admin_user",
                actor_id=str(actor_user_id),
                event_type="client.key_revoked",
                resource_type="client",
                resource_id=str(client_id),
                outcome="success",
                audit_metadata={"client_slug": getattr(client, "slug", None)},
            )

    async def authenticate_client_api_key(self, client_api_key: str) -> Any:
        if not client_api_key.startswith(self._config.auth.client_api_key_prefix):
            raise AuthError("AUTH_INVALID_CLIENT_KEY", "Invalid client API key")

        clients = await self._store.list_clients()
        for client in clients:
            if getattr(client, "status", "active") != "active":
                continue
            for key in await self._store.list_client_api_keys(client.id):
                if getattr(key, "status", "active") != "active":
                    continue
                try:
                    matches = self._verify_secret(client_api_key, key.secret_hash)
                except UnknownHashError:
                    continue
                if matches:
                    await self._store.update_client_api_key(
                        key.id,
                        last_used_at=datetime.now(UTC),
                    )
                    return client
        raise AuthError("AUTH_INVALID_CLIENT_KEY", "Invalid client API key")

    async def exchange_client_api_key(
        self,
        client_api_key: str,
        *,
        requested_scopes: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        client = await self.authenticate_client_api_key(client_api_key)
        allowed_scopes = list(getattr(client, "tool_scopes", []))
        requested = requested_scopes or allowed_scopes
        effective_scopes = [scope for scope in requested if scope in allowed_scopes]
        if not effective_scopes:
            effective_scopes = allowed_scopes

        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=self._config.auth.client_token_expiry_minutes)
        token_id = str(uuid.uuid4())
        session = await self._store.create_client_session(
            id=uuid.uuid4(),
            client_id=client.id,
            access_token_id=token_id,
            status="active",
            scopes=effective_scopes,
            issued_at=now,
            expires_at=expires_at,
            last_seen_at=now,
            session_metadata=metadata or {},
        )
        await self._session_store_set(
            f"client_session:{token_id}",
            {
                "client_id": str(client.id),
                "client_slug": client.slug,
                "scopes": effective_scopes,
                "repo_scope": list(getattr(client, "repo_scopes", [])),
                "session_id": str(session.id),
            },
            ttl_seconds=self._config.auth.client_token_expiry_minutes * 60,
        )
        payload = {
            "sub": str(client.id),
            "ptype": "client",
            "slug": client.slug,
            "scopes": effective_scopes,
            "repo_scope": list(getattr(client, "repo_scopes", [])),
            "jti": token_id,
            "iat": now,
            "exp": expires_at,
        }
        token = jwt.encode(payload, self._config.auth.jwt_secret, algorithm="HS256")
        await self._store.create_audit_log(
            id=uuid.uuid4(),
            actor_type="client",
            actor_id=str(client.id),
            event_type="client.token_exchanged",
            resource_type="client_session",
            resource_id=str(session.id),
            outcome="success",
            audit_metadata={"scopes": effective_scopes},
        )
        return {
            "access_token": token,
            "expires_in": self._config.auth.client_token_expiry_minutes * 60,
            "token_type": "Bearer",
            "client_id": str(client.id),
        }

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

    async def get_principal_from_token(self, token: str) -> Principal:
        payload = self.validate_jwt(token)
        if payload.get("ptype") == "client":
            token_id = payload.get("jti")
            if not token_id:
                raise AuthError("AUTH_TOKEN_INVALID", "Client token missing jti")
            cached = await self._session_store_get(f"client_session:{token_id}")
            if cached is None:
                raise AuthError("AUTH_TOKEN_INVALID", "Client session not found or expired")
            client = await self._store.get_client_by_id(uuid.UUID(payload["sub"]))
            if client is None or getattr(client, "status", "active") != "active":
                raise AuthError("AUTH_CLIENT_NOT_FOUND", "Client referenced by token not found")
            session = await self._store.get_client_session_by_token_id(token_id)
            if session is not None:
                await self._store.update_client_session(session.id, last_seen_at=datetime.now(UTC))
            return ClientPrincipal(
                client_id=client.id,
                client_slug=client.slug,
                scopes=list(cached.get("scopes", [])),
                repo_scope=list(cached.get("repo_scope", [])),
                metadata={"session_id": cached.get("session_id")},
            )
        user = await self.get_user_from_jwt(token)
        return AdminUserPrincipal(user)

    async def get_principal_from_client_key(
        self,
        client_api_key: str,
        *,
        requested_scopes: list[str] | None = None,
    ) -> Principal:
        exchange = await self.exchange_client_api_key(
            client_api_key,
            requested_scopes=requested_scopes,
        )
        return await self.get_principal_from_token(exchange["access_token"])

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
