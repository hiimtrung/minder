"""
Unit tests for Auth Service, RBAC decorator, and Auth Middleware.
Uses in-memory SQLite via RelationalStore.
"""

import uuid

import pytest

from minder.auth.middleware import AuthMiddleware
from minder.auth.rbac import require_role
from minder.auth.service import AuthError, AuthService, UserRole
from minder.config import MinderConfig
from minder.models.user import User
from minder.store.relational import RelationalStore

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def store() -> RelationalStore:
    s = RelationalStore(IN_MEMORY_URL)
    await s.init_db()
    yield s
    await s.dispose()


@pytest.fixture
def config() -> MinderConfig:
    return MinderConfig()


@pytest.fixture
def auth(store: RelationalStore, config: MinderConfig) -> AuthService:
    return AuthService(store=store, config=config)


@pytest.fixture
def middleware(auth: AuthService) -> AuthMiddleware:
    return AuthMiddleware(auth_service=auth)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    async def test_register_new_user_returns_user_and_key(
        self, auth: AuthService
    ) -> None:
        user, api_key = await auth.register_user(
            email="alice@example.com",
            username="alice",
            display_name="Alice",
        )
        assert user.email == "alice@example.com"
        assert user.role == UserRole.MEMBER.value
        assert api_key.startswith("mk_")

    async def test_register_default_role_is_member(self, auth: AuthService) -> None:
        user, _ = await auth.register_user(
            email="bob@example.com",
            username="bob",
            display_name="Bob",
        )
        assert user.role == "member"

    async def test_register_explicit_admin_role(self, auth: AuthService) -> None:
        user, _ = await auth.register_user(
            email="admin@example.com",
            username="admin",
            display_name="Admin",
            role=UserRole.ADMIN,
        )
        assert user.role == "admin"

    async def test_register_duplicate_email_raises(self, auth: AuthService) -> None:
        await auth.register_user(
            email="dup@example.com",
            username="dup1",
            display_name="Dup1",
        )
        with pytest.raises(AuthError) as exc:
            await auth.register_user(
                email="dup@example.com",
                username="dup2",
                display_name="Dup2",
            )
        assert exc.value.code == "AUTH_USER_EXISTS"

    async def test_register_duplicate_username_raises(self, auth: AuthService) -> None:
        await auth.register_user(
            email="u1@example.com",
            username="shared_name",
            display_name="U1",
        )
        with pytest.raises(AuthError) as exc:
            await auth.register_user(
                email="u2@example.com",
                username="shared_name",
                display_name="U2",
            )
        assert exc.value.code == "AUTH_USER_EXISTS"


# ---------------------------------------------------------------------------
# API Key Authentication
# ---------------------------------------------------------------------------


class TestApiKeyAuth:
    async def test_valid_api_key_returns_user(self, auth: AuthService) -> None:
        _, api_key = await auth.register_user(
            email="carol@example.com",
            username="carol",
            display_name="Carol",
        )
        user = await auth.authenticate_api_key(api_key)
        assert user.email == "carol@example.com"

    async def test_invalid_api_key_raises(self, auth: AuthService) -> None:
        with pytest.raises(AuthError) as exc:
            await auth.authenticate_api_key("mk_invalid_key_abc123")
        assert exc.value.code == "AUTH_INVALID_KEY"

    async def test_inactive_user_raises(
        self, auth: AuthService, store: RelationalStore
    ) -> None:
        user, api_key = await auth.register_user(
            email="dave@example.com",
            username="dave",
            display_name="Dave",
        )
        await store.update_user(user.id, is_active=False)
        with pytest.raises(AuthError) as exc:
            await auth.authenticate_api_key(api_key)
        assert exc.value.code == "AUTH_USER_INACTIVE"


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------


class TestJWT:
    async def test_issue_and_validate_jwt(self, auth: AuthService) -> None:
        user, _ = await auth.register_user(
            email="eve@example.com",
            username="eve",
            display_name="Eve",
        )
        token = auth.issue_jwt(user)
        assert isinstance(token, str)
        assert len(token) > 0

        payload = auth.validate_jwt(token)
        assert payload["sub"] == str(user.id)
        assert payload["email"] == "eve@example.com"
        assert payload["role"] == "member"

    async def test_validate_invalid_token_raises(self, auth: AuthService) -> None:
        with pytest.raises(AuthError) as exc:
            auth.validate_jwt("not.a.valid.token")
        assert exc.value.code == "AUTH_TOKEN_INVALID"

    async def test_get_user_from_valid_jwt(self, auth: AuthService) -> None:
        user, _ = await auth.register_user(
            email="frank@example.com",
            username="frank",
            display_name="Frank",
        )
        token = auth.issue_jwt(user)
        resolved = await auth.get_user_from_jwt(token)
        assert resolved.id == user.id

    async def test_get_user_from_jwt_unknown_user(
        self, auth: AuthService, store: RelationalStore, config: MinderConfig
    ) -> None:
        """JWT referencing a user that no longer exists."""
        import jwt as pyjwt
        from datetime import UTC, datetime, timedelta

        fake_payload = {
            "sub": str(uuid.uuid4()),  # non-existent
            "email": "ghost@example.com",
            "username": "ghost",
            "role": "member",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(hours=1),
        }
        token = pyjwt.encode(fake_payload, config.auth.jwt_secret, algorithm="HS256")
        with pytest.raises(AuthError) as exc:
            await auth.get_user_from_jwt(token)
        assert exc.value.code == "AUTH_USER_NOT_FOUND"


