from minder.config import Settings


def test_default_config_loading():
    settings = Settings(_env_file=None)
    assert settings.server.name == "minder"
    assert settings.auth.enabled is True
    assert settings.embedding.dimensions == 768
    assert settings.dashboard.dev_server_url in {None, ""}
    assert settings.dashboard.api_url in {None, ""}


def test_env_override(monkeypatch):
    monkeypatch.setenv("MINDER_SERVER__PORT", "9999")
    monkeypatch.setenv("MINDER_MONGODB__URI", "mongodb://example:27017")

    settings = Settings(_env_file=None)

    assert settings.server.port == 9999
    assert settings.mongodb.uri == "mongodb://example:27017"


def test_dotenv_file_override(tmp_path, monkeypatch):
    monkeypatch.delenv("MINDER_SERVER__PORT", raising=False)
    monkeypatch.delenv("MINDER_REDIS__URI", raising=False)
    monkeypatch.delenv("MINDER_VECTOR_STORE__PROVIDER", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "MINDER_SERVER__PORT=7777",
                "MINDER_REDIS__URI=redis://example:6379/7",
                "MINDER_VECTOR_STORE__PROVIDER=milvus",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.server.port == 7777
    assert settings.redis.uri == "redis://example:6379/7"
    assert settings.vector_store.provider == "milvus"
