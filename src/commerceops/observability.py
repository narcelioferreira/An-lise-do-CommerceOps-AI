"""Langfuse e pseudonimização de identificadores."""

from __future__ import annotations

import hashlib
import hmac
import logging

from langfuse import Langfuse

from commerceops.config import Settings

log = logging.getLogger(__name__)


def init_langfuse(settings: Settings) -> Langfuse:
    """Cria o cliente global do Langfuse. Sem chaves, devolve um cliente com tracing desligado.

    Uma falha do Langfuse nunca deve derrubar o atendimento: ele é observabilidade, não dependência.
    """
    if not settings.langfuse_enabled:
        log.warning("Langfuse sem chaves: tracing desligado")
        return Langfuse(public_key="disabled", secret_key="disabled", tracing_enabled=False)
    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key.get_secret_value(),  # type: ignore[union-attr]
        base_url=settings.langfuse_base_url,
        environment=settings.environment,
        release=settings.release,
    )


def hash_id(value: str, key: str) -> str:
    """HMAC-SHA256 truncado. Hash simples seria reversível: o dataset com os IDs é público."""
    return hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()[:16]
