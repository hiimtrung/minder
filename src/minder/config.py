from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict, TomlConfigSettingsSource


class ServerConfig(BaseModel):
    name: str = "minder"
    version: str = "0.1.0"
    transport: str = "sse"
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "info"


class AuthConfig(BaseModel):
    enabled: bool = True
    jwt_secret: str = "dev-secret-key-change-me-in-prod"
    jwt_expiry_hours: int = 24
    api_key_prefix: str = "mk_"
    default_admin_email: str = "admin@example.com"


class EmbeddingConfig(BaseModel):
    provider: str = "llamacpp"
    model_name: str = "Qwen/Qwen3-Embedding-0.6B"
    model_path: str = "~/.minder/models/qwen3-embedding-0.6b.Q8_0.gguf"
    dimensions: int = 1024
    openai_api_key: Optional[str] = None
    openai_model: str = "text-embedding-3-small"


class LLMConfig(BaseModel):
    provider: str = "llamacpp"
    model_name: str = "Qwen3.5-0.8B"
    model_path: str = "~/.minder/models/qwen3.5-0.8b-instruct.Q4_K_M.gguf"
    context_length: int = 4096
    temperature: float = 0.1
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"


class VectorStoreConfig(BaseModel):
    provider: str = "milvus_lite"  # "milvus" (standalone) | "milvus_lite" | "memory"
    db_path: str = "~/.minder/data/milvus.db"  # used by milvus_lite only
    uri: str = "http://localhost:19530"  # used by milvus standalone
    collection_prefix: str = "minder_"


class RelationalStoreConfig(BaseModel):
    provider: str = "sqlite"  # "sqlite" | "mongodb"
    db_path: str = "~/.minder/data/minder.db"  # used by sqlite only


class MongoDBConfig(BaseModel):
    uri: str = "mongodb://localhost:27017"
    database: str = "minder"
    min_pool_size: int = 5
    max_pool_size: int = 50


class RedisConfig(BaseModel):
    uri: str = "redis://localhost:6379/0"
    prefix: str = "minder:"
    session_ttl: int = 86400
    cache_ttl: int = 3600


class RetrievalConfig(BaseModel):
    top_k: int = 10
    rerank_top_n: int = 5
    similarity_threshold: float = 0.7
    hybrid_alpha: float = 0.7


class CacheConfig(BaseModel):
    enabled: bool = True
    provider: str = "lru"  # "lru" | "redis"
    max_size: int = 1000  # used by lru only
    ttl_seconds: int = 3600


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
    auth: AuthConfig = Field(default_factory=AuthConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    relational_store: RelationalStoreConfig = Field(default_factory=RelationalStoreConfig)
    mongodb: MongoDBConfig = Field(default_factory=MongoDBConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    verification: VerificationConfig = Field(default_factory=VerificationConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    seeding: SeedingConfig = Field(default_factory=SeedingConfig)

    model_config = SettingsConfigDict(
        env_prefix="MINDER_",
        env_nested_delimiter="__", 
        toml_file="minder.toml"
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