# ---------------------------------------------------------------------------
# API Key Rotation
# ---------------------------------------------------------------------------


class TestKeyRotation:
    async def test_rotate_returns_new_key(self, auth: AuthService) -> None:
        user, old_key = await auth.register_user(
            email="grace@example.com",
            username="grace",
            display_name="Grace",
        )
        new_key = await auth.rotate_api_key(user.id)
        assert new_key != old_key
        assert new_key.startswith("mk_")

    async def test_old_key_no_longer_valid(self, auth: AuthService) -> None:
        user, old_key = await auth.register_user(
            email="hank@example.com",
            username="hank",
            display_name="Hank",
        )
        await auth.rotate_api_key(user.id)
        with pytest.raises(AuthError) as exc:
            await auth.authenticate_api_key(old_key)
        assert exc.value.code == "AUTH_INVALID_KEY"

    async def test_new_key_valid_after_rotation(self, auth: AuthService) -> None:
        user, _ = await auth.register_user(
            email="iris@example.com",
            username="iris",
            display_name="Iris",
        )
        new_key = await auth.rotate_api_key(user.id)
        resolved = await auth.authenticate_api_key(new_key)
        assert resolved.id == user.id

    async def test_rotate_nonexistent_user_raises(self, auth: AuthService) -> None:
        with pytest.raises(AuthError) as exc:
            await auth.rotate_api_key(uuid.uuid4())
        assert exc.value.code == "AUTH_USER_NOT_FOUND"


# ---------------------------------------------------------------------------
# RBAC decorator
# ---------------------------------------------------------------------------


def _make_user(role: str) -> User:
    """Create a minimal in-memory User stub for RBAC tests."""
    return User(
        id=uuid.uuid4(),
        email=f"{role}@example.com",
        username=f"{role}_user",
        display_name=role.title(),
        api_key_hash="hash",
        role=role,
        settings={},
        is_active=True,
    )


class TestRBAC:
    async def test_admin_passes_admin_guard(self) -> None:
        @require_role(UserRole.ADMIN)
        async def handler(*, user: User) -> str:
            return "ok"

        result = await handler(user=_make_user("admin"))
        assert result == "ok"

    async def test_member_passes_member_guard(self) -> None:
        @require_role(UserRole.MEMBER)
        async def handler(*, user: User) -> str:
            return "ok"

        result = await handler(user=_make_user("member"))
        assert result == "ok"

    async def test_admin_passes_member_guard(self) -> None:
        @require_role(UserRole.MEMBER)
        async def handler(*, user: User) -> str:
            return "ok"

        result = await handler(user=_make_user("admin"))
        assert result == "ok"

    async def test_readonly_fails_member_guard(self) -> None:
        @require_role(UserRole.MEMBER)
        async def handler(*, user: User) -> str:
            return "ok"

        with pytest.raises(AuthError) as exc:
            await handler(user=_make_user("readonly"))
        assert exc.value.code == "AUTH_INSUFFICIENT_ROLE"

    async def test_member_fails_admin_guard(self) -> None:
        @require_role(UserRole.ADMIN)
        async def handler(*, user: User) -> str:
            return "ok"

        with pytest.raises(AuthError) as exc:
            await handler(user=_make_user("member"))
        assert exc.value.code == "AUTH_INSUFFICIENT_ROLE"

    async def test_missing_user_raises(self) -> None:
        @require_role(UserRole.MEMBER)
        async def handler(*, user: User | None = None) -> str:
            return "ok"

        with pytest.raises(AuthError) as exc:
            await handler()
        assert exc.value.code == "AUTH_NO_USER"


# ---------------------------------------------------------------------------
# AuthMiddleware
# ---------------------------------------------------------------------------


class TestAuthMiddleware:
    def test_extract_bearer_token_valid(self, middleware: AuthMiddleware) -> None:
        token = middleware.extract_bearer_token("Bearer mytoken123")
        assert token == "mytoken123"

    def test_extract_bearer_token_case_insensitive(
        self, middleware: AuthMiddleware
    ) -> None:
        token = middleware.extract_bearer_token("BEARER mytoken123")
        assert token == "mytoken123"

    def test_extract_missing_header_raises(self, middleware: AuthMiddleware) -> None:
        with pytest.raises(AuthError) as exc:
            middleware.extract_bearer_token(None)
        assert exc.value.code == "AUTH_MISSING_TOKEN"

    def test_extract_empty_header_raises(self, middleware: AuthMiddleware) -> None:
        with pytest.raises(AuthError) as exc:
            middleware.extract_bearer_token("")
        assert exc.value.code == "AUTH_MISSING_TOKEN"

    def test_extract_wrong_scheme_raises(self, middleware: AuthMiddleware) -> None:
        with pytest.raises(AuthError) as exc:
            middleware.extract_bearer_token("Basic dXNlcjpwYXNz")
        assert exc.value.code == "AUTH_INVALID_HEADER"

    async def test_authenticate_valid_jwt(
        self, middleware: AuthMiddleware, auth: AuthService
    ) -> None:
        user, _ = await auth.register_user(
            email="jwt_user@example.com",
            username="jwt_user",
            display_name="JWT User",
        )
        token = auth.issue_jwt(user)
        resolved = await middleware.authenticate(f"Bearer {token}")
        assert resolved.id == user.id

    async def test_authenticate_invalid_jwt_raises(
        self, middleware: AuthMiddleware
    ) -> None:
        with pytest.raises(AuthError) as exc:
            await middleware.authenticate("Bearer not_a_real_token")
        assert exc.value.code == "AUTH_TOKEN_INVALID"
