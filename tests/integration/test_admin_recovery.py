from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import pytest_asyncio

from minder.auth.service import AuthError, AuthService, UserRole
from minder.config import MinderConfig
from minder.store.relational import RelationalStore

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


def _load_module(path: Path, module_name: str):  # noqa: ANN001, ANN201
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest_asyncio.fixture
async def store() -> RelationalStore:
    backend = RelationalStore(IN_MEMORY_URL)
    await backend.init_db()
    yield backend
    await backend.dispose()


@pytest.fixture
def config() -> MinderConfig:
    return MinderConfig()


@pytest.fixture
def auth(store: RelationalStore, config: MinderConfig) -> AuthService:
    return AuthService(store=store, config=config)


@pytest.mark.asyncio
async def test_reset_admin_api_key_rotates_key_and_writes_audit_log(
    store: RelationalStore,
    config: MinderConfig,
    auth: AuthService,
) -> None:
    admin, old_key = await auth.register_user(
        email="recover-admin@example.com",
        username="recover_admin",
        display_name="Recover Admin",
        role=UserRole.ADMIN,
    )
    module = _load_module(Path("scripts/reset_admin_api_key.py"), "reset_admin_api_key_script")

    result = await module.reset_admin_api_key(
        store,
        config,
        username="recover_admin",
    )

    assert result["rotated"] is True
    assert result["user_id"] == str(admin.id)
    assert result["api_key"].startswith("mk_")
    assert result["api_key"] != old_key

    with pytest.raises(AuthError) as old_exc:
        await auth.authenticate_api_key(old_key)
    assert old_exc.value.code == "AUTH_INVALID_KEY"

    resolved = await auth.authenticate_api_key(result["api_key"])
    assert resolved.id == admin.id

    events = await store.list_audit_logs(actor_id=str(admin.id))
    assert any(event.event_type == "admin.api_key_rotated" for event in events)


@pytest.mark.asyncio
async def test_reset_admin_api_key_rejects_non_admin_user(
    store: RelationalStore,
    config: MinderConfig,
    auth: AuthService,
) -> None:
    await auth.register_user(
        email="member@example.com",
        username="member_user",
        display_name="Member User",
        role=UserRole.MEMBER,
    )
    module = _load_module(Path("scripts/reset_admin_api_key.py"), "reset_admin_api_key_script_non_admin")

    with pytest.raises(ValueError, match="admin"):
        await module.reset_admin_api_key(
            store,
            config,
            username="member_user",
        )


@pytest.mark.asyncio
async def test_reset_admin_api_key_raises_for_missing_user(
    store: RelationalStore,
    config: MinderConfig,
) -> None:
    module = _load_module(Path("scripts/reset_admin_api_key.py"), "reset_admin_api_key_script_missing")

    with pytest.raises(ValueError, match="not found"):
        await module.reset_admin_api_key(
            store,
            config,
            username="missing_admin",
        )
