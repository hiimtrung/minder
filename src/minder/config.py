import sys
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, TomlConfigSettingsSource


def _bundle_base_dir() -> Path | None:
    """Return the PyInstaller bundle directory when running as a frozen app.

    PyInstaller sets ``sys.frozen = True`` and ``sys._MEIPASS`` to the temp
    directory where bundled resources are extracted.  Returns ``None`` when
    running from source (normal development).
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", "."))
    return None


def _package_version() -> str:
    try:
        from importlib.metadata import version as _v
        return _v("minder")
    except Exception:
        return "0.6.9"


class ServerConfig(BaseModel):
    name: str = "minder"
    version: str = Field(default_factory=_package_version)
    transport: str = "sse"
    host: str = "0.0.0.0"
    port: int = 8800
    log_level: str = "info"
    http_timeout_keep_alive: int = 10


class DashboardConfig(BaseModel):
    base_path: str = "/dashboard"
    static_dir: str = "src/dashboard/dist"
    dev_server_url: str | None = None
    api_url: str | None = None

    @model_validator(mode="after")
    def _resolve_bundled_static_dir(self) -> "DashboardConfig":
        """In PyInstaller frozen mode, resolve static_dir to the bundled dashboard."""
        bundle = _bundle_base_dir()
        if bundle is None:
            return self
        bundled = bundle / "dashboard_dist"
        if bundled.is_dir():
            self.static_dir = str(bundled)
        return self


class AuthConfig(BaseModel):
    enabled: bool = True
    jwt_secret: str = "dev-secret-key-change-me-in-prod"
    jwt_expiry_hours: int = 24
    api_key_prefix: str = "mk_"
    client_api_key_prefix: str = "mkc_"
    client_token_expiry_minutes: int = 60
    default_admin_email: str = "admin@example.com"


class EmbeddingConfig(BaseModel):
    runtime: str = "auto"  # "auto" | "llama_cpp" | "mock"
    llama_cpp_model_repo: str = "ggml-org/embeddinggemma-300M-GGUF"
    # Q4_K_M uses ~45% less RAM than Q8_0 with negligible embedding quality loss.
    llama_cpp_model_file: str = "embeddinggemma-300M-Q4_K_M.gguf"
    dimensions: int = 768


class LLMConfig(BaseModel):
    provider: str = "llama_cpp"  # "llama_cpp" | "openai"
    runtime: str = "auto"  # "auto" | "llama_cpp" | "mock"
    llama_cpp_model_repo: str = "ggml-org/gemma-4-E2B-it-GGUF"
    llama_cpp_model_file: str = "gemma-4-E2B-it-Q4_K_M.gguf"
    # context_length is the UPPER BOUND requested.  The actual value used by the
    # engine is further capped by hardware detection (see hardware.py) to keep
    # KV-cache + Metal compute buffers within safe limits for the current device.
    # 8192 is a good default: enough for long conversations while staying well
    # within the 16 GB unified-memory budget of an M4 Mac Mini.
    context_length: int = 8192
    temperature: float = 0.1
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    timeout_seconds: float = 120.0
    max_concurrent: int = 1


class VectorStoreConfig(BaseModel):
    provider: str = "turbovec"  # "turbovec" | "milvus" | "memory"


class RelationalStoreConfig(BaseModel):
    provider: str = "sqlite"  # "sqlite" | "postgresql"
    db_path: str = "~/.minder/data/minder.db"
    uri: str = "postgresql+asyncpg://localhost/minder"  # postgresql only


class GraphStoreConfig(BaseModel):
    enabled: bool = True
    provider: str = "auto"  # "auto" mirrors relational_store.provider
    db_path: str = "~/.minder/data/graph.db"  # sqlite only
    uri: str = "postgresql+asyncpg://localhost/minder_graph"  # postgresql only


class MilvusConfig(BaseModel):
    db_path: str = "~/.minder/data/vectors.db"


class TurbovecConfig(BaseModel):
    db_path: str = "~/.minder/data/vectors.tvim"


class RetrievalConfig(BaseModel):
    top_k: int = 10
    rerank_top_n: int = 5
    similarity_threshold: float = 0.7
    hybrid_alpha: float = 0.7
    ingest_cooldown_secs: float = 60.0


class MemoryConfig(BaseModel):
    agentic_recall: bool = True
    recall_min_score: float = 0.4
    recall_max_iterations: int = 3


class SkillConfig(BaseModel):
    agentic_recall: bool = True


class SessionConfig(BaseModel):
    agentic_restore: bool = False
    restore_recall_count: int = 8


class GraphConfig(BaseModel):
    runtime: str = "langgraph"
    enable_parallel_retrieval: bool = False
    enable_checkpointing: bool = True
    checkpoint_ttl_days: int = 7


class CacheConfig(BaseModel):
    enabled: bool = True
    max_size: int = 1000
    ttl_seconds: int = 3600


class RateLimitConfig(BaseModel):
    enabled: bool = False
    window_seconds: int = 60
    admin_limit: int = 120
    member_limit: int = 60
    readonly_limit: int = 20
    client_limit: int = 90


class VerificationConfig(BaseModel):
    enabled: bool = True
    sandbox: str = "subprocess"
    timeout_seconds: int = 30


class WorkflowConfig(BaseModel):
    enforcement: str = "strict"
    default_workflow: str = "tdd"
    repo_state_dir: str = ".minder"
    block_step_skips: bool = True
    orchestration_runtime: str = "internal"


class SeedingConfig(BaseModel):
    skills_repo: str = ""
    skills_branch: str = "main"
    skills_path: str = "skills/"


class Settings(BaseSettings):
    server: ServerConfig = Field(default_factory=ServerConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    relational_store: RelationalStoreConfig = Field(default_factory=RelationalStoreConfig)
    graph_store: GraphStoreConfig = Field(default_factory=GraphStoreConfig)
    milvus: MilvusConfig = Field(default_factory=MilvusConfig)
    turbovec: TurbovecConfig = Field(default_factory=TurbovecConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    skill: SkillConfig = Field(default_factory=SkillConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    verification: VerificationConfig = Field(default_factory=VerificationConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    seeding: SeedingConfig = Field(default_factory=SeedingConfig)

    model_config = SettingsConfigDict(
        env_prefix="MINDER_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        toml_file="minder.toml",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        # In PyInstaller frozen mode, resolve minder.toml from the bundle
        # directory so the sidecar finds its default config.
        bundle = _bundle_base_dir()
        if bundle is not None:
            bundled_toml = bundle / "minder.toml"
            if bundled_toml.is_file():
                toml_source = TomlConfigSettingsSource(
                    settings_cls,
                    toml_file=bundled_toml,
                )
            else:
                toml_source = TomlConfigSettingsSource(settings_cls)
        else:
            toml_source = TomlConfigSettingsSource(settings_cls)

        return (
            init_settings,
            env_settings,
            dotenv_settings,
            toml_source,
            file_secret_settings,
        )


MinderConfig = Settings
settings = Settings()
