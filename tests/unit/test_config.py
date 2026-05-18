from minder.config import Settings
from minder.bootstrap.providers import build_graph_store



def test_default_config_loading():
    settings = Settings(_env_file=None)
    assert settings.server.name == "minder"
    assert settings.auth.enabled is True
    assert settings.embedding.dimensions == 768
    assert settings.dashboard.dev_server_url in {None, ""}
    assert settings.dashboard.api_url in {None, ""}


def test_env_override(monkeypatch):
    monkeypatch.setenv("MINDER_SERVER__PORT", "9999")

    settings = Settings(_env_file=None)

    assert settings.server.port == 9999


def test_dotenv_file_override(tmp_path, monkeypatch):
    monkeypatch.delenv("MINDER_SERVER__PORT", raising=False)
    monkeypatch.delenv("MINDER_VECTOR_STORE__PROVIDER", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "MINDER_SERVER__PORT=7777",
                "MINDER_VECTOR_STORE__PROVIDER=memory",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.server.port == 7777
    assert settings.vector_store.provider == "memory"


def test_graph_store_defaults_to_auto_qdrant_for_qdrant() -> None:
    settings = Settings(_env_file=None)

    graph_store = build_graph_store(settings)
    
    from minder.store.qdrant.graph_store import QdrantGraphStore
    assert isinstance(graph_store, QdrantGraphStore)


def test_graph_store_env_override(monkeypatch) -> None:
    monkeypatch.setenv("MINDER_GRAPH_STORE__PROVIDER", "postgresql")
    monkeypatch.setenv("MINDER_GRAPH_STORE__URI", "postgresql+asyncpg://localhost/custom_graph")

    settings = Settings(_env_file=None)

    assert settings.graph_store.provider == "postgresql"
    assert settings.graph_store.uri == "postgresql+asyncpg://localhost/custom_graph"
