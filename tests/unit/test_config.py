from minder.config import Settings


def test_default_config_loading():
    settings = Settings()
    assert settings.server.name == "minder"
    assert settings.auth.enabled is True
    assert settings.embedding.dimensions == 1024

def test_env_override(monkeypatch):
    monkeypatch.setenv("MINDER_SERVER__PORT", "9999")
    monkeypatch.setenv("MINDER_AUTH__JWT_SECRET", "super-secret")

    settings = Settings()

    assert settings.server.port == 9999
    assert settings.auth.jwt_secret == "super-secret"
