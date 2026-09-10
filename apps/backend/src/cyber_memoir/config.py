from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://memoir:memoir@localhost:55432/memoir"
    redis_url: str = "redis://localhost:56379/0"
    opensearch_url: str = "http://localhost:59200"
    search_index: str = "memoir-v1"
    storage_backend: str = "s3"
    storage_path: str = ".data/artifacts"
    s3_endpoint: str = "http://localhost:59000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "memoir-evidence"
    reviewer_token: str = ""
    submitter_token: str = ""
    cors_origins: str = "http://localhost:3100"
    mcp_allowed_hosts: str = "localhost:*,127.0.0.1:*,[::1]:*"
    mcp_allowed_origins: str = "http://localhost:*,http://127.0.0.1:*"
    embedding_backend: str = "disabled"
    embedding_model: str = "BAAI/bge-m3"
    reranker_backend: str = "disabled"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    asr_model: str = "small"
    auto_media: bool = False
    task_timeout_seconds: int = 1800
    max_material_bytes: int = 16 * 1024 * 1024
    # Retrieval fusion. Tunable so the gold set can sweep them; see ADR 0004.
    rrf_k: int = 60
    rrf_weight_exact_alias: float = 3.0
    rrf_weight_bm25: float = 1.0
    rrf_weight_vector: float = 1.0
    retrieval_channel_limit: int = 100
    retrieval_per_source_cap: int = 4
    retrieval_candidate_cap: int = 50
    # Reranker score below which a chunk cannot support an answer (ADR 0004).
    # Only enforceable when a calibrated scorer ran; 0 disables the floor entirely.
    answer_score_floor: float = 0.35


@lru_cache
def settings() -> Settings:
    return Settings()
