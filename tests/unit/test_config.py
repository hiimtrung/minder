from minder.config import Settings


def test_default_config_loading():
    settings = Settings(_env_file=None)
    assert settings.server.name == "minder"
    assert settings.auth.enabled is True
    assert settings.embedding.dimensions == 1024
    assert settings.dashboard.dev_server_url in {None, ""}
    assert settings.dashboard.api_url in {None, ""}

def test_env_override(monkeypatch):
    monkeypatch.setenv("MINDER_SERVER__PORT", "9999")
    monkeypatch.setenv("MINDER_AUTH__JWT_SECRET", "super-secret")

    settings = Settings(_env_file=None)

    assert settings.server.port == 9999
    assert settings.auth.jwt_secret == "super-secret"


def test_dotenv_file_override(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "MINDER_SERVER__PORT=7777",
                "MINDER_DASHBOARD__DEV_SERVER_URL=http://localhost:8808/dashboard",
                "MINDER_DASHBOARD__API_URL=http://localhost:8800",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.server.port == 7777
    assert settings.dashboard.dev_server_url == "http://localhost:8808/dashboard"
    assert settings.dashboard.api_url == "http://localhost:8800"
