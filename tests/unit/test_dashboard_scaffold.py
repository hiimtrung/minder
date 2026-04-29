from __future__ import annotations

import json
from pathlib import Path


def test_phase4_3_dashboard_web_scaffold_exists() -> None:
    src = Path("src/dashboard/src")

    assert Path("package.json").exists()
    assert Path("astro.config.mjs").exists()
    assert Path("tsconfig.json").exists()
    assert Path("src/dashboard/public/favicon.png").exists()
    assert (src / "styles/global.css").exists()
    assert (src / "layouts/DashboardLayout.astro").exists()
    assert (src / "pages/login.astro").exists()
    assert (src / "pages/setup.astro").exists()
    assert (src / "pages/clients/index.astro").exists()
    assert (src / "components/ClientRegistryShell.astro").exists()
    assert (src / "components/ClientDetailShell.astro").exists()
    assert (src / "middleware.ts").exists()
    assert (src / "lib/api/admin.ts").exists()
    assert (src / "scripts/login-page.ts").exists()
    assert (src / "scripts/setup-page.ts").exists()
    assert (src / "scripts/clients-page.ts").exists()
    assert (src / "scripts/session-header.ts").exists()


def test_phase4_3_dashboard_web_package_contract() -> None:
    package_json = json.loads(Path("package.json").read_text())
    astro_config = Path("astro.config.mjs").read_text()

    assert package_json["name"] == "minder"
    assert package_json["type"] == "module"
    assert package_json["packageManager"] == "bun@1.2.21"
    assert package_json["engines"]["node"] == ">=22.12.0"
    assert "dev" in package_json["scripts"]
    assert "build" in package_json["scripts"]
    assert package_json["scripts"]["dev"] == "astro dev"
    assert package_json["scripts"]["preview"] == "astro preview"
    assert package_json["dependencies"]["astro"] == "^6.1.4"
    assert "tailwindcss" in package_json["dependencies"]
    assert "typescript" in package_json["devDependencies"]
    assert "const env = loadEnv(" in astro_config
    assert 'process.env.NODE_ENV ?? "development"' in astro_config
    assert 'base: "/dashboard"' in astro_config
    assert "server:" in astro_config
    assert "port: 8808" in astro_config
    assert "preview:" in astro_config
    assert "env.PUBLIC_API_URL ?? env.API_URL ?? \"\"" in astro_config
    assert '"import.meta.env.PUBLIC_API_URL"' in astro_config


def test_phase4_3_dashboard_admin_api_client_targets_typed_backend_contracts() -> None:
    admin_api = Path("src/dashboard/src/lib/api/admin.ts").read_text()

    assert "/v1/admin/clients" in admin_api
    assert "/v1/admin/audit" in admin_api
    assert "/v1/auth/token-exchange" in admin_api
    assert "/v1/admin/setup" in admin_api
    assert "/v1/admin/login" in admin_api
    assert "/v1/admin/session" in admin_api
    assert "PUBLIC_API_URL" in admin_api
    assert "apiUrl(path)" in admin_api
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
    registry_shell = Path("src/dashboard/src/components/ClientRegistryShell.astro").read_text()
    detail_shell = Path("src/dashboard/src/components/ClientDetailShell.astro").read_text()
    middleware = Path("src/dashboard/src/middleware.ts").read_text()
    layout = Path("src/dashboard/src/layouts/DashboardLayout.astro").read_text()
    login_script = Path("src/dashboard/src/scripts/login-page.ts").read_text()
    setup_script = Path("src/dashboard/src/scripts/setup-page.ts").read_text()
    registry_script = Path("src/dashboard/src/scripts/clients-page.ts").read_text()
    session_script = Path("src/dashboard/src/scripts/session-header.ts").read_text()

    assert '<script src="../scripts/login-page.ts"></script>' in login_page
    assert '<script src="../scripts/setup-page.ts"></script>' in setup_page
    assert "ClientRegistryShell" in registry_page
    assert '<script src="../scripts/clients-page.ts"></script>' in registry_shell
    assert '<script src="../scripts/clients-page.ts"></script>' in detail_shell
    assert 'context.rewrite("/dashboard/clients")' in middleware
    assert "loginAdmin" in login_script
    assert "setupAdmin" in setup_script
    assert "syncVisibleClients" in registry_script
    assert "createClient" in registry_script
    assert "getClientDetail" in registry_script
    assert "getClientOnboarding" in registry_script
    assert "rotateClientKey" in registry_script
    assert "revokeClientKeys" in registry_script
    assert "testClientConnection" in registry_script
    assert "getAdminSession" in session_script
    assert "logoutAdmin" in session_script
    assert "navLinks?" in layout
    assert "navDescription?" in layout
    assert "sessionControls?" in layout
    assert "dashboard-toast-region" in layout
    assert 'rel="icon"' in layout
    assert '/dashboard/favicon.png' in layout
    # Login page no longer has a static "First-Time Setup" nav link; the link
    # to /dashboard/setup is rendered dynamically by login-page.ts when the
    # bootstrap-state API reports no admin users yet (fresh install only).
    assert '/dashboard/setup' in login_page
    assert 'setup-hint' in login_page
    assert 'Admin Login' in setup_page
    assert 'Client Registry' in registry_shell
    assert 'sessionControls={true}' in registry_shell
    assert 'Client Detail' in detail_shell
    assert 'sessionControls={true}' in detail_shell
