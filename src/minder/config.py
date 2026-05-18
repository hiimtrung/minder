from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict, TomlConfigSettingsSource


class ServerConfig(BaseModel):
    name: str = "minder"
    version: str = "0.1.0"
    transport: str = "sse"
    host: str = "0.0.0.0"
    port: int = 8800
    log_level: str = "info"


class DashboardConfig(BaseModel):
    base_path: str = "/dashboard"
    static_dir: str = "src/dashboard/dist"
    dev_server_url: str | None = None
    api_url: str | None = None


class AuthConfig(BaseModel):
    enabled: bool = True
    jwt_secret: str = "dev-secret-key-change-me-in-prod"
    jwt_expiry_hours: int = 24
    api_key_prefix: str = "mk_"
    client_api_key_prefix: str = "mkc_"
    client_token_expiry_minutes: int = 60
    default_admin_email: str = "admin@example.com"


class EmbeddingConfig(BaseModel):
    provider: str = "llama_cpp"
    runtime: str = "auto"  # "auto" | "llama_cpp" | "mock"
    llama_cpp_model_repo: str = "ggml-org/embeddinggemma-300M-GGUF"
    llama_cpp_model_file: str = "embeddinggemma-300M-Q8_0.gguf"
    dimensions: int = 768
    openai_api_key: Optional[str] = None
    openai_model: str = "text-embedding-3-small"


class LLMConfig(BaseModel):
    provider: str = "llama_cpp"  # "llama_cpp" | "openai"
    llama_cpp_model_repo: str = "ggml-org/gemma-4-E2B-it-GGUF"
    llama_cpp_model_file: str = "gemma-4-E2B-it-Q8_0.gguf"
    context_length: int = 16384
    temperature: float = 0.1
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"


class VectorStoreConfig(BaseModel):
    provider: str = "qdrant"  # "qdrant" | "memory"
    collection_prefix: str = "minder_"


class RelationalStoreConfig(BaseModel):
    provider: str = "qdrant"  # "qdrant" | "sqlite" | "postgresql"
    db_path: str = "minder.db"  # sqlite fallback
    uri: str = "postgresql+asyncpg://localhost/minder"  # postgresql only


class GraphStoreConfig(BaseModel):
    enabled: bool = True
    provider: str = "auto"  # "auto" mirrors relational_store.provider
    db_path: str = "~/.minder/data/graph.db"  # sqlite only
    uri: str = "postgresql+asyncpg://localhost/minder_graph"  # postgresql only


class QdrantConfig(BaseModel):
    url: str = "http://localhost:6333"
    api_key: Optional[str] = None
    prefer_grpc: bool = False
    collection_prefix: str = "minder_"



class RetrievalConfig(BaseModel):
    top_k: int = 10
    rerank_top_n: int = 5
    similarity_threshold: float = 0.7
    hybrid_alpha: float = 0.7


class MemoryConfig(BaseModel):
    agentic_recall: bool = False
    recall_min_score: float = 0.4
    recall_max_iterations: int = 3


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
    sandbox: str = "docker"
    timeout_seconds: int = 30
    docker_image: str = "minder-sandbox:latest"


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
    relational_store: RelationalStoreConfig = Field(
        default_factory=RelationalStoreConfig
    )
    graph_store: GraphStoreConfig = Field(default_factory=GraphStoreConfig)
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
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
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


MinderConfig = Settings
settings = Settings()
