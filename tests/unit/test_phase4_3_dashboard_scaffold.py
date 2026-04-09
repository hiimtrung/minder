from __future__ import annotations

import json
from pathlib import Path


def test_phase4_3_dashboard_web_scaffold_exists() -> None:
    root = Path("src/dashboard")

    assert (root / "package.json").exists()
    assert (root / "astro.config.mjs").exists()
    assert (root / "tsconfig.json").exists()
    assert (root / "src/styles/global.css").exists()
    assert (root / "src/layouts/DashboardLayout.astro").exists()
    assert (root / "src/pages/login.astro").exists()
    assert (root / "src/pages/setup.astro").exists()
    assert (root / "src/pages/clients/index.astro").exists()
    assert (root / "src/lib/api/admin.ts").exists()
    assert (root / "src/scripts/login-page.ts").exists()
    assert (root / "src/scripts/setup-page.ts").exists()
    assert (root / "src/scripts/clients-page.ts").exists()


def test_phase4_3_dashboard_web_package_contract() -> None:
    package_json = json.loads(Path("src/dashboard/package.json").read_text())
    astro_config = Path("src/dashboard/astro.config.mjs").read_text()

    assert package_json["name"] == "minder-dashboard"
    assert package_json["type"] == "module"
    assert package_json["packageManager"] == "bun@1.2.21"
    assert package_json["engines"]["node"] == ">=22.12.0"
    assert "dev" in package_json["scripts"]
    assert "build" in package_json["scripts"]
    assert package_json["dependencies"]["astro"] == "^6.1.4"
    assert "tailwindcss" in package_json["dependencies"]
    assert "typescript" in package_json["devDependencies"]
    assert 'base: "/dashboard"' in astro_config


def test_phase4_3_dashboard_admin_api_client_targets_typed_backend_contracts() -> None:
    admin_api = Path("src/dashboard/src/lib/api/admin.ts").read_text()

    assert "/v1/admin/clients" in admin_api
    assert "/v1/admin/audit" in admin_api
    assert "/v1/auth/token-exchange" in admin_api
    assert "/v1/admin/setup" in admin_api
    assert "/v1/admin/login" in admin_api
    assert "/v1/admin/session" in admin_api
    assert "export type ClientPayload" in admin_api
    assert "export async function listClients" in admin_api
    assert "export async function getClientDetail" in admin_api
    assert "export async function rotateClientKey" in admin_api
    assert "export async function revokeClientKeys" in admin_api
    assert "export async function testClientConnection" in admin_api


def test_phase4_3_dashboard_pages_use_real_admin_api_calls() -> None:
    login_page = Path("src/dashboard/src/pages/login.astro").read_text()
    setup_page = Path("src/dashboard/src/pages/setup.astro").read_text()
    registry_page = Path("src/dashboard/src/pages/clients/index.astro").read_text()
    layout = Path("src/dashboard/src/layouts/DashboardLayout.astro").read_text()
    login_script = Path("src/dashboard/src/scripts/login-page.ts").read_text()
    setup_script = Path("src/dashboard/src/scripts/setup-page.ts").read_text()
    registry_script = Path("src/dashboard/src/scripts/clients-page.ts").read_text()

    assert 'src={loginPageScript}' in login_page
    assert 'src={setupPageScript}' in setup_page
    assert 'src={clientsPageScript}' in registry_page
    assert "loginAdmin" in login_script
    assert "setupAdmin" in setup_script
    assert "listClients" in registry_script
    assert "createClient" in registry_script
    assert "getClientDetail" in registry_script
    assert "getClientOnboarding" in registry_script
    assert "rotateClientKey" in registry_script
    assert "revokeClientKeys" in registry_script
    assert "testClientConnection" in registry_script
    assert "/dashboard/clients" in layout
    assert "/dashboard/login" in layout
    assert "/dashboard/setup" in layout
