"""Configuração lida do ambiente (.env em desenvolvimento, Secrets no Kubernetes)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    release: str = "0.1.0"

    # Usuário de privilégio mínimo da aplicação (ver db/init/02_app_role.sh)
    database_url: SecretStr

    # Chave do HMAC que pseudonimiza order_id em traces e logs. Nunca registrar o ID cru.
    order_id_hmac_key: SecretStr

    # Langfuse é opcional: sem chaves, o tracing fica desligado e a API continua funcionando.
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_base_url: str = "https://cloud.langfuse.com"

    # Provedor de LLM com API no formato OpenAI (decisão D9): Groq por padrão, Ollama como
    # alternativa local. O modelo vem do ambiente porque o catálogo gratuito muda com frequência.
    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str | None = None

    # Embeddings: o Groq não oferece; padrão é o Ollama local com bge-m3 (1024 dimensões, kb.chunks).
    embedding_base_url: str | None = None
    embedding_api_key: SecretStr | None = None
    embedding_model: str | None = None

    # Requisições por minuto por IP nas rotas /v1 (OWASP Unbounded consumption)
    rate_limit_per_minute: int = 30

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
